import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from betting.models import BetSlip

logger = logging.getLogger(__name__)


@receiver(post_save, sender=BetSlip)
def check_reward_rules(sender, instance, created, **kwargs):
    """Evaluate active reward rules whenever a new bet is placed."""
    if not created:
        return

    from rewards.models import RewardRule

    active_rules = RewardRule.objects.filter(is_active=True).select_related("reward")

    for rule in active_rules:
        if rule.rule_type == RewardRule.RuleType.BET_COUNT:
            _check_bet_count_rule(rule, instance.user)
        elif rule.rule_type == RewardRule.RuleType.STAKE_AMOUNT:
            _check_stake_amount_rule(rule, instance)


def _check_bet_count_rule(rule, user):
    """Distribute reward if user just hit the bet count milestone."""
    bet_count = BetSlip.objects.filter(user=user).count()
    if bet_count == int(rule.threshold):
        rule.reward.distribute_to_users([user])


def _check_stake_amount_rule(rule, bet):
    """Distribute reward if this bet's stake meets the threshold."""
    if bet.stake >= rule.threshold:
        rule.reward.distribute_to_users([bet.user])
