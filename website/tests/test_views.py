from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import UserBalance
from betting.tests.factories import UserBalanceFactory
from users.tests.factories import UserFactory
from website.models import SiteSettings
from website.views import ARCHITECTURE_COMPONENTS, FLOW_PATHS


@pytest.mark.django_db
def test_signup_get_renders_form(client):
    response = client.get(reverse("website:signup"))

    assert response.status_code == 200
    assert any(template.name == "website/signup.html" for template in response.templates)


@pytest.mark.django_db
def test_signup_get_redirects_authenticated_user(client):
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("website:signup"))

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")


@pytest.mark.django_db
def test_signup_post_creates_user_balance_and_logs_user_in(client, django_user_model):
    response = client.post(
        reverse("website:signup"),
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )

    user = django_user_model.objects.get(email="newuser@example.com")

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")
    assert UserBalance.objects.filter(user=user).exists() is True
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_signup_post_returns_errors_for_duplicate_email(client):
    UserFactory(email="existing@example.com")

    response = client.post(
        reverse("website:signup"),
        data={
            "email": "existing@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )

    assert response.status_code == 200
    assert any(template.name == "website/signup.html" for template in response.templates)
    assert "An account with this email already exists." in response.content.decode()


@pytest.mark.django_db
def test_signup_post_returns_errors_for_password_mismatch(client):
    response = client.post(
        reverse("website:signup"),
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "password_confirm": "different123",
        },
    )

    assert response.status_code == 200
    assert "Passwords do not match." in response.content.decode()


@pytest.mark.django_db
def test_signup_get_shows_closed_when_cap_reached(client):
    site = SiteSettings.load()
    site.max_users = 1
    site.save()
    UserFactory()

    response = client.get(reverse("website:signup"))

    assert response.status_code == 200
    assert response.context["registration_closed"] is True
    assert response.context["closed_message"] == site.registration_closed_message


@pytest.mark.django_db
def test_signup_post_blocked_when_cap_reached(client, django_user_model):
    site = SiteSettings.load()
    site.max_users = 1
    site.save()
    UserFactory()

    response = client.post(
        reverse("website:signup"),
        data={
            "email": "new@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )

    assert response.status_code == 200
    assert response.context["registration_closed"] is True
    assert not django_user_model.objects.filter(email="new@example.com").exists()


@pytest.mark.django_db
def test_signup_allowed_when_max_users_is_zero(client, django_user_model):
    site = SiteSettings.load()
    site.max_users = 0
    site.save()
    UserFactory()

    response = client.post(
        reverse("website:signup"),
        data={
            "email": "unlimited@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )

    assert response.status_code == 302
    assert django_user_model.objects.filter(email="unlimited@example.com").exists()


@pytest.mark.django_db
def test_login_get_renders_form(client):
    response = client.get(reverse("website:login"))

    assert response.status_code == 200
    assert any(template.name == "website/login.html" for template in response.templates)


@pytest.mark.django_db
def test_login_get_redirects_authenticated_user(client):
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("website:login"))

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")


@pytest.mark.django_db
def test_login_post_authenticates_user(client):
    user = UserFactory(email="bettor@example.com")

    response = client.post(
        reverse("website:login"),
        data={
            "email": user.email,
            "password": "password123",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_login_post_redirects_to_next_path(client):
    user = UserFactory(email="bettor@example.com")

    response = client.post(
        f"{reverse('website:login')}?next=/fixtures/",
        data={
            "email": user.email,
            "password": "password123",
        },
    )

    assert response.status_code == 302
    assert response.url == "/fixtures/"


@pytest.mark.django_db
def test_login_post_shows_error_for_invalid_credentials(client):
    UserFactory(email="bettor@example.com")

    response = client.post(
        reverse("website:login"),
        data={
            "email": "bettor@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 200
    assert "Invalid email or password." in response.content.decode()


@pytest.mark.django_db
def test_logout_post_logs_user_out(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("website:logout"))

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")
    assert "_auth_user_id" not in client.session


def test_how_it_works_view_renders_context(client):
    response = client.get(reverse("website:how_it_works"))

    assert response.status_code == 200
    assert any(template.name == "website/how_it_works.html" for template in response.templates)
    assert response.context["components"] == ARCHITECTURE_COMPONENTS
    assert response.context["flows"] == FLOW_PATHS


def test_component_detail_returns_partial(client):
    response = client.get(
        reverse("website:component_detail"),
        data={"name": "browser"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "website/partials/component_detail.html"
        for template in response.templates
    )
    assert "Django Templates" in response.content.decode()


def test_component_detail_raises_404_for_invalid_component(client):
    response = client.get(
        reverse("website:component_detail"),
        data={"name": "unknown"},
    )

    assert response.status_code == 404


def test_component_detail_raises_404_when_name_missing(client):
    response = client.get(reverse("website:component_detail"))

    assert response.status_code == 404


def test_theme_context_defaults_to_dark_mode(client):
    response = client.get(reverse("website:login"))

    assert response.status_code == 200
    assert response.context["ui_theme_name"] == "dark"
    assert response.context["ui_theme_toggle_value"] == "light"


@pytest.mark.django_db
def test_theme_toggle_persists_preference_in_session(client):
    response = client.post(
        reverse("website:theme_toggle"),
        data={"theme": "light", "next": reverse("website:login")},
    )

    assert response.status_code == 302
    assert response.url == reverse("website:login")
    assert client.session["theme_preference"] == "light"

    follow_up = client.get(reverse("website:login"))
    assert follow_up.context["ui_theme_name"] == "light"
    assert follow_up.context["ui_theme_toggle_value"] == "dark"


@pytest.mark.django_db
def test_theme_toggle_rejects_external_redirects(client):
    response = client.post(
        reverse("website:theme_toggle"),
        data={"theme": "light", "next": "https://example.com/phish"},
    )

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")


@pytest.mark.django_db
def test_theme_toggle_without_theme_param_toggles_current_theme(client):
    session = client.session
    session["theme_preference"] = "dark"
    session.save()

    response = client.post(
        reverse("website:theme_toggle"),
        data={"next": reverse("website:login")},
    )

    assert response.status_code == 302
    assert response.url == reverse("website:login")
    assert client.session["theme_preference"] == "light"


@pytest.mark.django_db
def test_theme_toggle_uses_referrer_when_next_is_missing(client):
    response = client.post(
        reverse("website:theme_toggle"),
        data={"theme": "light"},
        HTTP_REFERER="http://testserver/how-it-works/",
    )

    assert response.status_code == 302
    assert response.url == "http://testserver/how-it-works/"


@pytest.mark.django_db
def test_theme_toggle_falls_back_when_referrer_is_missing(client):
    response = client.post(
        reverse("website:theme_toggle"),
        data={"theme": "light"},
    )

    assert response.status_code == 302
    assert response.url == reverse("matches:dashboard")


# --- AccountView tests ---


@pytest.mark.django_db
def test_account_view_redirects_anonymous_user(client):
    response = client.get(reverse("website:account"))

    assert response.status_code == 302
    assert reverse("website:login") in response.url


@pytest.mark.django_db
def test_account_view_renders_for_authenticated_user(client):
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("website:account"))

    assert response.status_code == 200
    assert any(template.name == "website/account.html" for template in response.templates)


@pytest.mark.django_db
def test_account_view_shows_display_name_form_with_current_value(client):
    user = UserFactory(email="bettor@example.com", display_name="Top Punter")
    client.force_login(user)

    response = client.get(reverse("website:account"))

    assert response.status_code == 200
    assert "Public display name" in response.content.decode()
    assert "Top Punter" in response.content.decode()


@pytest.mark.django_db
def test_account_view_shows_rank_summary_when_user_has_balance(client):
    for index in range(10):
        UserBalanceFactory(
            user__email=f"leader{index}@example.com",
            balance=Decimal("2000.00") - Decimal(index),
        )
    user = UserFactory(email="climber@example.com")
    UserBalanceFactory(user=user, balance="1500.00")
    client.force_login(user)

    response = client.get(reverse("website:account"))

    assert response.status_code == 200
    assert response.context["user_rank"].rank == 11
    assert "Your leaderboard rank" in response.content.decode()
    assert "You are currently #11" in response.content.decode()
    assert "cl*****@example.com" in response.content.decode()


@pytest.mark.django_db
def test_account_view_rank_summary_prefers_display_name(client):
    user = UserFactory(email="winner@example.com", display_name="League Leader")
    UserBalanceFactory(user=user, balance="2500.00")
    client.force_login(user)

    response = client.get(reverse("website:account"))

    assert response.status_code == 200
    assert response.context["user_rank"].display_identity == "League Leader"
    assert "League Leader" in response.content.decode()


@pytest.mark.django_db
def test_account_view_updates_display_name_via_htmx(client):
    user = UserFactory(email="bettor@example.com")
    client.force_login(user)

    response = client.post(
        reverse("website:account"),
        data={"display_name": "Top Punter"},
        HTTP_HX_REQUEST="true",
    )

    user.refresh_from_db()

    assert response.status_code == 200
    assert user.display_name == "Top Punter"
    assert "Display name updated." in response.content.decode()
    assert any(
        template.name == "website/partials/account_settings_card.html"
        for template in response.templates
    )


@pytest.mark.django_db
def test_account_view_shows_duplicate_display_name_error_and_allows_retry(client):
    UserFactory(display_name="Top Punter")
    user = UserFactory(email="bettor@example.com")
    client.force_login(user)

    response = client.post(
        reverse("website:account"),
        data={"display_name": "top punter"},
        HTTP_HX_REQUEST="true",
    )

    user.refresh_from_db()

    assert response.status_code == 422
    assert user.display_name in (None, "")
    assert "Display name already taken." in response.content.decode()
    assert 'value="top punter"' in response.content.decode()


@pytest.mark.django_db
def test_account_view_allows_clearing_display_name(client):
    user = UserFactory(email="bettor@example.com", display_name="Top Punter")
    client.force_login(user)

    response = client.post(
        reverse("website:account"),
        data={"display_name": "   "},
        HTTP_HX_REQUEST="true",
    )

    user.refresh_from_db()

    assert response.status_code == 200
    assert user.display_name is None
    assert "be****@example.com" in response.content.decode()


@pytest.mark.django_db
def test_account_view_post_full_page_on_success_without_htmx(client):
    user = UserFactory(email="bettor@example.com")
    client.force_login(user)

    response = client.post(
        reverse("website:account"),
        data={"display_name": "New Name"},
    )

    user.refresh_from_db()

    assert response.status_code == 200
    assert user.display_name == "New Name"
    assert any(template.name == "website/account.html" for template in response.templates)


@pytest.mark.django_db
def test_account_view_post_full_page_on_error_without_htmx(client):
    UserFactory(display_name="Taken Name")
    user = UserFactory(email="bettor@example.com")
    client.force_login(user)

    response = client.post(
        reverse("website:account"),
        data={"display_name": "taken name"},
    )

    assert response.status_code == 422
    assert any(template.name == "website/account.html" for template in response.templates)
    assert "Display name already taken." in response.content.decode()
