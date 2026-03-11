import pytest

from users.tests.factories import UserFactory


@pytest.mark.django_db
def test_create_user_with_email(django_user_model):
    user = django_user_model.objects.create_user(
        email="bettor@example.com",
        password="password123",
    )

    assert user.email == "bettor@example.com"
    assert user.check_password("password123")
    assert user.is_staff is False
    assert user.is_superuser is False


def test_create_user_no_email_raises(django_user_model):
    with pytest.raises(ValueError, match="The Email field must be set"):
        django_user_model.objects.create_user(email="", password="password123")


@pytest.mark.django_db
def test_create_user_normalizes_email(django_user_model):
    user = django_user_model.objects.create_user(
        email="Bettor@EXAMPLE.COM",
        password="password123",
    )

    assert user.email == "Bettor@example.com"


@pytest.mark.django_db
def test_create_superuser(django_user_model):
    user = django_user_model.objects.create_superuser(
        email="admin@example.com",
        password="password123",
    )

    assert user.is_staff is True
    assert user.is_superuser is True


def test_create_superuser_not_staff_raises(django_user_model):
    with pytest.raises(ValueError, match="Superuser must have is_staff=True."):
        django_user_model.objects.create_superuser(
            email="admin@example.com",
            password="password123",
            is_staff=False,
        )


def test_create_superuser_not_superuser_raises(django_user_model):
    with pytest.raises(ValueError, match="Superuser must have is_superuser=True."):
        django_user_model.objects.create_superuser(
            email="admin@example.com",
            password="password123",
            is_superuser=False,
        )


@pytest.mark.django_db
def test_user_str():
    user = UserFactory(email="bettor@example.com")

    assert str(user) == "bettor@example.com"


def test_user_username_field(django_user_model):
    assert django_user_model.USERNAME_FIELD == "email"

