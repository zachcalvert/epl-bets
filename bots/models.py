from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
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


class BotComment(BaseModel):
    """Tracks bot-generated comments for dedup and debugging."""

    class TriggerType(models.TextChoices):
        PRE_MATCH = "PRE_MATCH", _("Pre-match hype")
        POST_BET = "POST_BET", _("Post-bet reaction")
        POST_MATCH = "POST_MATCH", _("Post-match reaction")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bot_comments",
        limit_choices_to={"is_bot": True},
        verbose_name=_("bot user"),
    )
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="bot_comments",
        verbose_name=_("match"),
    )
    comment = models.OneToOneField(
        "discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_comment_meta",
        verbose_name=_("posted comment"),
    )
    trigger_type = models.CharField(
        _("trigger type"),
        max_length=20,
        choices=TriggerType.choices,
    )
    prompt_used = models.TextField(_("prompt used"), blank=True)
    raw_response = models.TextField(_("raw response"), blank=True)
    filtered = models.BooleanField(
        _("filtered out"),
        default=False,
        help_text=_("True if the post-hoc filter rejected this comment."),
    )
    error = models.TextField(_("error"), blank=True)

    class Meta:
        verbose_name = _("bot comment")
        verbose_name_plural = _("bot comments")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "match", "trigger_type"],
                name="unique_bot_comment_per_trigger",
            ),
        ]
        indexes = [
            models.Index(fields=["match", "trigger_type"]),
        ]

    def __str__(self):
        return f"{self.user.display_name} | {self.trigger_type} | {self.match}"
