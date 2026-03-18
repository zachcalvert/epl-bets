from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

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
