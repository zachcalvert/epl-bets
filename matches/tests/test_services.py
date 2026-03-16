import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from matches.models import Match, MatchStats
from matches.services import (
    FootballDataClient,
    RateLimitError,
    fetch_match_hype_data,
    get_team_form,
    sync_matches,
    sync_standings,
    sync_teams,
)
from matches.tests.factories import (
    MatchFactory,
    MatchStatsFactory,
    StandingFactory,
    TeamFactory,
)

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


# ---------------------------------------------------------------------------
# FootballDataClient — get_head_to_head
# ---------------------------------------------------------------------------

H2H_MATCH = {
    "utcDate": "2025-12-20T15:00:00Z",
    "homeTeam": {"id": 1, "shortName": "Arsenal", "name": "Arsenal FC"},
    "awayTeam": {"id": 2, "shortName": "Chelsea", "name": "Chelsea FC"},
    "score": {"fullTime": {"home": 2, "away": 1}},
}


def test_get_head_to_head_normalizes_matches_and_summary(monkeypatch):
    client = FootballDataClient()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: {"matches": [H2H_MATCH]},
    )

    # H2H_MATCH: Arsenal (id=1) beat Chelsea (id=2) 2-1 at home
    matches, summary = client.get_head_to_head(999, home_team_id=1, away_team_id=2, limit=5)

    assert len(matches) == 1
    assert matches[0] == {
        "date": "2025-12-20",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_score": 2,
        "away_score": 1,
    }
    assert summary == {"home_wins": 1, "away_wins": 0, "draws": 0}


def test_get_head_to_head_summary_counts_draws_and_away_wins(monkeypatch):
    draw_match = {
        "utcDate": "2025-10-01T15:00:00Z",
        "homeTeam": {"id": 2, "shortName": "Chelsea", "name": "Chelsea FC"},
        "awayTeam": {"id": 1, "shortName": "Arsenal", "name": "Arsenal FC"},
        "score": {"fullTime": {"home": 1, "away": 1}},
    }
    away_win_match = {
        "utcDate": "2025-08-01T15:00:00Z",
        "homeTeam": {"id": 2, "shortName": "Chelsea", "name": "Chelsea FC"},
        "awayTeam": {"id": 1, "shortName": "Arsenal", "name": "Arsenal FC"},
        "score": {"fullTime": {"home": 0, "away": 2}},
    }
    client = FootballDataClient()
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: {"matches": [H2H_MATCH, draw_match, away_win_match]},
    )

    _, summary = client.get_head_to_head(999, home_team_id=1, away_team_id=2, limit=5)

    # Arsenal (home_team_id=1) won H2H_MATCH and away_win_match; draw_match was a draw
    # home_wins/away_wins track wins for Arsenal/Chelsea overall, not per-venue
    assert summary == {"home_wins": 2, "away_wins": 0, "draws": 1}


def test_get_head_to_head_passes_limit_param(monkeypatch):
    client = FootballDataClient()
    captured = {}
    monkeypatch.setattr(
        client,
        "_get",
        lambda path, params=None: captured.update({"path": path, "params": params}) or {"matches": []},
    )

    client.get_head_to_head(42, home_team_id=1, away_team_id=2, limit=3)

    assert captured["params"] == {"limit": 3}
    assert "head2head" in captured["path"]


# ---------------------------------------------------------------------------
# get_team_form (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_team_form_win_from_home_perspective():
    team = TeamFactory()
    opponent = TeamFactory()
    MatchFactory(
        home_team=team, away_team=opponent,
        home_score=2, away_score=1,
        status=Match.Status.FINISHED,
        kickoff=timezone.now() - timedelta(days=1),
    )

    results = get_team_form(team)

    assert len(results) == 1
    assert results[0]["result"] == "W"


@pytest.mark.django_db
def test_get_team_form_win_from_away_perspective():
    team = TeamFactory()
    opponent = TeamFactory()
    MatchFactory(
        home_team=opponent, away_team=team,
        home_score=0, away_score=3,
        status=Match.Status.FINISHED,
        kickoff=timezone.now() - timedelta(days=1),
    )

    results = get_team_form(team)

    assert results[0]["result"] == "W"


@pytest.mark.django_db
def test_get_team_form_draw():
    team = TeamFactory()
    opponent = TeamFactory()
    MatchFactory(
        home_team=team, away_team=opponent,
        home_score=1, away_score=1,
        status=Match.Status.FINISHED,
        kickoff=timezone.now() - timedelta(days=1),
    )

    results = get_team_form(team)

    assert results[0]["result"] == "D"


