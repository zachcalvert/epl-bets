import json
import logging
from pathlib import Path

import httpx
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from matches.models import Match, MatchStats, Standing, Team

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).resolve().parent / "static_data"


class RateLimitError(Exception):
    pass


class FootballDataClient:
    BASE_URL = "https://api.football-data.org/v4/"

    def __init__(self):
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY},
            timeout=settings.API_TIMEOUT,
        )

    def _get(self, path, params=None):
        logger.info("football-data.org GET %s params=%s", path, params)
        resp = self.client.get(path, params=params)
        if resp.status_code == 429:
            logger.warning("Rate limited by football-data.org")
            raise RateLimitError("football-data.org rate limit exceeded")
        resp.raise_for_status()
        return resp.json()

    def get_teams(self, season):
        data = self._get("competitions/PL/teams", params={"season": season})
        return [self._normalize_team(t) for t in data.get("teams", [])]

    def get_matches(self, season, matchday=None, status=None):
        params = {"season": season}
        if matchday:
            params["matchday"] = matchday
        if status:
            params["status"] = status
        data = self._get("competitions/PL/matches", params=params)
        return [self._normalize_match(m, season) for m in data.get("matches", [])]

    def get_match(self, match_id):
        data = self._get(f"matches/{match_id}")
        return self._normalize_match(data, data.get("season", {}).get("id", ""))

    def get_head_to_head(self, match_external_id, limit=5):
        data = self._get(f"matches/{match_external_id}/head2head", params={"limit": limit})
        matches = [self._normalize_h2h_match(m) for m in data.get("matches", [])]
        aggregates = data.get("aggregates", {})
        home_team = aggregates.get("homeTeam", {})
        away_team = aggregates.get("awayTeam", {})
        summary = {
            "home_wins": home_team.get("wins", 0),
            "away_wins": away_team.get("wins", 0),
            "draws": aggregates.get("numberOfDraws", 0) or home_team.get("draws", 0),
        }
        return matches, summary

    def get_team_form(self, team_external_id, limit=5):
        data = self._get(
            "matches",
            params={"team": team_external_id, "status": "FINISHED", "limit": limit},
        )
        results = []
        for m in data.get("matches", [])[-limit:]:
            entry = self._normalize_h2h_match(m)
            score = m.get("score", {}).get("fullTime", {})
            home_id = m.get("homeTeam", {}).get("id")
            hs = score.get("home")
            as_ = score.get("away")
            if hs is not None and as_ is not None:
                if home_id == team_external_id:
                    entry["result"] = "W" if hs > as_ else ("D" if hs == as_ else "L")
                else:
                    entry["result"] = "W" if as_ > hs else ("D" if as_ == hs else "L")
            else:
                entry["result"] = None
            results.append(entry)
        return results

    def get_standings(self, season):
        data = self._get("competitions/PL/standings", params={"season": season})
        standings = []
        for group in data.get("standings", []):
            if group.get("type") == "TOTAL":
                for entry in group.get("table", []):
                    standings.append(self._normalize_standing(entry, season))
        return standings

    def _normalize_team(self, t):
        return {
            "external_id": t["id"],
            "name": t["name"],
            "short_name": t.get("shortName", ""),
            "tla": t.get("tla", ""),
            "crest_url": t.get("crest", ""),
            "venue": t.get("venue", ""),
        }

    def _normalize_match(self, m, season):
        score = m.get("score", {})
        full_time = score.get("fullTime", {})
        return {
            "external_id": m["id"],
            "home_team_external_id": m["homeTeam"]["id"],
            "away_team_external_id": m["awayTeam"]["id"],
            "home_score": full_time.get("home"),
            "away_score": full_time.get("away"),
            "status": m.get("status", "SCHEDULED"),
            "matchday": m.get("matchday", 0),
            "kickoff": parse_datetime(m["utcDate"]) if m.get("utcDate") else None,
            "season": str(season),
        }

    def _normalize_h2h_match(self, m):
        score = m.get("score", {})
        full_time = score.get("fullTime", {})
        return {
            "date": m.get("utcDate", "")[:10],
            "home_team": m.get("homeTeam", {}).get("shortName") or m.get("homeTeam", {}).get("name", ""),
            "away_team": m.get("awayTeam", {}).get("shortName") or m.get("awayTeam", {}).get("name", ""),
            "home_score": full_time.get("home"),
            "away_score": full_time.get("away"),
        }

    def _normalize_standing(self, entry, season):
        return {
            "team_external_id": entry["team"]["id"],
            "season": str(season),
            "position": entry["position"],
            "played": entry.get("playedGames", 0),
            "won": entry.get("won", 0),
            "drawn": entry.get("draw", 0),
            "lost": entry.get("lost", 0),
            "goals_for": entry.get("goalsFor", 0),
            "goals_against": entry.get("goalsAgainst", 0),
            "goal_difference": entry.get("goalDifference", 0),
            "points": entry.get("points", 0),
        }

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------


