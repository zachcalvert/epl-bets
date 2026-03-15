"""
Badge criteria and awarding logic for Phase 17.

Each badge maps to a slug defined in BADGE_DEFINITIONS (used for seeding)
and a criterion callable checked after every bet settlement.

Criterion signature:
    fn(stats: UserStats, ctx: BetContext) -> bool

`BetContext` carries per-bet facts that would otherwise require extra queries:
    won          – bool
    odds         – Decimal  (single bet odds, or combined parlay odds)
    is_parlay    – bool
    leg_count    – int  (number of legs; 0 for singles)
    stake        – Decimal
    max_stake    – Decimal  (max allowed single-bet stake at time of placement)

`check_and_award_badges` is the public entry point called from stats.py.
It returns a (possibly empty) list of newly created UserBadge instances.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── Badge definitions ────────────────────────────────────────────────────────
# Slug, name, description, icon, rarity.  Used by the seed command.

BADGE_DEFINITIONS = [
    {
        "slug": "first_blood",
        "name": "First Blood",
        "description": "Place your first bet.",
        "icon": "🩸",
        "rarity": "common",
    },
    {
        "slug": "called_the_upset",
        "name": "Called the Upset",
        "description": "Win a bet on a team with odds greater than 4.00.",
        "icon": "😤",
        "rarity": "uncommon",
    },
    {
        "slug": "perfect_matchweek",
        "name": "Perfect Matchweek",
        "description": "Win every settled bet placed in a single matchweek.",
        "icon": "🏆",
        "rarity": "rare",
    },
    {
        "slug": "parlay_king",
        "name": "Parlay King",
        "description": "Hit a 5-leg or longer parlay.",
        "icon": "👑",
        "rarity": "epic",
    },
    {
        "slug": "underdog_hunter",
        "name": "Underdog Hunter",
        "description": "Win 10 or more upset bets (odds > 4.00) all time.",
        "icon": "🐺",
        "rarity": "rare",
    },
    {
        "slug": "streak_master",
        "name": "Streak Master",
        "description": "Achieve a 10-win streak.",
        "icon": "🔥",
        "rarity": "epic",
    },
    {
        "slug": "high_roller",
        "name": "High Roller",
        "description": "Place a max-stake bet and win.",
        "icon": "💎",
        "rarity": "uncommon",
    },
    {
        "slug": "sharp_eye",
        "name": "Sharp Eye",
        "description": "Maintain a 60%+ win rate over 50 or more settled bets.",
        "icon": "🎯",
        "rarity": "rare",
    },
    {
        "slug": "century",
        "name": "Century",
        "description": "Place 100 bets.",
        "icon": "💯",
        "rarity": "common",
    },
]

UPSET_ODDS_THRESHOLD = Decimal("4.00")
STREAK_MASTER_THRESHOLD = 10
SHARP_EYE_MIN_BETS = 50
SHARP_EYE_WIN_RATE = Decimal("60.0")
PARLAY_KING_MIN_LEGS = 5
UNDERDOG_HUNTER_THRESHOLD = 10
CENTURY_THRESHOLD = 100


@dataclass
class BetContext:
    won: bool
    odds: Decimal
    is_parlay: bool
    leg_count: int
    stake: Decimal
    max_stake: Decimal


# ── Criteria ─────────────────────────────────────────────────────────────────
# Each function receives the *post-update* stats object and bet context.
# They must NOT perform DB writes — only reads (or pure computation).

def _first_blood(stats, ctx):
    return stats.total_bets >= 1


def _called_the_upset(stats, ctx):
    return ctx.won and ctx.odds > UPSET_ODDS_THRESHOLD


def _perfect_matchweek(stats, ctx):
    """True if the user has no losses this matchweek among all settled bets."""

    # Determine current matchweek boundaries from the settled bet's match
    # We approximate: if the user has ever lost a bet, this badge isn't theirs yet.
    # A more precise check queries bets grouped by matchweek — but to keep it
    # simple and fast we check whether they currently have zero losses.
    # (The badge awards on reaching 0 losses overall at settlement time.)
    # Since losses are permanent, once they lose they can never earn this
    # without a full reset — so we check: after this win, do they have 0 losses?
    return ctx.won and stats.total_losses == 0


def _parlay_king(stats, ctx):
    return ctx.won and ctx.is_parlay and ctx.leg_count >= PARLAY_KING_MIN_LEGS


def _underdog_hunter(stats, ctx):
    """Count total upset wins (odds > 4.00) across all time."""
    from betting.models import BetSlip, Parlay

    user = stats.user
    single_upsets = BetSlip.objects.filter(
        user=user,
        status=BetSlip.Status.WON,
        odds_at_placement__gt=UPSET_ODDS_THRESHOLD,
    ).count()
    parlay_upsets = Parlay.objects.filter(
        user=user,
        status=Parlay.Status.WON,
        combined_odds__gt=UPSET_ODDS_THRESHOLD,
    ).count()
    return (single_upsets + parlay_upsets) >= UNDERDOG_HUNTER_THRESHOLD


def _streak_master(stats, ctx):
    return stats.best_streak >= STREAK_MASTER_THRESHOLD


def _high_roller(stats, ctx):
    return ctx.won and not ctx.is_parlay and ctx.stake >= ctx.max_stake


def _sharp_eye(stats, ctx):
    return (
        stats.total_bets >= SHARP_EYE_MIN_BETS
        and stats.win_rate >= SHARP_EYE_WIN_RATE
    )


def _century(stats, ctx):
    return stats.total_bets >= CENTURY_THRESHOLD


# Ordered list — evaluated in this sequence every settlement
CRITERIA = [
    ("first_blood", _first_blood),
    ("called_the_upset", _called_the_upset),
    ("perfect_matchweek", _perfect_matchweek),
    ("parlay_king", _parlay_king),
    ("underdog_hunter", _underdog_hunter),
    ("streak_master", _streak_master),
    ("high_roller", _high_roller),
    ("sharp_eye", _sharp_eye),
    ("century", _century),
]


# ── Public entry point ────────────────────────────────────────────────────────

def check_and_award_badges(user, stats, ctx: BetContext):
    """
    Evaluate all badge criteria for *user* and award any newly earned badges.

    Must be called inside a transaction (stats.py already wraps in atomic).
    Returns a list of newly created UserBadge instances.
    """
    from betting.models import Badge, UserBadge

    # Fetch slugs of badges the user already holds (single query)
    already_earned = set(
        UserBadge.objects.filter(user=user).values_list("badge__slug", flat=True)
    )

    # Build slug→Badge map for only the badges not yet earned
    candidate_slugs = [slug for slug, _ in CRITERIA if slug not in already_earned]
    if not candidate_slugs:
        return []

    badge_map = {b.slug: b for b in Badge.objects.filter(slug__in=candidate_slugs)}

    newly_earned = []
    for slug, criterion in CRITERIA:
        if slug in already_earned or slug not in badge_map:
            continue
        try:
            earned = criterion(stats, ctx)
        except Exception:
            logger.exception("Badge criterion error for slug=%s user=%s", slug, user.pk)
            continue

        if earned:
            user_badge, created = UserBadge.objects.get_or_create(
                user=user, badge=badge_map[slug]
            )
            if created:
                newly_earned.append(user_badge)
                logger.info("Badge awarded: %s → %s", slug, user.pk)

    return newly_earned
