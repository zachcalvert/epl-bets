import pytest

from betting.tests.factories import BadgeFactory, UserBadgeFactory
from matches.tests.factories import TeamFactory
from users.avatars import (
    AVATAR_COLORS,
    AVATAR_ICONS,
    FRAME_REGISTRY,
    get_frame_by_slug,
    get_unlocked_frames,
)
from users.forms import AvatarForm
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ── Registry sanity ───────────────────────────────────────────────────────────


def test_avatar_icons_is_non_empty_list_of_strings():
    assert len(AVATAR_ICONS) > 0
    assert all(isinstance(i, str) for i in AVATAR_ICONS)


def test_avatar_colors_are_valid_hex():
    for color in AVATAR_COLORS:
        assert color.startswith("#"), f"{color!r} does not start with #"
        assert len(color) == 7, f"{color!r} is not a 7-char hex"


def test_frame_slugs_are_unique():
    slugs = [f["slug"] for f in FRAME_REGISTRY]
    assert len(slugs) == len(set(slugs))


def test_frame_required_badge_slugs_are_unique():
    badge_slugs = [f["required_badge_slug"] for f in FRAME_REGISTRY]
    assert len(badge_slugs) == len(set(badge_slugs))


def test_frame_rarities_are_valid():
    valid = {"common", "uncommon", "rare", "epic"}
    for frame in FRAME_REGISTRY:
        assert frame["rarity"] in valid, f"{frame['slug']} has invalid rarity"


def test_frame_registry_required_fields():
    required = {"slug", "name", "rarity", "required_badge_slug"}
    for frame in FRAME_REGISTRY:
        assert required <= frame.keys(), f"{frame.get('slug')} missing fields"


# ── get_frame_by_slug ─────────────────────────────────────────────────────────


def test_get_frame_by_slug_returns_frame_for_known_slug():
    frame = FRAME_REGISTRY[0]
    result = get_frame_by_slug(frame["slug"])
    assert result == frame


def test_get_frame_by_slug_returns_none_for_unknown_slug():
    assert get_frame_by_slug("does-not-exist") is None


def test_get_frame_by_slug_returns_none_for_empty_string():
    assert get_frame_by_slug("") is None


# ── get_unlocked_frames ───────────────────────────────────────────────────────


def test_get_unlocked_frames_all_locked_for_new_user():
    user = UserFactory()
    frames = get_unlocked_frames(user)

    assert len(frames) == len(FRAME_REGISTRY)
    assert all(f["unlocked"] is False for f in frames)


def test_get_unlocked_frames_marks_earned_badge_frame_as_unlocked():
    frame_def = FRAME_REGISTRY[0]
    user = UserFactory()
    badge = BadgeFactory(slug=frame_def["required_badge_slug"])
    UserBadgeFactory(user=user, badge=badge)

    frames = get_unlocked_frames(user)
    unlocked = {f["slug"]: f["unlocked"] for f in frames}

    assert unlocked[frame_def["slug"]] is True
    # All others remain locked
    for slug, is_unlocked in unlocked.items():
        if slug != frame_def["slug"]:
            assert is_unlocked is False


def test_get_unlocked_frames_preserves_all_frame_fields():
    user = UserFactory()
    frames = get_unlocked_frames(user)

    for frame in frames:
        assert "slug" in frame
        assert "name" in frame
        assert "rarity" in frame
        assert "required_badge_slug" in frame
        assert "unlocked" in frame


# ── AvatarForm ────────────────────────────────────────────────────────────────


def test_avatar_form_valid_with_icon_and_color():
    user = UserFactory()
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": "",
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid(), form.errors


def test_avatar_form_valid_with_crest_url():
    user = UserFactory()
    team = TeamFactory()
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": "",
            "avatar_crest_url": team.crest_url,
        },
        user=user,
    )
    assert form.is_valid(), form.errors


def test_avatar_form_rejects_unrecognised_crest_url():
    user = UserFactory()
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": "",
            "avatar_crest_url": "https://evil.example.com/fake.png",
        },
        user=user,
    )
    assert form.is_valid() is False
    assert "avatar_crest_url" in form.errors


def test_avatar_form_rejects_invalid_icon():
    user = UserFactory()
    form = AvatarForm(
        data={
            "avatar_icon": "not-a-real-icon",
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": "",
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid() is False
    assert "avatar_icon" in form.errors


def test_avatar_form_rejects_invalid_color():
    user = UserFactory()
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": "#zzzzzz",
            "avatar_frame": "",
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid() is False
    assert "avatar_bg" in form.errors


def test_avatar_form_rejects_unknown_frame_slug():
    user = UserFactory()
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": "fake-frame-slug",
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid() is False
    assert "avatar_frame" in form.errors


def test_avatar_form_rejects_locked_frame():
    frame_def = FRAME_REGISTRY[0]
    user = UserFactory()  # no badges earned
    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": frame_def["slug"],
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid() is False
    assert "avatar_frame" in form.errors


def test_avatar_form_accepts_unlocked_frame():
    frame_def = FRAME_REGISTRY[0]
    user = UserFactory()
    badge = BadgeFactory(slug=frame_def["required_badge_slug"])
    UserBadgeFactory(user=user, badge=badge)

    form = AvatarForm(
        data={
            "avatar_icon": AVATAR_ICONS[0],
            "avatar_bg": AVATAR_COLORS[0],
            "avatar_frame": frame_def["slug"],
            "avatar_crest_url": "",
        },
        user=user,
    )
    assert form.is_valid(), form.errors
