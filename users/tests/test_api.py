import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from users.serializers import RegisterSerializer
from users.tests.factories import UserFactory
from users.views import MeView
from website.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_register_serializer_create_uses_create_user():
    SiteSettings.load()

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
    assert result.email == "new@example.com"


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


def test_register_api_blocked_when_cap_reached(client):
    site = SiteSettings.load()
    site.max_users = 1
    site.save()
    UserFactory()

    response = client.post(
        reverse("users:register"),
        data={
            "email": "capped@example.com",
            "password": "password123",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not get_user_model().objects.filter(email="capped@example.com").exists()


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
