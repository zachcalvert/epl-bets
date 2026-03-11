import json
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


def test_get_teams_and_matches_normalize_payloads(monkeypatch):
    client = FootballDataClient()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: {
            "teams": [
                {
                    "id": 1,
                    "name": "Arsenal FC",
                    "shortName": "Arsenal",
                    "tla": "ARS",
                    "crest": "https://example.com/arsenal.png",
                    "venue": "Emirates Stadium",
                }
            ],
            "matches": [
                {
                    "id": 10,
                    "homeTeam": {"id": 1},
                    "awayTeam": {"id": 2},
                    "score": {"fullTime": {"home": 2, "away": 1}},
                    "status": "FINISHED",
                    "matchday": 28,
                    "utcDate": "2026-03-11T20:00:00Z",
                }
            ],
        }
        if "matches" in path
        else {
            "teams": [
                {
                    "id": 1,
                    "name": "Arsenal FC",
                    "shortName": "Arsenal",
                    "tla": "ARS",
                    "crest": "https://example.com/arsenal.png",
                    "venue": "Emirates Stadium",
                }
            ]
        },
    )

    teams = client.get_teams("2025")
    matches = client.get_matches("2025", matchday=28, status="FINISHED")

    assert teams == [
        {
            "external_id": 1,
            "name": "Arsenal FC",
            "short_name": "Arsenal",
            "tla": "ARS",
            "crest_url": "https://example.com/arsenal.png",
            "venue": "Emirates Stadium",
        }
    ]
    assert matches[0]["external_id"] == 10
    assert matches[0]["kickoff"] == timezone.make_aware(datetime(2026, 3, 11, 20, 0))
    assert matches[0]["season"] == "2025"


def test_get_match_and_normalizers_cover_optional_fields(monkeypatch):
    client = FootballDataClient()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: {
            "id": 15,
            "homeTeam": {"id": 1},
            "awayTeam": {"id": 2},
            "score": {},
            "season": {"id": 2025},
        },
    )

    match = client.get_match(15)

    assert match == {
        "external_id": 15,
        "home_team_external_id": 1,
        "away_team_external_id": 2,
        "home_score": None,
        "away_score": None,
        "status": "SCHEDULED",
        "matchday": 0,
        "kickoff": None,
        "season": "2025",
    }
    assert client._normalize_team({"id": 2, "name": "Chelsea FC"}) == {
        "external_id": 2,
        "name": "Chelsea FC",
        "short_name": "",
        "tla": "",
        "crest_url": "",
        "venue": "",
    }


def test_client_context_manager_closes_http_client(monkeypatch):
    client = FootballDataClient()
    close = SimpleNamespace(called=False)

    def fake_close():
        close.called = True

    monkeypatch.setattr(client.client, "close", fake_close)
    client.close()
    assert close.called is True

    close.called = False
    managed = client.__enter__()
    assert managed is client
    client.__exit__()
    assert close.called is True


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


def test_sync_helpers_support_offline_static_json(tmp_path, monkeypatch):
    data_dir = tmp_path / "static_data"
    data_dir.mkdir()
    (data_dir / "teams.json").write_text(
        json.dumps(
            [
                {
                    "external_id": 1,
                    "name": "Arsenal FC",
                    "short_name": "Arsenal",
                    "tla": "ARS",
                    "crest_url": "https://example.com/arsenal.png",
                    "venue": "Emirates",
                }
            ]
        )
    )
    kickoff = timezone.make_aware(datetime(2026, 3, 11, 20, 0))
    (data_dir / "matches.json").write_text(
        json.dumps(
            [
                {
                    "external_id": 100,
                    "home_team_external_id": 1,
                    "away_team_external_id": 2,
                    "home_score": None,
                    "away_score": None,
                    "status": "SCHEDULED",
                    "matchday": 1,
                    "kickoff": kickoff.isoformat(),
                    "season": "2025",
                }
            ]
        )
    )
    (data_dir / "standings.json").write_text(
        json.dumps(
            [
                {
                    "team_external_id": 1,
                    "season": "2025",
                    "position": 1,
                    "played": 1,
                    "won": 1,
                    "drawn": 0,
                    "lost": 0,
                    "goals_for": 2,
                    "goals_against": 0,
                    "goal_difference": 2,
                    "points": 3,
                }
            ]
        )
    )
    monkeypatch.setattr("matches.services.STATIC_DATA_DIR", data_dir)
    TeamFactory(external_id=2, name="Chelsea FC")

    team_counts = sync_teams("2025", offline=True)
    match_counts = sync_matches("2025", offline=True)
    standing_counts = sync_standings("2025", offline=True)

    created_match = MatchFactory._meta.model.objects.get(external_id=100)
    assert team_counts == (1, 0)
    assert match_counts == (1, 0)
    assert standing_counts == (1, 0)
    assert created_match.kickoff == kickoff


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
