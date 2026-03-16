from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.utils import timezone
from django.utils.translation import ngettext

from betting.models import BetSlip, UserBalance
from rewards.models import Reward

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "display_name", "first_name", "last_name", "is_staff", "is_bot")
    list_filter = ("is_staff", "is_superuser", "is_active", "is_bot")
    search_fields = ("email", "display_name", "first_name", "last_name")
    ordering = ("email",)
    actions = ["grant_latest_reward", "simulate_bankruptcy"]

    @admin.action(description="Grant latest reward to selected users")
    def grant_latest_reward(self, request, queryset):
        reward = Reward.objects.first()
        if not reward:
            self.message_user(
                request,
                "No rewards exist yet. Create one first.",
                messages.WARNING,
            )
            return

        distributions = reward.distribute_to_users(queryset)
        self.message_user(
            request,
            ngettext(
                "%(count)d user received '%(name)s' (%(amount)s credits).",
                "%(count)d users received '%(name)s' (%(amount)s credits).",
                len(distributions),
            )
            % {"count": len(distributions), "name": reward.name, "amount": reward.amount},
            messages.SUCCESS,
        )

    @admin.action(description="Simulate bankruptcy for selected users")
    def simulate_bankruptcy(self, request, queryset):
        count = 0
        for user in queryset:
            with transaction.atomic():
                # Settle all pending bets as losses
                BetSlip.objects.filter(
                    user=user, status=BetSlip.Status.PENDING
                ).update(
                    status=BetSlip.Status.LOST,
                    payout=0,
                    updated_at=timezone.now(),
                )

                # Zero out balance
                UserBalance.objects.filter(user=user).update(
                    balance=0,
                    updated_at=timezone.now(),
                )

            count += 1

        self.message_user(
            request,
            ngettext(
                "%(count)d user is now bankrupt.",
                "%(count)d users are now bankrupt.",
                count,
            )
            % {"count": count},
            messages.SUCCESS,
        )

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("display_name", "first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
