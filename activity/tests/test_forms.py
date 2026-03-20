import pytest

from activity.forms import ActivityPreferencesForm
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestActivityPreferencesForm:
    def test_valid_with_show_true(self):
        user = UserFactory(show_activity_toasts=False)
        form = ActivityPreferencesForm({"show_activity_toasts": True}, instance=user)
        assert form.is_valid()

    def test_valid_with_show_false(self):
        user = UserFactory(show_activity_toasts=True)
        form = ActivityPreferencesForm({}, instance=user)
        assert form.is_valid()

    def test_only_exposes_toast_field(self):
        form = ActivityPreferencesForm()
        assert list(form.fields.keys()) == ["show_activity_toasts"]

    def test_save_updates_user(self):
        user = UserFactory(show_activity_toasts=True)
        form = ActivityPreferencesForm({"show_activity_toasts": False}, instance=user)
        assert form.is_valid()
        form.save()
        user.refresh_from_db()
        assert user.show_activity_toasts is False
