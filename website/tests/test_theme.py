from django.test import RequestFactory

from website.theme import DEFAULT_THEME, get_theme, get_toggle_theme, normalize_theme


def test_normalize_theme_falls_back_for_invalid_values():
    assert normalize_theme("sepia") == DEFAULT_THEME


def test_get_theme_reads_valid_session_value():
    request = RequestFactory().get("/")
    request.session = {"theme_preference": "light"}

    assert get_theme(request) == "light"


def test_get_toggle_theme_returns_dark_when_current_theme_is_light():
    request = RequestFactory().get("/")
    request.session = {"theme_preference": "light"}

    assert get_toggle_theme(request) == "dark"
