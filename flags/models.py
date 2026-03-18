from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class FeatureFlag(BaseModel):
    """A named flag used to gate experimental or trial functionality.

    A flag can be enabled globally (is_enabled_for_all=True) or restricted to
    specific users via the ``users`` many-to-many relationship.
    """

    name = models.SlugField(
        _("name"),
        max_length=100,
        unique=True,
        help_text=_("Unique slug identifier used in code (e.g. 'enhanced-match-stats')."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=_("Human-readable explanation of what this flag controls."),
    )
    is_enabled_for_all = models.BooleanField(
        _("enabled for all users"),
        default=False,
        help_text=_("When checked, this flag is active for every user regardless of the user list below."),
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="feature_flags",
        verbose_name=_("enabled for users"),
        help_text=_("Individual users for whom this flag is explicitly enabled."),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("feature flag")
        verbose_name_plural = _("feature flags")

    def __str__(self):
        return self.name

    def is_enabled(self, user=None):
        """Return True if this flag is active for *user*.

        If *user* is None only the global ``is_enabled_for_all`` switch is
        considered.
        """
        if self.is_enabled_for_all:
            return True
        if user is not None:
            return self.users.filter(pk=user.pk).exists()
        return False
