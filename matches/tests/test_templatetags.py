from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from matches.templatetags.match_tags import (
    _coerce_datetime,
    _humanize_delta,
    format_odds,
    relative_time,
    score_display,
    status_badge,
)


def test_status_badge_for_scheduled_match_formats_local_kickoff(settings):
    settings.TIME_ZONE = "UTC"
    match = SimpleNamespace(
        status="SCHEDULED",
        kickoff=timezone.make_aware(datetime(2026, 3, 11, 20, 30)),
    )

    html = status_badge(match)

    assert "Wed 20:30" in html


def test_status_badge_for_live_match_uses_live_label():
    html = status_badge(SimpleNamespace(status="IN_PLAY", kickoff=timezone.now()))

    assert "LIVE" in html
    assert "text-accent" in html


@pytest.mark.parametrize(
    ("status", "expected_label"),
    [
        ("PAUSED", "HT"),
        ("FINISHED", "FT"),
        ("POSTPONED", "PP"),
        ("CANCELLED", "CAN"),
    ],
)
def test_status_badge_for_mapped_terminal_statuses(status, expected_label):
    html = status_badge(SimpleNamespace(status=status, kickoff=timezone.now()))

    assert expected_label in html


def test_status_badge_falls_back_to_unknown_status_label():
    html = status_badge(SimpleNamespace(status="ABANDONED", kickoff=timezone.now()))

    assert "ABANDONED" in html


def test_score_display_renders_score_when_available():
    html = score_display(SimpleNamespace(home_score=2, away_score=1))

    assert "2 - 1" in html


def test_score_display_renders_vs_when_scores_missing():
    html = score_display(SimpleNamespace(home_score=None, away_score=None))

    assert ">vs<" in html


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "-"),
        ("bad-value", "-"),
        ("2.5", "2.50"),
    ],
)
def test_format_odds_handles_supported_values(value, expected):
    assert format_odds(value) == expected


def test_relative_time_formats_recent_past():
    ts = timezone.now() - timedelta(seconds=32)

    assert relative_time(ts) == "32 seconds ago"


def test_relative_time_formats_iso_timestamp():
    ts = (timezone.now() - timedelta(minutes=3)).isoformat()

    assert relative_time(ts) == "3 minutes ago"


def test_relative_time_formats_future_values():
    ts = timezone.now() + timedelta(minutes=5)

    assert relative_time(ts) == "in 5 minutes"


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=30), "in under a minute"),
        (timedelta(minutes=1), "in 1 minute"),
        (timedelta(hours=1), "in 1 hour"),
        (timedelta(hours=3), "in 3 hours"),
    ],
)
def test_relative_time_formats_future_boundary_values(monkeypatch, delta, expected):
    now = timezone.make_aware(datetime(2026, 3, 12, 12, 0))
    monkeypatch.setattr("matches.templatetags.match_tags.timezone.now", lambda: now)
    ts = now + delta

    assert relative_time(ts) == expected


@pytest.mark.parametrize(
    ("delta_seconds", "expected"),
    [
        (60, "1 minute ago"),
        (3600, "1 hour ago"),
        (7200, "2 hours ago"),
        (86400, "1 day ago"),
        (172800, "2 days ago"),
    ],
)
def test_humanize_delta_formats_boundary_values(delta_seconds, expected):
    assert _humanize_delta(delta_seconds) == expected


def test_coerce_datetime_returns_none_for_invalid_string():
    assert _coerce_datetime("not-a-datetime") is None


def test_coerce_datetime_returns_none_for_unsupported_type():
    assert _coerce_datetime(42) is None


def test_coerce_datetime_makes_naive_datetimes_aware(settings):
    settings.TIME_ZONE = "UTC"
    coerced = _coerce_datetime(datetime(2026, 3, 11, 12, 0))

    assert coerced is not None
    assert timezone.is_aware(coerced)
