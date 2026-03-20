from datetime import timedelta

import pytest
from django.utils import timezone

from board.context import format_board_context_for_prompt, get_board_context
from matches.models import Match
from matches.tests.factories import MatchFactory, StandingFactory, TeamFactory

pytestmark = pytest.mark.django_db


class TestGetBoardContext:
    def test_returns_expected_keys(self):
        ctx = get_board_context()

        assert "standings" in ctx
        assert "last_gw_results" in ctx
        assert "upcoming_fixtures" in ctx
        assert "current_matchday" in ctx

    def test_empty_database(self):
        ctx = get_board_context()

        assert ctx["standings"] == []
        assert ctx["last_gw_results"] == []
        assert ctx["upcoming_fixtures"] == []
        assert ctx["current_matchday"] is None

    def test_standings_populated(self, settings):
        settings.CURRENT_SEASON = "2025"
        team = TeamFactory(short_name="Arsenal", tla="ARS")
        StandingFactory(team=team, season="2025", position=1, points=30)

        ctx = get_board_context()

        assert len(ctx["standings"]) == 1
        s = ctx["standings"][0]
        assert s["team"] == "Arsenal"
        assert s["tla"] == "ARS"
        assert s["position"] == 1
        assert s["points"] == 30

    def test_standings_ordered_by_position(self, settings):
        settings.CURRENT_SEASON = "2025"
        StandingFactory(season="2025", position=2)
        StandingFactory(season="2025", position=1)
        StandingFactory(season="2025", position=3)

        ctx = get_board_context()

        positions = [s["position"] for s in ctx["standings"]]
        assert positions == [1, 2, 3]

    def test_current_matchday_from_last_finished(self, settings):
        settings.CURRENT_SEASON = "2025"
        MatchFactory(
            status=Match.Status.FINISHED,
            matchday=10,
            season="2025",
            kickoff=timezone.now() - timedelta(days=1),
        )

        ctx = get_board_context()

        assert ctx["current_matchday"] == 10

    def test_last_gw_results(self, settings):
        settings.CURRENT_SEASON = "2025"
        home = TeamFactory(short_name="Chelsea")
        away = TeamFactory(short_name="Spurs")
        MatchFactory(
            status=Match.Status.FINISHED,
            matchday=5,
            season="2025",
            home_team=home,
            away_team=away,
            home_score=2,
            away_score=1,
            kickoff=timezone.now() - timedelta(days=1),
        )

        ctx = get_board_context()

        assert len(ctx["last_gw_results"]) == 1
        r = ctx["last_gw_results"][0]
        assert r["home"] == "Chelsea"
        assert r["away"] == "Spurs"
        assert r["home_score"] == 2
        assert r["away_score"] == 1

    def test_upcoming_fixtures(self, settings):
        settings.CURRENT_SEASON = "2025"
        home = TeamFactory(short_name="Liverpool")
        away = TeamFactory(short_name="City")
        MatchFactory(
            status=Match.Status.SCHEDULED,
            season="2025",
            home_team=home,
            away_team=away,
            kickoff=timezone.now() + timedelta(days=2),
            matchday=11,
        )

        ctx = get_board_context()

        assert len(ctx["upcoming_fixtures"]) == 1
        f = ctx["upcoming_fixtures"][0]
        assert f["home"] == "Liverpool"
        assert f["away"] == "City"

    def test_upcoming_excludes_past_matches(self, settings):
        settings.CURRENT_SEASON = "2025"
        MatchFactory(
            status=Match.Status.SCHEDULED,
            season="2025",
            kickoff=timezone.now() - timedelta(days=1),
        )

        ctx = get_board_context()

        assert ctx["upcoming_fixtures"] == []

    def test_upcoming_excludes_beyond_7_days(self, settings):
        settings.CURRENT_SEASON = "2025"
        MatchFactory(
            status=Match.Status.SCHEDULED,
            season="2025",
            kickoff=timezone.now() + timedelta(days=10),
        )

        ctx = get_board_context()

        assert ctx["upcoming_fixtures"] == []


class TestFormatBoardContextForPrompt:
    def test_empty_context(self):
        ctx = {
            "standings": [],
            "last_gw_results": [],
            "upcoming_fixtures": [],
            "current_matchday": None,
        }

        result = format_board_context_for_prompt(ctx)

        assert result == ""

    def test_includes_matchday(self):
        ctx = {
            "standings": [],
            "last_gw_results": [],
            "upcoming_fixtures": [],
            "current_matchday": 15,
        }

        result = format_board_context_for_prompt(ctx)

        assert "Current Matchday: 15" in result

    def test_includes_standings_top_10(self):
        standings = [
            {
                "position": i,
                "team": f"Team {i}",
                "played": 20,
                "won": 10,
                "drawn": 5,
                "lost": 5,
                "gd": 10,
                "points": 35,
            }
            for i in range(1, 21)
        ]
        ctx = {
            "standings": standings,
            "last_gw_results": [],
            "upcoming_fixtures": [],
            "current_matchday": None,
        }

        result = format_board_context_for_prompt(ctx)

        assert "League Table (top 10)" in result
        assert "Team 1" in result
        assert "Team 10" in result
        # Bottom 5 shown when > 15 teams
        assert "Team 16" in result
        assert "Team 20" in result
        # Middle teams not shown
        assert "Team 11" not in result

    def test_includes_results(self):
        ctx = {
            "standings": [],
            "last_gw_results": [
                {
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "home_score": 3,
                    "away_score": 1,
                    "matchday": 10,
                }
            ],
            "upcoming_fixtures": [],
            "current_matchday": None,
        }

        result = format_board_context_for_prompt(ctx)

        assert "Gameweek 10 Results" in result
        assert "Arsenal 3-1 Chelsea" in result

    def test_includes_upcoming(self):
        ctx = {
            "standings": [],
            "last_gw_results": [],
            "upcoming_fixtures": [
                {
                    "home": "Liverpool",
                    "away": "City",
                    "kickoff": "Sat 22 Mar, 15:00 UTC",
                    "matchday": 11,
                }
            ],
            "current_matchday": None,
        }

        result = format_board_context_for_prompt(ctx)

        assert "Upcoming Fixtures" in result
        assert "Liverpool vs City" in result

    def test_no_bottom_5_when_15_or_fewer_teams(self):
        standings = [
            {
                "position": i,
                "team": f"Team {i}",
                "played": 20,
                "won": 10,
                "drawn": 5,
                "lost": 5,
                "gd": 10,
                "points": 35,
            }
            for i in range(1, 16)
        ]
        ctx = {
            "standings": standings,
            "last_gw_results": [],
            "upcoming_fixtures": [],
            "current_matchday": None,
        }

        result = format_board_context_for_prompt(ctx)

        assert "..." not in result
