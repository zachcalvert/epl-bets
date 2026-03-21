from decimal import Decimal

import pytest

from betting.odds_engine import (
    MAX_ODDS,
    MIN_ODDS,
    generate_all_upcoming_odds,
    generate_match_odds,
)
from matches.models import Match
from matches.tests.factories import MatchFactory, StandingFactory, TeamFactory

pytestmark = pytest.mark.django_db


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_standing(team=None, **kwargs):
    defaults = {
        "position": 10,
        "played": 30,
        "won": 12,
        "drawn": 6,
        "lost": 12,
        "goals_for": 40,
        "goals_against": 40,
        "goal_difference": 0,
        "points": 42,
    }
    defaults.update(kwargs)
    if team is None:
        team = TeamFactory()
    return StandingFactory(team=team, **defaults)


# ── Core odds generation ─────────────────────────────────────────────────────


class TestGenerateMatchOdds:
    def test_returns_three_positive_decimal_odds(self):
        home = _make_standing(position=5, points=55)
        away = _make_standing(position=15, points=30)

        result = generate_match_odds(home, away)

        assert "home_win" in result
        assert "draw" in result
        assert "away_win" in result
        assert all(v > Decimal("1.00") for v in result.values())

    def test_strong_home_team_has_lower_odds(self):
        """Top team at home vs bottom team → home odds should be low, away high."""
        home = _make_standing(position=1, points=80, played=30, won=25, drawn=3, lost=2)
        away = _make_standing(position=20, points=15, played=30, won=3, drawn=6, lost=21)

        result = generate_match_odds(home, away)

        assert result["home_win"] < Decimal("1.50")
        assert result["away_win"] > Decimal("6.00")

    def test_even_teams_have_similar_odds(self):
        """Two mid-table teams → odds should be relatively close."""
        home = _make_standing(position=10, points=42, played=30)
        away = _make_standing(position=11, points=41, played=30)

        result = generate_match_odds(home, away)

        # Home advantage means home < away, but they should be in the same ballpark
        assert result["home_win"] < result["away_win"]
        assert result["home_win"] > Decimal("1.50")
        assert result["away_win"] < Decimal("5.00")

    def test_home_advantage_is_visible(self):
        """Same teams swapping home/away should produce different odds."""
        team_a = _make_standing(position=6, points=50)
        team_b = _make_standing(position=8, points=45)

        odds_a_home = generate_match_odds(team_a, team_b)
        odds_b_home = generate_match_odds(team_b, team_a)

        # When team_a is home, their odds should be lower than when away
        assert odds_a_home["home_win"] < odds_b_home["away_win"]

    def test_draw_odds_higher_for_close_teams(self):
        """Close teams should have lower draw odds (more likely) than mismatched teams."""
        close_home = _make_standing(position=9, points=43)
        close_away = _make_standing(position=10, points=42)

        far_home = _make_standing(position=1, points=80, played=30, won=25, drawn=3, lost=2)
        far_away = _make_standing(position=20, points=15, played=30, won=3, drawn=6, lost=21)

        close_result = generate_match_odds(close_home, close_away)
        far_result = generate_match_odds(far_home, far_away)

        # Close teams → lower draw odds (higher probability)
        assert close_result["draw"] < far_result["draw"]

    def test_odds_are_clamped_within_bounds(self):
        home = _make_standing(position=1, points=90, played=30, won=29, drawn=1, lost=0)
        away = _make_standing(position=20, points=5, played=30, won=1, drawn=2, lost=27)

        result = generate_match_odds(home, away)

        for val in result.values():
            assert val >= MIN_ODDS
            assert val <= MAX_ODDS

    def test_odds_are_rounded_to_two_decimal_places(self):
        home = _make_standing(position=3, points=60)
        away = _make_standing(position=7, points=48)

        result = generate_match_odds(home, away)

        for val in result.values():
            assert val == val.quantize(Decimal("0.01"))

    def test_overround_exists(self):
        """Sum of implied probabilities should exceed 100% (bookmaker margin)."""
        home = _make_standing(position=4, points=55)
        away = _make_standing(position=12, points=38)

        result = generate_match_odds(home, away)

        implied_total = (
            Decimal("1") / result["home_win"]
            + Decimal("1") / result["draw"]
            + Decimal("1") / result["away_win"]
        )
        assert implied_total > Decimal("1.00")

    def test_handles_none_standings(self):
        """Teams with no standing data should get fallback mid-table odds."""
        result = generate_match_odds(None, None)

        assert all(v >= MIN_ODDS for v in result.values())
        assert all(v <= MAX_ODDS for v in result.values())

    def test_handles_zero_games_played(self):
        """Season start: teams with 0 games played should still get valid odds."""
        home = _make_standing(position=1, points=0, played=0, won=0, drawn=0, lost=0)
        away = _make_standing(position=20, points=0, played=0, won=0, drawn=0, lost=0)

        result = generate_match_odds(home, away)

        assert all(v >= MIN_ODDS for v in result.values())

    def test_identical_standings_favor_home(self):
        """Two identical teams → home should still be favored due to home advantage."""
        home = _make_standing(position=10, points=42)
        away = _make_standing(position=10, points=42)

        result = generate_match_odds(home, away)

        assert result["home_win"] < result["away_win"]


# ── Batch generation ──────────────────────────────────────────────────────────


class TestGenerateAllUpcomingOdds:
    def test_generates_odds_for_all_upcoming_matches(self):
        home1 = TeamFactory(name="Team A")
        away1 = TeamFactory(name="Team B")
        home2 = TeamFactory(name="Team C")
        away2 = TeamFactory(name="Team D")
        _make_standing(team=home1, position=1, points=70)
        _make_standing(team=away1, position=10, points=40)
        _make_standing(team=home2, position=5, points=55)
        _make_standing(team=away2, position=15, points=30)
        MatchFactory(home_team=home1, away_team=away1, status=Match.Status.SCHEDULED)
        MatchFactory(home_team=home2, away_team=away2, status=Match.Status.TIMED)

        results = generate_all_upcoming_odds()

        assert len(results) == 2
        for r in results:
            assert "match" in r
            assert "home_win" in r
            assert r["home_win"] >= MIN_ODDS

    def test_skips_finished_matches(self):
        home = TeamFactory()
        away = TeamFactory()
        _make_standing(team=home)
        _make_standing(team=away)
        MatchFactory(home_team=home, away_team=away, status=Match.Status.FINISHED)

        results = generate_all_upcoming_odds()

        assert len(results) == 0

    def test_handles_missing_standings_gracefully(self):
        """Matches for teams without standings should still get odds (fallback)."""
        home = TeamFactory()
        away = TeamFactory()
        MatchFactory(home_team=home, away_team=away, status=Match.Status.SCHEDULED)

        results = generate_all_upcoming_odds()

        assert len(results) == 1
        assert results[0]["home_win"] >= MIN_ODDS
