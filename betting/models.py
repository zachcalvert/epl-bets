from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class Odds(BaseModel):
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="odds",
        verbose_name=_("match"),
    )
    bookmaker = models.CharField(_("bookmaker"), max_length=100)
    home_win = models.DecimalField(_("home win"), max_digits=6, decimal_places=2)
    draw = models.DecimalField(_("draw"), max_digits=6, decimal_places=2)
    away_win = models.DecimalField(_("away win"), max_digits=6, decimal_places=2)
    fetched_at = models.DateTimeField(_("fetched at"))

    class Meta:
        ordering = ["-fetched_at"]
        unique_together = [("match", "bookmaker")]
        verbose_name_plural = "odds"

    def __str__(self):
        return f"{self.bookmaker}: {self.match} ({self.home_win}/{self.draw}/{self.away_win})"


class BetSlip(BaseModel):
    class Selection(models.TextChoices):
        HOME_WIN = "HOME_WIN", _("Home Win")
        DRAW = "DRAW", _("Draw")
        AWAY_WIN = "AWAY_WIN", _("Away Win")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        WON = "WON", _("Won")
        LOST = "LOST", _("Lost")
        VOID = "VOID", _("Void")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("user"),
    )
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("match"),
    )
    selection = models.CharField(
        _("selection"),
        max_length=10,
        choices=Selection.choices,
    )
    odds_at_placement = models.DecimalField(
        _("odds at placement"), max_digits=6, decimal_places=2
    )
    stake = models.DecimalField(_("stake"), max_digits=10, decimal_places=2)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    payout = models.DecimalField(
        _("payout"), max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.get_selection_display()} on {self.match} @ {self.odds_at_placement}"


class UserBalance(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance",
        verbose_name=_("user"),
    )
    balance = models.DecimalField(
        _("balance"), max_digits=10, decimal_places=2, default=1000.00
    )

    def __str__(self):
        return f"{self.user}: {self.balance} credits"
