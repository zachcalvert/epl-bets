from datetime import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone

from matches.templatetags.match_tags import format_odds, score_display, status_badge


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
