from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import ngettext

from rewards.models import Reward

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "display_name", "first_name", "last_name", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name", "first_name", "last_name")
    ordering = ("email",)
    actions = ["grant_latest_reward"]

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
