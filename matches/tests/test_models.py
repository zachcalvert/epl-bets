import pytest

from matches.models import Match
from matches.tests.factories import MatchFactory, StandingFactory, TeamFactory

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
