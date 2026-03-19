from django.db import models


class ActivityEvent(models.Model):
    class EventType(models.TextChoices):
        BOT_BET = "bot_bet", "Bot Bet"
        BOT_COMMENT = "bot_comment", "Bot Comment"
        BOT_BOARD_POST = "bot_board_post", "Bot Board Post"
        SCORE_CHANGE = "score_change", "Score Change"
        ODDS_UPDATE = "odds_update", "Odds Update"
        BET_SETTLEMENT = "bet_settlement", "Bet Settlement"

    event_type = models.CharField(max_length=20, choices=EventType.choices)
    message = models.CharField(max_length=280)
    url = models.CharField(max_length=200, blank=True, default="")
    icon = models.CharField(max_length=50, default="lightning")
    created_at = models.DateTimeField(auto_now_add=True)
    broadcast_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["broadcast_at", "created_at"],
                name="activity_pending_broadcast_idx",
            ),
        ]

    def __str__(self):
        status = "sent" if self.broadcast_at else "queued"
        return f"[{status}] {self.message}"
