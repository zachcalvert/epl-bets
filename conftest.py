import pytest
import respx
from django.core.cache import cache


@pytest.fixture(autouse=True)
def configure_test_settings(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "phase-7-tests",
        }
    }
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.FOOTBALL_DATA_API_KEY = "test-football-data-key"
    settings.ODDS_API_KEY = "test-odds-key"
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


@pytest.fixture(autouse=True)
def clear_cache_between_tests(configure_test_settings):
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _block_outbound_requests():
    """Block all outbound HTTP requests in tests.

    Any test that needs to mock an HTTP call should use respx or
    unittest.mock to patch the client. If an unmocked call slips
    through, this fixture will raise instead of hitting the network.
    """
    with respx.mock(assert_all_called=False) as _mock:
        yield
