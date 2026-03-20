from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class BotProfile(BaseModel):
    """Database-backed bot identity — persona prompt, strategy type, and cosmetics.

    Each bot User gets one BotProfile. The persona_prompt field is the system
    prompt sent to the LLM and is editable via the Django admin.
    """

    class StrategyType(models.TextChoices):
        FRONTRUNNER = "frontrunner", _("Frontrunner")
        UNDERDOG = "underdog", _("Underdog")
        PARLAY = "parlay", _("Parlay")
        DRAW_SPECIALIST = "draw_specialist", _("Draw Specialist")
        VALUE_HUNTER = "value_hunter", _("Value Hunter")
        CHAOS_AGENT = "chaos_agent", _("Chaos Agent")
        ALL_IN_ALICE = "all_in_alice", _("All-In Alice")
        HOMER = "homer", _("Homer (team-loyal)")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bot_profile",
        limit_choices_to={"is_bot": True},
        verbose_name=_("bot user"),
    )
    strategy_type = models.CharField(
        _("strategy type"),
        max_length=30,
        choices=StrategyType.choices,
    )
    team_tla = models.CharField(
        _("team TLA"),
        max_length=5,
        blank=True,
        help_text=_("Only for homer bots. Must match a Team.tla value."),
    )
    persona_prompt = models.TextField(
        _("persona prompt"),
        help_text=_("Full system prompt sent to the LLM. Edit to tweak personality and voice."),
    )
    avatar_icon = models.CharField(
        _("avatar icon"),
        max_length=30,
        default="robot",
        help_text=_("Lucide icon name."),
    )
    avatar_bg = models.CharField(
        _("avatar background"),
        max_length=10,
        default="#374151",
        help_text=_("Hex colour for the avatar background."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive bots are skipped by all tasks."),
    )

    class Meta:
        verbose_name = _("bot profile")
        verbose_name_plural = _("bot profiles")

    def __str__(self):
        return f"{self.user.display_name} ({self.get_strategy_type_display()})"


class BotComment(BaseModel):
    """Tracks bot-generated comments for dedup and debugging."""

    class TriggerType(models.TextChoices):
        PRE_MATCH = "PRE_MATCH", _("Pre-match hype")
        POST_BET = "POST_BET", _("Post-bet reaction")
        POST_MATCH = "POST_MATCH", _("Post-match reaction")
        REPLY = "REPLY", _("Reply to comment")

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
    parent_comment = models.ForeignKey(
        "discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_replies",
        verbose_name=_("replied to"),
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
