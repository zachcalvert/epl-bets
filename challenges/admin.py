from django.contrib import admin

from challenges.models import Challenge, ChallengeTemplate, UserChallenge


@admin.register(ChallengeTemplate)
class ChallengeTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "challenge_type", "criteria_type", "reward_amount", "is_active"]
    list_filter = ["challenge_type", "criteria_type", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["title", "slug"]
    readonly_fields = ["created_at", "updated_at"]


class UserChallengeInline(admin.TabularInline):
    model = UserChallenge
    extra = 0
    readonly_fields = ["user", "progress", "target", "status", "completed_at", "reward_credited"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "starts_at", "ends_at", "matchday", "participant_count"]
    list_filter = ["status", "template__challenge_type"]
    search_fields = ["template__title"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["template"]
    inlines = [UserChallengeInline]

    def get_queryset(self, request):
        from django.db import models
        return super().get_queryset(request).annotate(
            _participant_count=models.Count("user_challenges")
        )

    def participant_count(self, obj):
        return obj._participant_count

    participant_count.short_description = "Participants"
    participant_count.admin_order_field = "_participant_count"


@admin.register(UserChallenge)
class UserChallengeAdmin(admin.ModelAdmin):
    list_display = ["user", "challenge", "progress", "target", "status", "completed_at", "reward_credited"]
    list_filter = ["status", "reward_credited"]
    search_fields = ["user__email", "challenge__template__title"]
    raw_id_fields = ["user", "challenge"]
    readonly_fields = ["created_at", "updated_at"]