def sync_teams(season, offline=False):
    if offline:
        with open(STATIC_DATA_DIR / "teams.json") as f:
            teams_data = json.load(f)
    else:
        with FootballDataClient() as client:
            teams_data = client.get_teams(season)

    created = updated = 0
    for t in teams_data:
        _, was_created = Team.objects.update_or_create(
            external_id=t["external_id"],
            defaults={
                "name": t["name"],
                "short_name": t["short_name"],
                "tla": t["tla"],
                "crest_url": t["crest_url"],
                "venue": t["venue"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_teams: created=%d updated=%d", created, updated)
    return created, updated


def sync_matches(season, matchday=None, status=None, offline=False):
    if offline:
        with open(STATIC_DATA_DIR / "matches.json") as f:
            matches_data = json.load(f)
    else:
        with FootballDataClient() as client:
            matches_data = client.get_matches(season, matchday=matchday, status=status)

    # Pre-fetch team lookup
    team_map = {t.external_id: t for t in Team.objects.all()}

    created = updated = 0
    for m in matches_data:
        home = team_map.get(m["home_team_external_id"])
        away = team_map.get(m["away_team_external_id"])
        if not home or not away:
            logger.warning(
                "Skipping match %s: missing team(s) home=%s away=%s",
                m["external_id"],
                m["home_team_external_id"],
                m["away_team_external_id"],
            )
            continue

        _, was_created = Match.objects.update_or_create(
            external_id=m["external_id"],
            defaults={
                "home_team": home,
                "away_team": away,
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "status": m["status"],
                "matchday": m["matchday"],
                "kickoff": m["kickoff"],
                "season": m["season"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_matches: created=%d updated=%d", created, updated)
    return created, updated


def sync_standings(season, offline=False):
    if offline:
        with open(STATIC_DATA_DIR / "standings.json") as f:
            standings_data = json.load(f)
    else:
        with FootballDataClient() as client:
            standings_data = client.get_standings(season)

    team_map = {t.external_id: t for t in Team.objects.all()}

    created = updated = 0
    for s in standings_data:
        team = team_map.get(s["team_external_id"])
        if not team:
            logger.warning("Skipping standing: missing team %s", s["team_external_id"])
            continue

        _, was_created = Standing.objects.update_or_create(
            team=team,
            season=s["season"],
            defaults={
                "position": s["position"],
                "played": s["played"],
                "won": s["won"],
                "drawn": s["drawn"],
                "lost": s["lost"],
                "goals_for": s["goals_for"],
                "goals_against": s["goals_against"],
                "goal_difference": s["goal_difference"],
                "points": s["points"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_standings: created=%d updated=%d", created, updated)
    return created, updated


def fetch_match_hype_data(match):
    """Fetch and cache H2H + form data for a match.

    Returns the MatchStats instance (fresh or from cache). Never raises — on
    any API error the existing (possibly stale) record is returned, or None if
    no record exists yet.
    """
    stats, _ = MatchStats.objects.get_or_create(match=match)
    if not stats.is_stale():
        return stats

    try:
        with FootballDataClient() as client:
            h2h_matches, h2h_summary = client.get_head_to_head(match.external_id, limit=5)
            home_form = client.get_team_form(match.home_team.external_id, limit=5)
            away_form = client.get_team_form(match.away_team.external_id, limit=5)

        stats.h2h_json = h2h_matches
        stats.h2h_summary_json = h2h_summary
        stats.home_form_json = home_form
        stats.away_form_json = away_form
        stats.fetched_at = timezone.now()
        stats.save()
        logger.info("fetch_match_hype_data: updated stats for match %d", match.pk)
    except RateLimitError:
        logger.warning("fetch_match_hype_data: rate limited for match %d", match.pk)
    except Exception:
        logger.exception("fetch_match_hype_data: failed for match %d", match.pk)

    return stats
