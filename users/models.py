from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.text import slugify

from core.models import generate_short_id

from .managers import UserManager


class Currency(models.TextChoices):
    USD = "USD", "US Dollars ($)"
    GBP = "GBP", "UK Pounds (£)"
    EUR = "EUR", "Euros (€)"


class User(AbstractUser):
    username = None
    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=50, null=True, blank=True)
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.GBP,
    )
    is_bot = models.BooleanField(
        default=False,
        help_text="Designates bot/automated accounts.",
    )
    avatar_icon = models.CharField(max_length=50, default="user-circle")
    avatar_bg = models.CharField(max_length=7, default="#374151")
    avatar_frame = models.CharField(max_length=50, blank=True, default="")
    avatar_crest_url = models.URLField(blank=True, default="")
    show_activity_toasts = models.BooleanField(
        default=True,
        help_text="Show live activity feed toasts on every page.",
    )
    id_hash = models.CharField(
        max_length=8,
        default=generate_short_id,
        editable=False,
        unique=True,
    )
    slug = models.SlugField(max_length=70, unique=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("display_name"),
                condition=Q(display_name__isnull=False) & ~Q(display_name=""),
                name="users_user_display_name_unique_non_empty_ci",
            )
        ]

    def __str__(self):
        return self.email

    def generate_slug(self):
        name_part = slugify(self.display_name or self.email.split("@")[0])
        return f"{name_part}-{self.id_hash}"

    def save(self, *args, **kwargs):
        if not self.id_hash:
            self.id_hash = generate_short_id()
        if not self.slug or self._slug_needs_update():
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    def _slug_needs_update(self):
        if not self.pk:
            return True
        try:
            old = User.objects.only("display_name").get(pk=self.pk)
            return old.display_name != self.display_name
        except User.DoesNotExist:
            return True

    def get_absolute_url(self):
        return reverse("profile", kwargs={"slug": self.slug})
