from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from betting.models import UserBalance
from betting.tests.factories import BetSlipFactory, UserBalanceFactory
from rewards.models import RewardDistribution, RewardRule
from rewards.tests.factories import RewardFactory, RewardRuleFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestBetCountRule:
    def test_first_bet_triggers_reward(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        rule = RewardRuleFactory(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="1.00",
        )

        BetSlipFactory(user=user)

        assert RewardDistribution.objects.filter(
            reward=rule.reward, user=user
        ).exists()

    def test_milestone_triggers_at_exact_count(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        rule = RewardRuleFactory(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="3.00",
        )

        BetSlipFactory(user=user)
        BetSlipFactory(user=user)
        assert not RewardDistribution.objects.filter(
            reward=rule.reward, user=user
        ).exists()

        BetSlipFactory(user=user)
        assert RewardDistribution.objects.filter(
            reward=rule.reward, user=user
        ).exists()

    def test_no_duplicate_reward_on_subsequent_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="1.00",
        )

        BetSlipFactory(user=user)
        BetSlipFactory(user=user)

        assert RewardDistribution.objects.filter(user=user).count() == 1

    def test_inactive_rule_does_not_trigger(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="1.00",
            is_active=False,
        )

        BetSlipFactory(user=user)

        assert RewardDistribution.objects.filter(user=user).count() == 0

    def test_different_users_tracked_independently(self):
        user1 = UserFactory()
        user2 = UserFactory()
        UserBalanceFactory(user=user1)
        UserBalanceFactory(user=user2)
        rule = RewardRuleFactory(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="2.00",
        )

        BetSlipFactory(user=user1)
        BetSlipFactory(user=user2)
        BetSlipFactory(user=user1)

        assert RewardDistribution.objects.filter(
            reward=rule.reward, user=user1
        ).exists()
        assert not RewardDistribution.objects.filter(
            reward=rule.reward, user=user2
        ).exists()


class TestStakeAmountRule:
    def test_stake_at_threshold_triggers_reward(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        rule = RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="100.00",
        )

        BetSlipFactory(user=user, stake="100.00")

        assert RewardDistribution.objects.filter(
            reward=rule.reward, user=user
        ).exists()

    def test_stake_above_threshold_triggers_reward(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        rule = RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="200.00",
        )

        BetSlipFactory(user=user, stake="250.00")

        assert RewardDistribution.objects.filter(
            reward=rule.reward, user=user
        ).exists()

    def test_stake_below_threshold_does_not_trigger(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="300.00",
        )

        BetSlipFactory(user=user, stake="99.99")

        assert RewardDistribution.objects.filter(user=user).count() == 0

    def test_no_duplicate_reward_on_second_qualifying_bet(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="50.00",
        )

        BetSlipFactory(user=user, stake="200.00")
        BetSlipFactory(user=user, stake="200.00")

        assert RewardDistribution.objects.filter(user=user).count() == 1

    def test_inactive_stake_rule_does_not_trigger(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="75.00",
            is_active=False,
        )

        BetSlipFactory(user=user, stake="500.00")

        assert RewardDistribution.objects.filter(user=user).count() == 0

    def test_reward_credits_user_balance(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="1000.00")
        RewardRuleFactory(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="25.00",
            reward=RewardFactory(amount="25.00"),
        )

        BetSlipFactory(user=user, stake="75.00")

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("1025.00")


class TestRewardRuleValidation:
    def test_bet_count_rejects_non_integer_threshold(self):
        rule = RewardRuleFactory.build(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="10.50",
        )
        with pytest.raises(ValidationError, match="whole numbers"):
            rule.clean()

    def test_bet_count_accepts_integer_threshold(self):
        rule = RewardRuleFactory.build(
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold="10.00",
        )
        rule.clean()

    def test_stake_amount_allows_decimal_threshold(self):
        rule = RewardRuleFactory.build(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold="99.99",
        )
        rule.clean()
