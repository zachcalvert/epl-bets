from django.contrib import admin, messages

from .models import FeatureFlag


@admin.action(description="Enable for all users")
def enable_for_all(modeladmin, request, queryset):
    updated = queryset.update(is_enabled_for_all=True)
    modeladmin.message_user(
        request,
        f"{updated} flag(s) enabled for all users.",
        messages.SUCCESS,
    )


@admin.action(description="Disable for all users")
def disable_for_all(modeladmin, request, queryset):
    updated = queryset.update(is_enabled_for_all=False)
    modeladmin.message_user(
        request,
        f"{updated} flag(s) disabled for all users.",
        messages.SUCCESS,
    )


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "is_enabled_for_all", "user_count", "created_at"]
    list_filter = ["is_enabled_for_all"]
    search_fields = ["name", "description"]
    readonly_fields = ["id_hash", "created_at", "updated_at"]
    filter_horizontal = ["users"]
    actions = [enable_for_all, disable_for_all]

    @admin.display(description="Users enabled")
    def user_count(self, obj):
        return obj.users.count()
