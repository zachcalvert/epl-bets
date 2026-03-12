import pytest
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from users.serializers import RegisterSerializer
from users.tests.factories import UserFactory
from users.views import MeView

pytestmark = pytest.mark.django_db


def test_register_serializer_create_uses_create_user(monkeypatch):
    called = {}

    def fake_create_user(**kwargs):
        called.update(kwargs)
        return object()

    monkeypatch.setattr("users.serializers.User.objects.create_user", fake_create_user)

    serializer = RegisterSerializer()
    result = serializer.create(
        {
            "email": "new@example.com",
            "password": "password123",
            "display_name": "New User",
            "first_name": "New",
            "last_name": "User",
        }
    )

    assert result is not None
    assert called["email"] == "new@example.com"
    assert called["password"] == "password123"


def test_register_api_creates_user(client):
    response = client.post(
        reverse("users:register"),
        data={
            "email": "apiuser@example.com",
            "password": "password123",
            "display_name": "API User",
            "first_name": "Api",
            "last_name": "User",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["email"] == "apiuser@example.com"


def test_me_view_get_object_returns_authenticated_user():
    user = UserFactory()
    request = APIRequestFactory().get(reverse("users:me"))
    request.user = user

    view = MeView()
    view.request = request

    assert view.get_object() == user


def test_me_api_returns_authenticated_user():
    user = UserFactory(
        email="me@example.com",
        display_name="Original Name",
        first_name="First",
        last_name="Last",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(reverse("users:me"))

    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_me_api_updates_authenticated_user():
    user = UserFactory(
        email="me@example.com",
        display_name="Original Name",
        first_name="First",
        last_name="Last",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.patch(
        reverse("users:me"),
        data={"display_name": "Updated Name"},
        format="json",
    )

    user.refresh_from_db()

    assert response.status_code == 200
    assert response.json()["display_name"] == "Updated Name"
    assert user.display_name == "Updated Name"
