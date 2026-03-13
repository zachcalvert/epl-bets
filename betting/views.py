import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Max, Min, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from betting.forms import DisplayNameForm, PlaceBetForm
from betting.models import BetSlip, Odds, UserBalance
from betting.services import get_public_identity, get_user_rank, mask_email
from matches.models import Match
from rewards.models import RewardDistribution
from website.transparency import (
    GLOBAL_SCOPE,
    get_events,
    match_scope,
    page_scope,
    record_event,
)

logger = logging.getLogger(__name__)


def _get_odds_board_transparency_context():
    events = get_events(page_scope("odds_board"), limit=8)
    latest_event = events[0] if events else None

    counts = {
        "htmx": 0,
        "celery": 0,
        "betting": 0,
    }
    for event in events:
        category = event["category"]
        if category in counts:
            counts[category] += 1

    tracked_categories = [category for category, count in counts.items() if count]
    if not tracked_categories:
        tracked_categories = list(counts.keys())

    return {
        "under_the_hood_events": events,
        "under_the_hood_latest": latest_event,
        "under_the_hood_counts": counts,
        "under_the_hood_tracked_categories": tracked_categories,
    }


def _get_latest_odds_refresh(match_ids):
    if not match_ids:
        return None
    return Odds.objects.filter(match_id__in=match_ids).aggregate(
        latest_refresh=Max("fetched_at")
    )["latest_refresh"]


class OddsBoardView(TemplateView):
    template_name = "betting/odds_board.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        upcoming = (
            Match.objects.filter(
                season=settings.CURRENT_SEASON,
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            )
            .select_related("home_team", "away_team")
            .order_by("kickoff")
        )

        match_list = list(upcoming)
        match_ids = [m.pk for m in match_list]

        best_odds = (
            Odds.objects.filter(match_id__in=match_ids)
            .values("match_id")
            .annotate(
                best_home=Min("home_win"),
                best_draw=Min("draw"),
                best_away=Min("away_win"),
            )
        )
        odds_map = {o["match_id"]: o for o in best_odds}

        matches_with_odds = []
        for match in match_list:
            odds = odds_map.get(match.pk, {})
            match.best_home_odds = odds.get("best_home")
            match.best_draw_odds = odds.get("best_draw")
            match.best_away_odds = odds.get("best_away")
            if any(
                odd is not None
                for odd in (
                    match.best_home_odds,
                    match.best_draw_odds,
                    match.best_away_odds,
                )
            ):
                matches_with_odds.append(match)

        ctx["matches"] = matches_with_odds
        ctx["last_odds_refresh"] = _get_latest_odds_refresh(match_ids)
        ctx["rendered_at"] = timezone.now()
        ctx.update(_get_odds_board_transparency_context())
        return ctx


class OddsBoardUnderTheHoodPartialView(TemplateView):
    template_name = "betting/partials/odds_board_under_the_hood.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_get_odds_board_transparency_context())
        ctx["rendered_at"] = timezone.now()
        return ctx


class OddsBoardPartialView(OddsBoardView):
    """Returns just the odds board body for HTMX polling."""

    template_name = "betting/partials/odds_board_body.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        record_event(
            scope=page_scope("odds_board"),
            scopes=[GLOBAL_SCOPE],
            category="htmx",
            source="odds_board_partial",
            action="partial_refreshed",
            summary="Odds board refreshed with the latest stored prices.",
            detail=f"Rendered {len(ctx['matches'])} upcoming matches.",
            status="info",
            route=self.request.path,
        )
        return ctx


