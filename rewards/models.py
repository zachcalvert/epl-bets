from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from betting.models import UserBalance
from core.models import BaseModel


class Reward(BaseModel):
    name = models.CharField(_("name"), max_length=200)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    description = models.TextField(_("description"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_rewards",
        verbose_name=_("created by"),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.amount} credits)"

    def distribute_to_users(self, users):
        """Credit this reward to the given users atomically.

        Creates RewardDistribution records and increments each user's balance.
        Skips users who have already received this reward.
        Returns the list of newly created distributions.
        """
        new_distributions = []

        with transaction.atomic():
            existing = set(
                self.distributions.filter(user__in=users).values_list("user_id", flat=True)
            )
            for user in users:
                if user.pk in existing:
                    continue

                dist = RewardDistribution.objects.create(reward=self, user=user)
                new_distributions.append(dist)

                balance, _ = UserBalance.objects.get_or_create(
                    user=user, defaults={"balance": Decimal("1000.00")}
                )
                UserBalance.objects.filter(pk=balance.pk).update(
                    balance=models.F("balance") + self.amount
                )

        return new_distributions


class RewardDistribution(BaseModel):
    reward = models.ForeignKey(
        Reward,
        on_delete=models.CASCADE,
        related_name="distributions",
        verbose_name=_("reward"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reward_distributions",
        verbose_name=_("user"),
    )
    seen = models.BooleanField(_("seen"), default=False)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("reward", "user")]

    def __str__(self):
        return f"{self.reward.name} → {self.user}"
