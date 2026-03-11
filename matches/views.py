from django.conf import settings
from django.db.models import Min
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from matches.models import Match, Standing


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

        from betting.models import Odds

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

        from betting.models import Odds

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
        else:
            best_home = best_draw = best_away = None

        ctx["odds"] = odds_list
        ctx["best_home"] = best_home
        ctx["best_draw"] = best_draw
        ctx["best_away"] = best_away

        # Bet form for authenticated users
        if self.request.user.is_authenticated:
            from betting.forms import PlaceBetForm

            ctx["form"] = PlaceBetForm()

        return ctx


class MatchOddsPartialView(MatchDetailView):
    """Returns just the odds table body for HTMX polling."""

    template_name = "matches/partials/odds_table_body.html"
