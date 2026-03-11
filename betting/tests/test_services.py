from decimal import Decimal
from types import SimpleNamespace

import pytest

from betting.services import OddsApiClient, _build_team_lookup, _resolve_team, sync_odds
from betting.tests.factories import OddsFactory
from matches.models import Match
from matches.tests.factories import MatchFactory, TeamFactory


pytestmark = pytest.mark.django_db


def test_build_team_lookup_indexes_name_and_short_name():
    team = TeamFactory(name="Manchester City FC", short_name="Man City")

    lookup = _build_team_lookup()

    assert lookup["manchester city fc"] == team
    assert lookup["man city"] == team


def test_resolve_team_supports_direct_alias_and_missing_lookup():
    direct = TeamFactory(name="Arsenal FC")
    alias_target = TeamFactory(name="Tottenham Hotspur FC")
    lookup = {
        "arsenal fc": direct,
        "tottenham hotspur fc": alias_target,
    }

    assert _resolve_team("Arsenal FC", lookup) == direct
    assert _resolve_team("Spurs", lookup) == alias_target
    assert _resolve_team("Unknown FC", lookup) is None


def test_odds_api_client_get_epl_odds_tracks_credit_headers(monkeypatch):
    client = OddsApiClient()

    class Response:
        headers = {
            "x-requests-remaining": "499",
            "x-requests-used": "1",
        }

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": "event-1"}]

    monkeypatch.setattr(client.client, "get", lambda path, params=None: Response())

    result = client.get_epl_odds()

    assert result == [{"id": "event-1"}]
    assert client.remaining_credits == "499"
    assert client.used_credits == "1"


def test_sync_odds_creates_updates_and_skips_unmatched_events(monkeypatch):
    home = TeamFactory(name="Arsenal FC", short_name="Arsenal")
    away = TeamFactory(name="Chelsea FC", short_name="Chelsea")
    match = MatchFactory(home_team=home, away_team=away, status=Match.Status.SCHEDULED)
    OddsFactory(match=match, bookmaker="Bet365", home_win="2.40", draw="3.30", away_win="3.10")
    monkeypatch.setattr(
        "betting.services.OddsApiClient.get_epl_odds",
        lambda self, markets="h2h", regions="uk": [
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "bookmakers": [
                    {
                        "title": "Bet365",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 2.10},
                                    {"name": "Draw", "price": 3.20},
                                    {"name": "Chelsea", "price": 3.80},
                                ],
                            }
                        ],
                    },
                    {
                        "title": "Sky Bet",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 2.25},
                                    {"name": "Chelsea", "price": 3.40},
                                ],
                            },
                            {"key": "spreads", "outcomes": []},
                        ],
                    },
                ],
            },
            {
                "home_team": "Unknown",
                "away_team": "Chelsea",
                "bookmakers": [],
            },
        ],
    )

    created, updated = sync_odds()

    assert (created, updated) == (0, 1)
    odds = match.odds.get(bookmaker="Bet365")
    assert odds.home_win == Decimal("2.10")
    assert match.odds.count() == 1


def test_sync_odds_skips_when_no_upcoming_match_exists(monkeypatch):
    TeamFactory(name="Liverpool FC", short_name="Liverpool")
    TeamFactory(name="Everton FC", short_name="Everton")
    MatchFactory(status=Match.Status.FINISHED)
    monkeypatch.setattr(
        "betting.services.OddsApiClient.get_epl_odds",
        lambda self, markets="h2h", regions="uk": [
            {
                "home_team": "Liverpool",
                "away_team": "Everton",
                "bookmakers": [
                    {
                        "title": "Betfred",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Liverpool", "price": 1.80},
                                    {"name": "Draw", "price": 3.50},
                                    {"name": "Everton", "price": 4.50},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )

    created, updated = sync_odds()

    assert (created, updated) == (0, 0)
