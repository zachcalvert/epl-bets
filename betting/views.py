import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Min, Sum
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from betting.forms import PlaceBetForm
from betting.models import BetSlip, Odds, UserBalance
from betting.services import get_user_rank
from matches.models import Match

logger = logging.getLogger(__name__)


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
            matches_with_odds.append(match)

        ctx["matches"] = matches_with_odds
        return ctx


class OddsBoardPartialView(OddsBoardView):
    """Returns just the odds board body for HTMX polling."""

    template_name = "betting/partials/odds_board_body.html"


class PlaceBetView(LoginRequiredMixin, View):
    """Handle bet placement via HTMX POST."""

    def post(self, request, match_pk):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            pk=match_pk,
        )

        # Only allow bets on upcoming matches
        if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
            return render(
                request,
                "betting/partials/bet_form.html",
                {"match": match, "form": PlaceBetForm(), "error": "This match is no longer accepting bets."},
            )

        form = PlaceBetForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "betting/partials/bet_form.html",
                {"match": match, "form": form, "error": None},
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
                "betting/partials/bet_form.html",
                {"match": match, "form": form, "error": "No odds available for this match."},
            )

        # Atomic: deduct balance + create bet
        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return render(
                        request,
                        "betting/partials/bet_form.html",
                        {"match": match, "form": form, "error": f"Insufficient balance. You have {balance.balance:.2f} credits."},
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
            UserBalance.objects.create(user=request.user, balance=Decimal("1000.00") - stake)
            bet = BetSlip.objects.create(
                user=request.user,
                match=match,
                selection=selection,
                odds_at_placement=best_odds_val,
                stake=stake,
            )

        potential_payout = stake * best_odds_val
        return render(
            request,
            "betting/partials/bet_confirmation.html",
            {"bet": bet, "match": match, "potential_payout": potential_payout},
        )


class MyBetsView(LoginRequiredMixin, TemplateView):
    template_name = "betting/my_bets.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
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

        ctx["bets"] = bets
        ctx["total_staked"] = total_staked
        ctx["total_payout"] = total_payout
        ctx["net_pnl"] = total_payout - total_staked
        ctx["current_balance"] = current_balance
        ctx["user_rank"] = get_user_rank(user)
        return ctx


class QuickBetFormView(LoginRequiredMixin, View):
    """Return an inline bet form for the odds board."""

    def get(self, request, match_pk):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            pk=match_pk,
        )
        selection = request.GET.get("selection", "")
        form = PlaceBetForm(initial={"selection": selection})
        return render(
            request,
            "betting/partials/quick_bet_form.html",
            {"match": match, "form": form, "selection": selection},
        )