@pytest.mark.django_db
def test_get_team_form_respects_limit():
    team = TeamFactory()
    opponent = TeamFactory()
    for i in range(8):
        MatchFactory(
            home_team=team, away_team=opponent,
            home_score=1, away_score=0,
            status=Match.Status.FINISHED,
            kickoff=timezone.now() - timedelta(days=i + 1),
        )

    results = get_team_form(team, limit=5)

    assert len(results) == 5


@pytest.mark.django_db
def test_get_team_form_ordered_oldest_first():
    """Results are returned chronologically (oldest first) for display."""
    team = TeamFactory()
    opponent = TeamFactory()
    for i in range(3):
        MatchFactory(
            home_team=team, away_team=opponent,
            home_score=i, away_score=0,
            status=Match.Status.FINISHED,
            kickoff=timezone.now() - timedelta(days=3 - i),
        )

    results = get_team_form(team, limit=5)

    dates = [r["date"] for r in results]
    assert dates == sorted(dates)


@pytest.mark.django_db
def test_get_team_form_excludes_unfinished():
    team = TeamFactory()
    opponent = TeamFactory()
    MatchFactory(home_team=team, away_team=opponent, status=Match.Status.SCHEDULED)

    results = get_team_form(team)

    assert results == []


# ---------------------------------------------------------------------------
# fetch_match_hype_data
# ---------------------------------------------------------------------------


class _FakeHypeClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get_head_to_head(self, match_id, home_team_id, away_team_id, limit=5):
        return (
            [{"date": "2025-01-01", "home_team": "A", "away_team": "B", "home_score": 1, "away_score": 0}],
            {"home_wins": 1, "away_wins": 0, "draws": 0},
        )

_FAKE_FORM = [{"date": "2025-01-01", "home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0, "result": "W"}]


def test_fetch_match_hype_data_creates_and_populates_stats(monkeypatch):
    match = MatchFactory()
    monkeypatch.setattr("matches.services.FootballDataClient", _FakeHypeClient)
    monkeypatch.setattr("matches.services.get_team_form", lambda team, limit=5: _FAKE_FORM)

    stats = fetch_match_hype_data(match)

    assert stats.match == match
    assert stats.h2h_json != []
    assert stats.home_form_json != []
    assert stats.away_form_json != []
    assert stats.fetched_at is not None
    assert MatchStats.objects.filter(match=match).count() == 1


def test_fetch_match_hype_data_returns_cached_when_fresh(monkeypatch):
    match = MatchFactory()
    existing = MatchStatsFactory(match=match)  # fetched_at=now() by default
    called = {"count": 0}

    class NeverCalledClient(_FakeHypeClient):
        def get_head_to_head(self, *args, **kwargs):
            called["count"] += 1
            return super().get_head_to_head(*args, **kwargs)

    monkeypatch.setattr("matches.services.FootballDataClient", NeverCalledClient)

    stats = fetch_match_hype_data(match)

    assert stats.pk == existing.pk
    assert called["count"] == 0


def test_fetch_match_hype_data_refreshes_stale_stats(monkeypatch):
    match = MatchFactory()
    stale = MatchStatsFactory(match=match, fetched_at=timezone.now() - timedelta(hours=25))
    monkeypatch.setattr("matches.services.FootballDataClient", _FakeHypeClient)

    stats = fetch_match_hype_data(match)
    stale.refresh_from_db()

    assert stale.fetched_at is not None
    assert stale.h2h_json != []
    assert stats.pk == stale.pk


def test_fetch_match_hype_data_returns_stale_stats_on_rate_limit(monkeypatch):
    match = MatchFactory()
    existing = MatchStatsFactory(match=match, fetched_at=None)  # stale

    class RateLimitedClient(_FakeHypeClient):
        def get_head_to_head(self, *args, **kwargs):
            raise RateLimitError("rate limited")

    monkeypatch.setattr("matches.services.FootballDataClient", RateLimitedClient)

    stats = fetch_match_hype_data(match)

    # Should return the existing record without raising
    assert stats.pk == existing.pk
    stats.refresh_from_db()
    assert stats.fetched_at is None  # not updated


def test_fetch_match_hype_data_returns_stale_stats_on_generic_error(monkeypatch):
    match = MatchFactory()
    existing = MatchStatsFactory(match=match, fetched_at=None)

    class BrokenClient(_FakeHypeClient):
        def get_head_to_head(self, *args, **kwargs):
            raise ConnectionError("network down")

    monkeypatch.setattr("matches.services.FootballDataClient", BrokenClient)

    stats = fetch_match_hype_data(match)

    assert stats.pk == existing.pk
