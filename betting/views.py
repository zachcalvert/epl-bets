from django.conf import settings
from django.db.models import Min
from django.views.generic import TemplateView

from betting.models import Odds
from matches.models import Match


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
