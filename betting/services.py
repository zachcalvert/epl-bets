import logging

import httpx
from django.conf import settings
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Cast
from django.utils import timezone

from betting.models import Odds, UserBalance, UserStats
from matches.models import Match, Team

logger = logging.getLogger(__name__)

# Mapping from Odds API team names (normalized) → football-data.org full names (normalized).
# Covers cases where the two APIs use different naming for the same club.
TEAM_NAME_ALIASES = {
    "wolves": "wolverhampton wanderers fc",
    "wolverhampton wanderers": "wolverhampton wanderers fc",
    "spurs": "tottenham hotspur fc",
    "tottenham hotspur": "tottenham hotspur fc",
    "tottenham": "tottenham hotspur fc",
    "west ham united": "west ham united fc",
    "west ham": "west ham united fc",
    "manchester united": "manchester united fc",
    "man united": "manchester united fc",
    "manchester city": "manchester city fc",
    "man city": "manchester city fc",
    "newcastle united": "newcastle united fc",
    "newcastle": "newcastle united fc",
    "nottingham forest": "nottingham forest fc",
    "nott'm forest": "nottingham forest fc",
    "leicester city": "leicester city fc",
    "leicester": "leicester city fc",
    "brighton and hove albion": "brighton & hove albion fc",
    "brighton hove": "brighton & hove albion fc",
    "brighton": "brighton & hove albion fc",
    "crystal palace": "crystal palace fc",
    "afc bournemouth": "afc bournemouth",
    "bournemouth": "afc bournemouth",
    "ipswich town": "ipswich town fc",
    "ipswich": "ipswich town fc",
    "arsenal": "arsenal fc",
    "aston villa": "aston villa fc",
    "brentford": "brentford fc",
    "chelsea": "chelsea fc",
    "everton": "everton fc",
    "fulham": "fulham fc",
    "liverpool": "liverpool fc",
    "sunderland": "sunderland afc",
    "burnley": "burnley fc",
    "leeds united": "leeds united fc",
}


def mask_email(email):
    local_part, _, domain = email.partition("@")
    if not domain:
        return email

    visible_count = min(2, len(local_part))
    visible_prefix = local_part[:visible_count]
    masked_suffix = "*" * max(len(local_part) - visible_count, 1)
    return f"{visible_prefix}{masked_suffix}@{domain}"


def get_public_identity(user):
    if getattr(user, "display_name", None):
        return user.display_name
    return mask_email(user.email)


BOARD_TYPES = ("balance", "profit", "win_rate", "streak")
WIN_RATE_MIN_BETS = 10


def get_leaderboard_entries(limit=10, board_type="balance"):
    if board_type == "balance":
        return _get_balance_leaderboard(limit)
    elif board_type == "profit":
        return _get_profit_leaderboard(limit)
    elif board_type == "win_rate":
        return _get_win_rate_leaderboard(limit)
    elif board_type == "streak":
        return _get_streak_leaderboard(limit)
    return _get_balance_leaderboard(limit)


def _annotate_identity(entries):
    for entry in entries:
        entry.display_identity = get_public_identity(entry.user)
    return entries


