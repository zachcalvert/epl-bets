from datetime import timedelta

import pytest
from django.utils import timezone

from matches.models import Match
from matches.tests.factories import (
    MatchFactory,
    MatchStatsFactory,
    StandingFactory,
    TeamFactory,
)

pytestmark = pytest.mark.django_db


def test_team_str_returns_name():
    team = TeamFactory(name="Arsenal FC")

    assert str(team) == "Arsenal FC"


def test_match_str_uses_short_names_and_score_when_available():
    match = MatchFactory(
        home_team=TeamFactory(name="Arsenal FC", short_name="Arsenal"),
        away_team=TeamFactory(name="Chelsea FC", short_name="Chelsea"),
        home_score=2,
        away_score=1,
    )

    assert str(match) == "Arsenal vs Chelsea 2-1"


def test_match_str_falls_back_to_team_name_without_score():
    match = MatchFactory(
        home_team=TeamFactory(name="Arsenal FC", short_name=""),
        away_team=TeamFactory(name="Chelsea FC", short_name=""),
        home_score=None,
        away_score=None,
        status=Match.Status.TIMED,
    )

    assert str(match) == "Arsenal FC vs Chelsea FC"


def test_standing_str_returns_position_name_and_points():
    standing = StandingFactory(position=1, team=TeamFactory(name="Liverpool FC"), points=28)

    assert str(standing) == "1. Liverpool FC (28 pts)"


# ---------------------------------------------------------------------------
# MatchStats
# ---------------------------------------------------------------------------


def test_match_stats_str_references_match():
    match = MatchFactory(
        home_team=TeamFactory(short_name="Arsenal"),
        away_team=TeamFactory(short_name="Chelsea"),
    )
    stats = MatchStatsFactory(match=match, fetched_at=None)

    assert "Arsenal" in str(stats)


def test_match_stats_is_stale_when_never_fetched():
    stats = MatchStatsFactory(fetched_at=None)

    assert stats.is_stale() is True


def test_match_stats_is_stale_when_older_than_24_hours():
    stats = MatchStatsFactory(fetched_at=timezone.now() - timedelta(hours=25))

    assert stats.is_stale() is True


def test_match_stats_is_not_stale_within_24_hours():
    stats = MatchStatsFactory(fetched_at=timezone.now() - timedelta(hours=23))

    assert stats.is_stale() is False


def test_match_stats_is_not_stale_when_just_fetched():
    stats = MatchStatsFactory(fetched_at=timezone.now())

    assert stats.is_stale() is False
