import pytest

from users.tests.factories import UserFactory
from website.forms import LoginForm, SignupForm

pytestmark = pytest.mark.django_db


def test_signup_form_valid():
    form = SignupForm(
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "password_confirm": "password123",
        }
    )

    assert form.is_valid() is True


def test_signup_form_rejects_duplicate_email():
    UserFactory(email="existing@example.com")
    form = SignupForm(
        data={
            "email": "existing@example.com",
            "password": "password123",
            "password_confirm": "password123",
        }
    )

    assert form.is_valid() is False
    assert "email" in form.errors


def test_signup_form_rejects_password_mismatch():
    form = SignupForm(
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "password_confirm": "different123",
        }
    )

    assert form.is_valid() is False
    assert "password_confirm" in form.errors


def test_signup_form_rejects_short_password():
    form = SignupForm(
        data={
            "email": "newuser@example.com",
            "password": "short",
            "password_confirm": "short",
        }
    )

    assert form.is_valid() is False
    assert "password" in form.errors


def test_login_form_valid():
    form = LoginForm(
        data={
            "email": "bettor@example.com",
            "password": "password123",
        }
    )

    assert form.is_valid() is True


def test_login_form_missing_fields():
    form = LoginForm(data={})

    assert form.is_valid() is False
    assert "email" in form.errors
    assert "password" in form.errors
