from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from betting.forms import PlaceBetForm
from betting.models import Odds
from betting.services import BOARD_TYPES, get_leaderboard_entries, get_user_rank
from matches.models import Match, Standing
from website.transparency import (
    GLOBAL_SCOPE,
    get_events,
    match_scope,
    page_scope,
    record_event,
)


def _build_transparency_context(scope, *, limit=8, categories=None):
    events = get_events(scope, limit=limit)
    latest_event = events[0] if events else None

    counts = {category: 0 for category in (categories or ["htmx", "websocket", "celery"])}
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


def _get_dashboard_transparency_context():
    return _build_transparency_context(
        page_scope("dashboard"),
        categories=["htmx", "websocket", "celery"],
    )


def _get_match_transparency_context(match_id):
    return _build_transparency_context(
        match_scope(match_id),
        categories=["htmx", "websocket", "celery", "betting"],
    )


class DashboardView(TemplateView):
    template_name = "matches/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = settings.CURRENT_SEASON
        today = timezone.now().date()

        # Try today's matches first
        matches = Match.objects.filter(
            season=season, kickoff__date=today
        ).select_related("home_team", "away_team")

        if not matches.exists():
            # Find the nearest matchday (next upcoming, or most recent)
            next_match = (
                Match.objects.filter(season=season, kickoff__date__gte=today)
                .order_by("kickoff")
                .first()
            )
            if next_match:
                matchday = next_match.matchday
            else:
                prev_match = (
                    Match.objects.filter(season=season, kickoff__date__lt=today)
                    .order_by("-kickoff")
                    .first()
                )
                matchday = prev_match.matchday if prev_match else 1

            matches = Match.objects.filter(
                season=season, matchday=matchday
            ).select_related("home_team", "away_team")

        # Annotate best odds per match
        matches = matches.order_by("kickoff")
        match_list = list(matches)
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

        for match in match_list:
            odds = odds_map.get(match.pk, {})
            match.best_home_odds = odds.get("best_home")
            match.best_draw_odds = odds.get("best_draw")
            match.best_away_odds = odds.get("best_away")

        ctx["matches"] = match_list
        ctx["current_matchday"] = match_list[0].matchday if match_list else None
        ctx["leaderboard"] = get_leaderboard_entries()
        ctx["user_rank"] = get_user_rank(self.request.user, ctx["leaderboard"])
        ctx["leaderboard_rendered_at"] = timezone.now()
        ctx.update(_get_dashboard_transparency_context())
        return ctx


class DashboardUnderTheHoodPartialView(TemplateView):
    template_name = "matches/partials/dashboard_under_the_hood.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_get_dashboard_transparency_context())
        return ctx


class LeaderboardPartialView(TemplateView):
    template_name = "matches/partials/leaderboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["leaderboard"] = get_leaderboard_entries()
        ctx["user_rank"] = get_user_rank(self.request.user, ctx["leaderboard"])
        ctx["leaderboard_rendered_at"] = timezone.now()
        record_event(
            scope=page_scope("dashboard"),
            scopes=[GLOBAL_SCOPE],
            category="htmx",
            source="leaderboard_partial",
            action="partial_refreshed",
            summary="Homepage leaderboard refreshed from the server.",
            detail=f"Returned {len(ctx['leaderboard'])} ranked balances.",
            status="info",
            route=self.request.path,
        )
        return ctx


class LeaderboardView(TemplateView):
    template_name = "matches/leaderboard.html"

    def _get_board_type(self):
        board_type = self.request.GET.get("type", "balance")
        return board_type if board_type in BOARD_TYPES else "balance"

    def get_template_names(self):
        if self.request.htmx:
            return ["matches/partials/leaderboard_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        board_type = self._get_board_type()
        ctx["leaderboard"] = get_leaderboard_entries(limit=None, board_type=board_type)
        ctx["user_rank"] = get_user_rank(
            self.request.user, ctx["leaderboard"], board_type=board_type
        )
        ctx["board_type"] = board_type
        ctx["board_types"] = BOARD_TYPES
        return ctx


class FixturesView(TemplateView):
    template_name = "matches/fixtures.html"

    def get_template_names(self):
        if self.request.htmx:
            return ["matches/partials/fixture_list.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = settings.CURRENT_SEASON
        matchdays = list(range(1, 39))

        # Determine current matchday
        today = timezone.now().date()
        next_match = (
            Match.objects.filter(season=season, kickoff__date__gte=today)
            .order_by("kickoff")
            .first()
        )
        default_matchday = next_match.matchday if next_match else 1

        try:
            matchday = int(self.request.GET.get("matchday", default_matchday))
        except (ValueError, TypeError):
            matchday = default_matchday

        matches = (
            Match.objects.filter(season=season, matchday=matchday)
            .select_related("home_team", "away_team")
            .order_by("kickoff")
        )

        # Annotate best odds
        match_list = list(matches)
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

        for match in match_list:
            odds = odds_map.get(match.pk, {})
            match.best_home_odds = odds.get("best_home")
            match.best_draw_odds = odds.get("best_draw")
            match.best_away_odds = odds.get("best_away")

        ctx["matches"] = match_list
        ctx["matchday"] = matchday
        ctx["matchdays"] = matchdays
        ctx["current_matchday"] = matchday
        return ctx


class LeagueTableView(TemplateView):
    template_name = "matches/league_table.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["standings"] = (
            Standing.objects.filter(season=settings.CURRENT_SEASON)
            .select_related("team")
            .order_by("position")
        )
        ctx["season"] = settings.CURRENT_SEASON
        return ctx


class MatchDetailView(DetailView):
    model = Match
    template_name = "matches/match_detail.html"
    context_object_name = "match"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team").prefetch_related(
            "odds"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        match = self.object
        odds_qs = match.odds.all().order_by("bookmaker")
        odds_list = list(odds_qs)

        if odds_list:
            best_home = min(o.home_win for o in odds_list)
            best_draw = min(o.draw for o in odds_list)
            best_away = min(o.away_win for o in odds_list)
            latest_odds_refresh = max(o.fetched_at for o in odds_list)
        else:
            best_home = best_draw = best_away = None
            latest_odds_refresh = None

        ctx["odds"] = odds_list
        ctx["best_home"] = best_home
        ctx["best_draw"] = best_draw
        ctx["best_away"] = best_away
        ctx["latest_odds_refresh"] = latest_odds_refresh
        ctx["match_updated_at"] = match.updated_at

        # Bet form for authenticated users
        if self.request.user.is_authenticated:
            ctx["form"] = PlaceBetForm()

        ctx.update(_get_match_transparency_context(match.pk))
        return ctx


class MatchUnderTheHoodPartialView(DetailView):
    model = Match
    template_name = "matches/partials/match_under_the_hood.html"
    context_object_name = "match"

    def get_queryset(self):
        return Match.objects.select_related("home_team", "away_team")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_get_match_transparency_context(self.object.pk))
        ctx["rendered_at"] = timezone.now()
        return ctx


class MatchOddsPartialView(MatchDetailView):
    """Returns just the odds table body for HTMX polling."""

    template_name = "matches/partials/odds_table_body.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        record_event(
            scope=page_scope("match_detail"),
            scopes=[GLOBAL_SCOPE, match_scope(self.object.pk)],
            category="htmx",
            source="match_odds_partial",
            action="partial_refreshed",
            summary="Match odds table refreshed.",
            detail=f"Rendered {len(ctx['odds'])} bookmaker rows for match {self.object.pk}.",
            status="info",
            route=self.request.path,
            entity_ref=self.object.pk,
        )
        return ctx
