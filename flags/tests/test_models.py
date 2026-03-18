import pytest

from flags.tests.factories import FeatureFlagFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# FeatureFlag.__str__
# ---------------------------------------------------------------------------


def test_feature_flag_str_returns_name():
    flag = FeatureFlagFactory(name="test-flag")
    assert str(flag) == "test-flag"


# ---------------------------------------------------------------------------
# FeatureFlag.is_enabled – global switch
# ---------------------------------------------------------------------------


def test_is_enabled_returns_true_when_enabled_for_all():
    flag = FeatureFlagFactory(is_enabled_for_all=True)
    user = UserFactory()
    assert flag.is_enabled(user=user) is True


def test_is_enabled_returns_true_for_all_when_no_user_provided():
    flag = FeatureFlagFactory(is_enabled_for_all=True)
    assert flag.is_enabled() is True


def test_is_enabled_returns_false_when_disabled_globally_and_no_user():
    flag = FeatureFlagFactory(is_enabled_for_all=False)
    assert flag.is_enabled() is False


# ---------------------------------------------------------------------------
# FeatureFlag.is_enabled – per-user
# ---------------------------------------------------------------------------


def test_is_enabled_returns_true_for_explicitly_enabled_user():
    flag = FeatureFlagFactory(is_enabled_for_all=False)
    user = UserFactory()
    flag.users.add(user)
    assert flag.is_enabled(user=user) is True


def test_is_enabled_returns_false_for_user_not_in_list():
    flag = FeatureFlagFactory(is_enabled_for_all=False)
    user = UserFactory()
    assert flag.is_enabled(user=user) is False


def test_is_enabled_returns_false_when_no_user_and_not_enabled_for_all():
    flag = FeatureFlagFactory(is_enabled_for_all=False)
    assert flag.is_enabled(user=None) is False


# ---------------------------------------------------------------------------
# FeatureFlag ordering
# ---------------------------------------------------------------------------


def test_feature_flags_are_ordered_by_name():
    FeatureFlagFactory(name="z-flag")
    FeatureFlagFactory(name="a-flag")
    FeatureFlagFactory(name="m-flag")

    from flags.models import FeatureFlag

    names = list(FeatureFlag.objects.values_list("name", flat=True))
    assert names == sorted(names)
