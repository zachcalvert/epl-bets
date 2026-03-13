import logging
from decimal import Decimal

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

    bet_count_rules = []
    stake_rules = []
    for rule in active_rules:
        if rule.rule_type == RewardRule.RuleType.BET_COUNT:
            bet_count_rules.append(rule)
        elif rule.rule_type == RewardRule.RuleType.STAKE_AMOUNT:
            stake_rules.append(rule)

    if bet_count_rules:
        bet_count = BetSlip.objects.filter(user=instance.user).count()
        for rule in bet_count_rules:
            if bet_count == int(rule.threshold):
                rule.reward.distribute_to_users([instance.user])

    stake = Decimal(str(instance.stake))
    for rule in stake_rules:
        if stake >= rule.threshold:
            rule.reward.distribute_to_users([instance.user])
