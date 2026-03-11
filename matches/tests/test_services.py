from datetime import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from matches.services import (
    FootballDataClient,
    RateLimitError,
    sync_matches,
    sync_standings,
    sync_teams,
)
from matches.tests.factories import MatchFactory, StandingFactory, TeamFactory


pytestmark = pytest.mark.django_db


def test_football_data_client_get_raises_rate_limit_error(monkeypatch):
    client = FootballDataClient()

    def fake_get(path, params=None):
        return SimpleNamespace(status_code=429)

    monkeypatch.setattr(client.client, "get", fake_get)

    with pytest.raises(RateLimitError):
        client._get("competitions/PL/teams")


def test_football_data_client_get_returns_json_and_passes_params(monkeypatch):
    client = FootballDataClient()
    payload = {"matches": []}
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return Response()

    monkeypatch.setattr(client.client, "get", fake_get)

    result = client._get("competitions/PL/matches", params={"season": "2025"})

    assert result == payload
    assert captured == {"path": "competitions/PL/matches", "params": {"season": "2025"}}


def test_get_standings_normalizes_only_total_group(monkeypatch):
    client = FootballDataClient()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: {
            "standings": [
                {"type": "HOME", "table": [{"position": 1}]},
                {
                    "type": "TOTAL",
                    "table": [
                        {
                            "position": 1,
                            "playedGames": 10,
                            "won": 7,
                            "draw": 1,
                            "lost": 2,
                            "goalsFor": 20,
                            "goalsAgainst": 8,
                            "goalDifference": 12,
                            "points": 22,
                            "team": {"id": 10},
                        }
                    ],
                },
            ]
        },
    )

    standings = client.get_standings("2025")

    assert standings == [
        {
            "team_external_id": 10,
            "season": "2025",
            "position": 1,
            "played": 10,
            "won": 7,
            "drawn": 1,
            "lost": 2,
            "goals_for": 20,
            "goals_against": 8,
            "goal_difference": 12,
            "points": 22,
        }
    ]


def test_sync_teams_creates_and_updates_records(monkeypatch):
    existing = TeamFactory(external_id=1, name="Old Name")
    monkeypatch.setattr(
        "matches.services.FootballDataClient.get_teams",
        lambda self, season: [
            {
                "external_id": 1,
                "name": "New Name",
                "short_name": "New",
                "tla": "NEW",
                "crest_url": "https://example.com/new.png",
                "venue": "New Ground",
            },
            {
                "external_id": 2,
                "name": "Created FC",
                "short_name": "Created",
                "tla": "CRE",
                "crest_url": "https://example.com/created.png",
                "venue": "Created Ground",
            },
        ],
    )

    created, updated = sync_teams("2025")
    existing.refresh_from_db()

    assert (created, updated) == (1, 1)
    assert existing.name == "New Name"


def test_sync_matches_creates_updates_and_skips_missing_teams(monkeypatch):
    home = TeamFactory(external_id=1)
    away = TeamFactory(external_id=2)
    existing = MatchFactory(external_id=101, home_team=home, away_team=away, home_score=0, away_score=0)
    kickoff = timezone.make_aware(datetime(2026, 3, 11, 19, 0))
    monkeypatch.setattr(
        "matches.services.FootballDataClient.get_matches",
        lambda self, season, matchday=None, status=None: [
            {
                "external_id": 101,
                "home_team_external_id": 1,
                "away_team_external_id": 2,
                "home_score": 2,
                "away_score": 1,
                "status": "FINISHED",
                "matchday": 3,
                "kickoff": kickoff,
                "season": "2025",
            },
            {
                "external_id": 102,
                "home_team_external_id": 1,
                "away_team_external_id": 2,
                "home_score": None,
                "away_score": None,
                "status": "SCHEDULED",
                "matchday": 4,
                "kickoff": kickoff,
                "season": "2025",
            },
            {
                "external_id": 103,
                "home_team_external_id": 1,
                "away_team_external_id": 999,
                "home_score": None,
                "away_score": None,
                "status": "SCHEDULED",
                "matchday": 4,
                "kickoff": kickoff,
                "season": "2025",
            },
        ],
    )

    created, updated = sync_matches("2025")
    existing.refresh_from_db()

    assert (created, updated) == (1, 1)
    assert existing.home_score == 2
    assert existing.status == "FINISHED"


def test_sync_standings_creates_updates_and_skips_missing_teams(monkeypatch):
    team = TeamFactory(external_id=1)
    existing = StandingFactory(team=team, season="2025", points=10)
    monkeypatch.setattr(
        "matches.services.FootballDataClient.get_standings",
        lambda self, season: [
            {
                "team_external_id": 1,
                "season": "2025",
                "position": 1,
                "played": 10,
                "won": 8,
                "drawn": 1,
                "lost": 1,
                "goals_for": 25,
                "goals_against": 7,
                "goal_difference": 18,
                "points": 25,
            },
            {
                "team_external_id": 2,
                "season": "2025",
                "position": 2,
                "played": 10,
                "won": 7,
                "drawn": 2,
                "lost": 1,
                "goals_for": 22,
                "goals_against": 10,
                "goal_difference": 12,
                "points": 23,
            },
        ],
    )
    TeamFactory(external_id=2)

    created, updated = sync_standings("2025")
    existing.refresh_from_db()

    assert (created, updated) == (1, 1)
    assert existing.points == 25
