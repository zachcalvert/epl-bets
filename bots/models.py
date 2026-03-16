from decimal import Decimal

from django.db import models

from matches.models import Team
from users.models import User


class HomerBotConfig(models.Model):
    """Configuration for a Homer Bot instance.

    Links a bot user to the team they unconditionally support.
    Multiple Homer bots can coexist, each backing a different club.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="homer_config",
        limit_choices_to={"is_bot": True},
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="homer_bots",
    )
    draw_underdog_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.50"),
        help_text=(
            "Away-win odds at or above this value trigger a DRAW bet instead of AWAY_WIN. "
            "Represents the point at which even a homer accepts a draw is the best realistic outcome."
        ),
    )

    class Meta:
        verbose_name = "Homer Bot config"
        verbose_name_plural = "Homer Bot configs"

    def __str__(self):
        return f"{self.user.display_name} → {self.team.name}"
