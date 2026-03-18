from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class Comment(BaseModel):
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("match"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("user"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("parent comment"),
    )
    body = models.TextField(_("body"), max_length=1000)
    is_deleted = models.BooleanField(_("deleted"), default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["match", "created_at"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.user} on {self.match} ({self.id_hash})"
