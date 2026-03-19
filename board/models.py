from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class PostType(models.TextChoices):
    RESULTS_TABLE = "results_table", _("Results & Table")
    PREDICTION = "prediction", _("Prediction")
    META = "meta", _("Meta")


class BoardPost(BaseModel):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="board_posts",
        verbose_name=_("author"),
    )
    post_type = models.CharField(
        _("post type"),
        max_length=20,
        choices=PostType.choices,
    )
    body = models.TextField(_("body"), max_length=2000)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("parent post"),
    )
    is_hidden = models.BooleanField(_("hidden"), default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["post_type", "created_at"]),
            models.Index(fields=["parent"]),
            models.Index(fields=["author", "created_at"]),
        ]

    def __str__(self):
        return f"{self.author} — {self.get_post_type_display()} ({self.id_hash})"
