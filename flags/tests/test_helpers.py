import pytest

from flags.helpers import is_flag_enabled
from flags.tests.factories import FeatureFlagFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_is_flag_enabled_returns_false_for_missing_flag():
    assert is_flag_enabled("non-existent-flag") is False


def test_is_flag_enabled_returns_false_for_missing_flag_with_user():
    user = UserFactory()
    assert is_flag_enabled("non-existent-flag", user=user) is False


def test_is_flag_enabled_returns_true_when_enabled_for_all():
    FeatureFlagFactory(name="my-flag", is_enabled_for_all=True)
    assert is_flag_enabled("my-flag") is True


def test_is_flag_enabled_returns_true_for_specific_user():
    flag = FeatureFlagFactory(name="per-user-flag", is_enabled_for_all=False)
    user = UserFactory()
    flag.users.add(user)
    assert is_flag_enabled("per-user-flag", user=user) is True


def test_is_flag_enabled_returns_false_for_other_user():
    flag = FeatureFlagFactory(name="selective-flag", is_enabled_for_all=False)
    enabled_user = UserFactory()
    other_user = UserFactory()
    flag.users.add(enabled_user)
    assert is_flag_enabled("selective-flag", user=other_user) is False


def test_is_flag_enabled_returns_false_when_disabled_globally_and_no_user():
    FeatureFlagFactory(name="off-flag", is_enabled_for_all=False)
    assert is_flag_enabled("off-flag") is False
