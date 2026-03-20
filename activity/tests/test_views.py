import pytest
from django.urls import reverse

from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestToggleToastsView:
    def test_toggles_toasts_on_to_off(self, client):
        user = UserFactory(show_activity_toasts=True)
        client.force_login(user)

        response = client.post(reverse("activity:toggle_toasts"))

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.show_activity_toasts is False

    def test_toggles_toasts_off_to_on(self, client):
        user = UserFactory(show_activity_toasts=False)
        client.force_login(user)

        response = client.post(reverse("activity:toggle_toasts"), {"show_activity_toasts": "on"})

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.show_activity_toasts is True

    def test_idempotent_on(self, client):
        user = UserFactory(show_activity_toasts=True)
        client.force_login(user)

        client.post(reverse("activity:toggle_toasts"), {"show_activity_toasts": "on"})
        client.post(reverse("activity:toggle_toasts"), {"show_activity_toasts": "on"})

        user.refresh_from_db()
        assert user.show_activity_toasts is True

    def test_idempotent_off(self, client):
        user = UserFactory(show_activity_toasts=False)
        client.force_login(user)

        client.post(reverse("activity:toggle_toasts"))
        client.post(reverse("activity:toggle_toasts"))

        user.refresh_from_db()
        assert user.show_activity_toasts is False

    def test_returns_settings_card_partial(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.post(reverse("activity:toggle_toasts"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "activity-settings-card" in content
        assert "Live Activity Feed" in content

    def test_requires_login(self, client):
        url = reverse("activity:toggle_toasts")
        response = client.post(url)
        assert response.status_code == 302
        assert "/login" in response["Location"] or "/accounts/login" in response["Location"]

    def test_get_not_allowed(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse("activity:toggle_toasts"))
        assert response.status_code == 405
