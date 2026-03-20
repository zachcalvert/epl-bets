from unittest.mock import Mock

import pytest

from activity.context_processors import activity_toasts
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestActivityToastsContextProcessor:
    def test_returns_true_for_anonymous_user(self):
        request = Mock()
        request.user = Mock(is_authenticated=False)

        ctx = activity_toasts(request)

        assert ctx == {"show_activity_toasts": True}

    def test_returns_true_for_opted_in_user(self):
        user = UserFactory(show_activity_toasts=True)
        request = Mock()
        request.user = user

        ctx = activity_toasts(request)

        assert ctx == {"show_activity_toasts": True}

    def test_returns_false_for_opted_out_user(self):
        user = UserFactory(show_activity_toasts=False)
        request = Mock()
        request.user = user

        ctx = activity_toasts(request)

        assert ctx == {"show_activity_toasts": False}

    def test_returns_true_when_no_user_on_request(self):
        request = Mock(spec=[])  # no .user attribute

        ctx = activity_toasts(request)

        assert ctx == {"show_activity_toasts": True}
