"""
Avatar registry: icons, background colors, and unlockable frames.

Everything is defined as static Python data — no database tables.
Frames unlock 1:1 with badges from betting/badges.py.
"""

# ── Phosphor icon names available as avatar bases ────────────────────────────

AVATAR_ICONS = [
    "user-circle",
    "soccer-ball",
    "crown",
    "shield-star",
    "trophy",
    "target",
    "lightning",
    "flame",
    "star",
    "sword",
]

# ── Background hex colors (legible in both dark and light themes) ────────────

AVATAR_COLORS = [
    "#374151",  # Gray (default)
    "#f1f5f9",  # Light
    "#1e40af",  # Blue
    "#dc2626",  # Red
    "#059669",  # Green
    "#d97706",  # Amber
    "#7c3aed",  # Purple
]

# ── Frame definitions (1:1 mapping with badges) ─────────────────────────────

FRAME_REGISTRY = [
    {
        "slug": "first-blood",
        "name": "First Blood",
        "rarity": "common",
        "required_badge_slug": "first_blood",
    },
    {
        "slug": "century",
        "name": "Century",
        "rarity": "common",
        "required_badge_slug": "century",
    },
    {
        "slug": "called-the-upset",
        "name": "Called the Upset",
        "rarity": "uncommon",
        "required_badge_slug": "called_the_upset",
    },
    {
        "slug": "high-roller",
        "name": "High Roller",
        "rarity": "uncommon",
        "required_badge_slug": "high_roller",
    },
    {
        "slug": "perfect-matchweek",
        "name": "Perfect Matchweek",
        "rarity": "rare",
        "required_badge_slug": "perfect_matchweek",
    },
    {
        "slug": "sharp-eye",
        "name": "Sharp Eye",
        "rarity": "rare",
        "required_badge_slug": "sharp_eye",
    },
    {
        "slug": "underdog-hunter",
        "name": "Underdog Hunter",
        "rarity": "rare",
        "required_badge_slug": "underdog_hunter",
    },
    {
        "slug": "parlay-king",
        "name": "Parlay King",
        "rarity": "epic",
        "required_badge_slug": "parlay_king",
    },
    {
        "slug": "streak-master",
        "name": "Streak Master",
        "rarity": "epic",
        "required_badge_slug": "streak_master",
    },
]

_FRAME_MAP = {f["slug"]: f for f in FRAME_REGISTRY}


def get_frame_by_slug(slug):
    """Return frame dict or None."""
    return _FRAME_MAP.get(slug)


def get_unlocked_frames(user):
    """Return list of frame dicts the user has unlocked, with 'unlocked' key."""
    from betting.models import UserBadge

    earned_slugs = set(
        UserBadge.objects.filter(user=user).values_list(
            "badge__slug", flat=True
        )
    )
    result = []
    for frame in FRAME_REGISTRY:
        result.append(
            {**frame, "unlocked": frame["required_badge_slug"] in earned_slugs}
        )
    return result
