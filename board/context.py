"""Shared context builder for bot board posts.

Provides get_board_context() which returns a structured dict with current
standings, last gameweek results, upcoming fixtures, and current matchday.
Consumed by all bot post generators in board/tasks.py.
"""

import logging

from django.conf import settings
from django.utils import timezone

from matches.models import Match, Standing

logger = logging.getLogger(__name__)


def get_board_context():
    """Return a dict with league context for bot post prompts.

    Keys:
        standings: list of dicts (position, team, played, won, drawn, lost, gd, points)
        last_gw_results: list of dicts (home, away, home_score, away_score, matchday)
        upcoming_fixtures: list of dicts (home, away, kickoff, matchday)
        current_matchday: int or None
    """
    season = getattr(settings, "CURRENT_SEASON", "2025")
    now = timezone.now()

    # Current standings
    standings_qs = Standing.objects.filter(season=season).select_related("team").order_by("position")
    standings = [
        {
            "position": s.position,
            "team": s.team.short_name or s.team.name,
            "tla": s.team.tla,
            "played": s.played,
            "won": s.won,
            "drawn": s.drawn,
            "lost": s.lost,
            "gd": s.goal_difference,
            "points": s.points,
        }
        for s in standings_qs
    ]

    # Determine current matchday from the most recent finished match
    last_finished = (
        Match.objects.filter(status=Match.Status.FINISHED, season=season)
        .order_by("-matchday", "-kickoff")
        .first()
    )
    current_matchday = last_finished.matchday if last_finished else None

    # Last GW results
    last_gw_results = []
    if current_matchday:
        results_qs = (
            Match.objects.filter(
                season=season,
                matchday=current_matchday,
                status=Match.Status.FINISHED,
            )
            .select_related("home_team", "away_team")
            .order_by("kickoff")
        )
        last_gw_results = [
            {
                "home": m.home_team.short_name or m.home_team.name,
                "away": m.away_team.short_name or m.away_team.name,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "matchday": m.matchday,
            }
            for m in results_qs
        ]

    # Upcoming fixtures (next 7 days)
    upcoming_qs = (
        Match.objects.filter(
            season=season,
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            kickoff__gte=now,
            kickoff__lte=now + timezone.timedelta(days=7),
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff")[:20]
    )
    upcoming_fixtures = [
        {
            "home": m.home_team.short_name or m.home_team.name,
            "away": m.away_team.short_name or m.away_team.name,
            "kickoff": m.kickoff.strftime("%a %d %b, %H:%M UTC"),
            "matchday": m.matchday,
        }
        for m in upcoming_qs
    ]

    return {
        "standings": standings,
        "last_gw_results": last_gw_results,
        "upcoming_fixtures": upcoming_fixtures,
        "current_matchday": current_matchday,
    }


def format_board_context_for_prompt(ctx):
    """Format the board context dict into a string for LLM prompts."""
    lines = []

    if ctx["current_matchday"]:
        lines.append(f"Current Matchday: {ctx['current_matchday']}")

    if ctx["standings"]:
        lines.append("\nLeague Table (top 10):")
        for s in ctx["standings"][:10]:
            lines.append(
                f"  {s['position']:>2}. {s['team']:<20} P:{s['played']} "
                f"W:{s['won']} D:{s['drawn']} L:{s['lost']} "
                f"GD:{s['gd']:+d} Pts:{s['points']}"
            )
        # Also show bottom 5 for relegation context
        if len(ctx["standings"]) > 15:
            lines.append("  ...")
            for s in ctx["standings"][-5:]:
                lines.append(
                    f"  {s['position']:>2}. {s['team']:<20} P:{s['played']} "
                    f"W:{s['won']} D:{s['drawn']} L:{s['lost']} "
                    f"GD:{s['gd']:+d} Pts:{s['points']}"
                )

    if ctx["last_gw_results"]:
        lines.append(f"\nGameweek {ctx['last_gw_results'][0]['matchday']} Results:")
        for r in ctx["last_gw_results"]:
            lines.append(f"  {r['home']} {r['home_score']}-{r['away_score']} {r['away']}")

    if ctx["upcoming_fixtures"]:
        lines.append("\nUpcoming Fixtures:")
        for f in ctx["upcoming_fixtures"][:10]:
            lines.append(f"  {f['home']} vs {f['away']} — {f['kickoff']}")

    return "\n".join(lines)