def _get_balance_leaderboard(limit):
    qs = UserBalance.objects.select_related("user").order_by("-balance", "user_id")
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def _get_profit_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(total_bets__gt=0)
        .order_by("-net_profit", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def _get_win_rate_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(total_bets__gte=WIN_RATE_MIN_BETS)
        .annotate(
            _win_rate=Case(
                When(total_bets=0, then=Value(0.0)),
                default=Cast(F("total_wins"), models.FloatField())
                / Cast(F("total_bets"), models.FloatField())
                * 100.0,
            )
        )
        .order_by("-_win_rate", "-total_bets", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def _get_streak_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(total_bets__gt=0)
        .order_by("-best_streak", "-current_streak", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def get_user_rank(user, leaderboard=None, board_type="balance"):
    if not getattr(user, "is_authenticated", False):
        return None

    leaderboard_user_ids = {entry.user_id for entry in leaderboard or []}
    if user.id in leaderboard_user_ids:
        return None

    if board_type == "balance":
        return _get_balance_rank(user)
    elif board_type in ("profit", "win_rate", "streak"):
        return _get_stats_rank(user, board_type)
    return _get_balance_rank(user)


def _get_balance_rank(user):
    try:
        balance = user.balance
    except UserBalance.DoesNotExist:
        return None

    higher_ranked_count = UserBalance.objects.filter(
        Q(balance__gt=balance.balance)
        | Q(balance=balance.balance, user_id__lt=user.id)
    ).count()

    balance.display_identity = get_public_identity(user)
    balance.rank = higher_ranked_count + 1
    return balance


def _get_stats_rank(user, board_type):
    try:
        stats = user.stats
    except UserStats.DoesNotExist:
        return None

    if stats.total_bets == 0:
        return None

    if board_type == "profit":
        higher = UserStats.objects.filter(
            Q(net_profit__gt=stats.net_profit)
            | Q(net_profit=stats.net_profit, user_id__lt=user.id)
        ).filter(total_bets__gt=0).count()
    elif board_type == "win_rate":
        if stats.total_bets < WIN_RATE_MIN_BETS:
            return None
        user_rate = stats.total_wins / stats.total_bets
        higher = (
            UserStats.objects.filter(total_bets__gte=WIN_RATE_MIN_BETS)
            .annotate(
                _win_rate=Cast(F("total_wins"), models.FloatField())
                / Cast(F("total_bets"), models.FloatField())
            )
            .filter(
                Q(_win_rate__gt=user_rate)
                | Q(_win_rate=user_rate, total_bets__gt=stats.total_bets)
                | Q(
                    _win_rate=user_rate,
                    total_bets=stats.total_bets,
                    user_id__lt=user.id,
                )
            )
            .count()
        )
    elif board_type == "streak":
        higher = UserStats.objects.filter(
            Q(best_streak__gt=stats.best_streak)
            | Q(best_streak=stats.best_streak, current_streak__gt=stats.current_streak)
            | Q(
                best_streak=stats.best_streak,
                current_streak=stats.current_streak,
                user_id__lt=user.id,
            )
        ).filter(total_bets__gt=0).count()
    else:
        return None

    stats.display_identity = get_public_identity(user)
    stats.rank = higher + 1
    return stats


def _normalize_name(name):
    return name.strip().lower()


def _build_team_lookup():
    """Build a lookup dict: normalized name → Team instance."""
    lookup = {}
    for team in Team.objects.all():
        lookup[_normalize_name(team.name)] = team
        if team.short_name:
            lookup[_normalize_name(team.short_name)] = team
    return lookup


def _resolve_team(name, lookup):
    """Resolve an Odds API team name to a Team record."""
    norm = _normalize_name(name)
    # Direct match on name or short_name
    if norm in lookup:
        return lookup[norm]
    # Check alias table
    canonical = TEAM_NAME_ALIASES.get(norm)
    if canonical and canonical in lookup:
        return lookup[canonical]
    return None


class OddsApiClient:
    BASE_URL = "https://api.the-odds-api.com/v4/"

    def __init__(self):
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=settings.API_TIMEOUT,
        )
        self.remaining_credits = None
        self.used_credits = None

    def get_epl_odds(self, markets="h2h", regions="uk"):
        params = {
            "apiKey": settings.ODDS_API_KEY,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        logger.info("the-odds-api GET sports/soccer_epl/odds markets=%s", markets)
        resp = self.client.get("sports/soccer_epl/odds", params=params)
        resp.raise_for_status()

        self.remaining_credits = resp.headers.get("x-requests-remaining")
        self.used_credits = resp.headers.get("x-requests-used")
        logger.info(
            "Odds API credits: remaining=%s used=%s",
            self.remaining_credits,
            self.used_credits,
        )

        return resp.json()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def sync_odds():
    with OddsApiClient() as client:
        events = client.get_epl_odds()

    team_lookup = _build_team_lookup()
    now = timezone.now()

    created = updated = 0
    skipped = 0

    for event in events:
        home_team = _resolve_team(event["home_team"], team_lookup)
        away_team = _resolve_team(event["away_team"], team_lookup)

        if not home_team or not away_team:
            logger.warning(
                "Could not resolve teams for odds event: %s vs %s",
                event["home_team"],
                event["away_team"],
            )
            skipped += 1
            continue

        # Find matching Match record
        match = (
            Match.objects.filter(home_team=home_team, away_team=away_team)
            .exclude(status__in=[Match.Status.FINISHED, Match.Status.CANCELLED])
            .order_by("kickoff")
            .first()
        )
        if not match:
            logger.warning(
                "No upcoming match found for %s vs %s", home_team.name, away_team.name
            )
            skipped += 1
            continue

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market["key"] != "h2h":
                    continue

                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                home_price = outcomes.get(event["home_team"])
                draw_price = outcomes.get("Draw")
                away_price = outcomes.get(event["away_team"])

                if not all([home_price, draw_price, away_price]):
                    continue

                _, was_created = Odds.objects.update_or_create(
                    match=match,
                    bookmaker=bookmaker["title"],
                    defaults={
                        "home_win": home_price,
                        "draw": draw_price,
                        "away_win": away_price,
                        "fetched_at": now,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

    logger.info(
        "sync_odds: created=%d updated=%d skipped=%d", created, updated, skipped
    )
    return created, updated