class PlaceBetView(LoginRequiredMixin, View):
    """Handle bet placement via HTMX POST."""

    def _error_template(self, container_id):
        """Return the appropriate error template based on context."""
        if container_id:
            return "betting/partials/quick_bet_form.html"
        return "betting/partials/bet_form.html"

    def _get_odds_context(self, match, selection="", container_id=""):
        """Return odds context for payout preview on error re-renders."""
        if container_id:
            # Quick bet form: pass selected_odds for the chosen outcome
            odds_field_map = {"HOME_WIN": "home_win", "DRAW": "draw", "AWAY_WIN": "away_win"}
            odds_field = odds_field_map.get(selection)
            if odds_field:
                result = Odds.objects.filter(match=match).aggregate(best=Min(odds_field))
                return {"selected_odds": result.get("best")}
            return {}
        # Full bet form: pass all three best odds
        result = Odds.objects.filter(match=match).aggregate(
            best_home=Min("home_win"), best_draw=Min("draw"), best_away=Min("away_win"),
        )
        return {"best_home": result["best_home"], "best_draw": result["best_draw"], "best_away": result["best_away"]}

    def post(self, request, match_pk):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            pk=match_pk,
        )
        container_id = request.POST.get("container_id", "")

        # Only allow bets on upcoming matches
        if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
            selection_val = request.POST.get("selection", "")
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": PlaceBetForm(),
                    "selection": selection_val,
                    "container_id": container_id,
                    "error": "This match is no longer accepting bets.",
                    **self._get_odds_context(match, selection_val, container_id),
                },
            )

        form = PlaceBetForm(request.POST)
        if not form.is_valid():
            selection_val = request.POST.get("selection", "")
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": form,
                    "selection": selection_val,
                    "container_id": container_id,
                    "error": None,
                    **self._get_odds_context(match, selection_val, container_id),
                },
            )

        selection = form.cleaned_data["selection"]
        stake = form.cleaned_data["stake"]

        # Look up best odds for this selection
        odds_field = {
            BetSlip.Selection.HOME_WIN: "home_win",
            BetSlip.Selection.DRAW: "draw",
            BetSlip.Selection.AWAY_WIN: "away_win",
        }[selection]

        best_odds_val = (
            Odds.objects.filter(match=match)
            .aggregate(best=Min(odds_field))
            .get("best")
        )
        if not best_odds_val:
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": form,
                    "selection": selection,
                    "container_id": container_id,
                    "error": "No odds available for this match.",
                    **self._get_odds_context(match, selection, container_id),
                },
            )

        # Atomic: deduct balance + create bet
        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return render(
                        request,
                        self._error_template(container_id),
                        {
                            "match": match,
                            "form": form,
                            "selection": selection,
                            "container_id": container_id,
                            "error": f"Insufficient balance. You have {balance.balance:.2f} credits.",
                            **self._get_odds_context(match, selection, container_id),
                        },
                    )

                balance.balance -= stake
                balance.save(update_fields=["balance"])

                bet = BetSlip.objects.create(
                    user=request.user,
                    match=match,
                    selection=selection,
                    odds_at_placement=best_odds_val,
                    stake=stake,
                )
        except UserBalance.DoesNotExist:
            # Auto-create balance if missing (shouldn't happen with signup flow)
            balance = UserBalance.objects.create(user=request.user, balance=Decimal("1000.00") - stake)
            bet = BetSlip.objects.create(
                user=request.user,
                match=match,
                selection=selection,
                odds_at_placement=best_odds_val,
                stake=stake,
            )

        potential_payout = stake * best_odds_val
        record_event(
            scope=match_scope(match.pk),
            scopes=[GLOBAL_SCOPE, page_scope("match_detail")],
            category="betting",
            source="place_bet",
            action="bet_placed",
            summary=f"Bet placed on {match.home_team.short_name or match.home_team.name} vs {match.away_team.short_name or match.away_team.name}.",
            detail=f"Selection {selection} at {best_odds_val} for {stake} credits.",
            status="success",
            route=request.path,
            entity_ref=match.pk,
        )
        return render(
            request,
            "betting/partials/bet_confirmation.html",
            {
                "bet": bet,
                "match": match,
                "potential_payout": potential_payout,
                "balance": f"{balance.balance:.2f}",
            },
        )


class MyBetsView(LoginRequiredMixin, TemplateView):
    template_name = "betting/my_bets.html"

    def _build_context(self, form=None, account_save_success=False):
        ctx = super().get_context_data()
        user = self.request.user

        bets = (
            BetSlip.objects.filter(user=user)
            .select_related("match__home_team", "match__away_team")
        )

        totals = bets.aggregate(
            total_staked=Sum("stake"),
            total_payout=Sum("payout"),
        )
        total_staked = totals["total_staked"] or Decimal("0")
        total_payout = totals["total_payout"] or Decimal("0")

        balance = getattr(user, "balance", None)
        current_balance = balance.balance if balance else Decimal("1000.00")

        reward_distributions = (
            RewardDistribution.objects.filter(user=user)
            .select_related("reward")
        )
        total_rewards = (
            reward_distributions.aggregate(
                total=Sum("reward__amount")
            )["total"]
            or Decimal("0")
        )

        # Build unified activity feed sorted by date descending
        activity = []
        for bet in bets:
            activity.append({"type": "bet", "date": bet.created_at, "item": bet})
        for dist in reward_distributions:
            activity.append({"type": "reward", "date": dist.created_at, "item": dist})
        activity.sort(key=lambda a: a["date"], reverse=True)

        ctx["bets"] = bets
        ctx["total_staked"] = total_staked
        ctx["total_payout"] = total_payout
        ctx["net_pnl"] = total_payout - total_staked
        ctx["current_balance"] = current_balance
        ctx["total_rewards"] = total_rewards
        ctx["activity"] = activity
        ctx["user_rank"] = get_user_rank(user)
        ctx["display_name_form"] = form or DisplayNameForm(instance=user)
        ctx["account_public_identity"] = get_public_identity(user)
        ctx["account_masked_email"] = mask_email(user.email)
        ctx["account_save_success"] = account_save_success
        return ctx

    def get_context_data(self, **kwargs):
        return self._build_context()

    def post(self, request, *args, **kwargs):
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            if request.htmx:
                return render(
                    request,
                    "betting/partials/account_settings_card.html",
                    self._build_context(
                        form=DisplayNameForm(instance=request.user),
                        account_save_success=True,
                    ),
                )
            return self.render_to_response(
                self._build_context(
                    form=DisplayNameForm(instance=request.user),
                    account_save_success=True,
                )
            )

        context = self._build_context(form=form)
        if request.htmx:
            return render(
                request,
                "betting/partials/account_settings_card.html",
                context,
                status=422,
            )
        return self.render_to_response(context, status=422)


class QuickBetFormView(LoginRequiredMixin, View):
    """Return an inline bet form for the odds board."""

    ODDS_FIELD_MAP = {
        "HOME_WIN": "home_win",
        "DRAW": "draw",
        "AWAY_WIN": "away_win",
    }

    def get(self, request, match_pk):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            pk=match_pk,
        )
        selection = request.GET.get("selection", "")
        container_id = request.GET.get("container", "")
        form = PlaceBetForm(initial={"selection": selection})

        selected_odds = None
        odds_field = self.ODDS_FIELD_MAP.get(selection)
        if odds_field:
            result = Odds.objects.filter(match=match).aggregate(best=Min(odds_field))
            selected_odds = result.get("best")

        return render(
            request,
            "betting/partials/quick_bet_form.html",
            {
                "match": match,
                "form": form,
                "selection": selection,
                "container_id": container_id,
                "selected_odds": selected_odds,
            },
        )
