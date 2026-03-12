from decimal import Decimal

from django.contrib import admin, messages
from django.db import models
from django.utils.translation import ngettext

from betting.models import UserBalance
from rewards.models import Reward, RewardDistribution
from users.models import User


class RewardDistributionInline(admin.TabularInline):
    model = RewardDistribution
    extra = 0
    readonly_fields = ["user", "seen", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ["name", "amount", "recipient_count", "created_by", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_by", "created_at"]
    inlines = [RewardDistributionInline]
    actions = ["distribute_to_all_users"]

    def recipient_count(self, obj):
        return obj.distributions.count()

    recipient_count.short_description = "Recipients"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Distribute to all users")
    def distribute_to_all_users(self, request, queryset):
        users = User.objects.filter(is_active=True)
        total_distributed = 0

        for reward in queryset:
            distributions = reward.distribute_to_users(users)
            total_distributed += len(distributions)

        self.message_user(
            request,
            ngettext(
                "%d reward distribution created.",
                "%d reward distributions created.",
                total_distributed,
            )
            % total_distributed,
            messages.SUCCESS,
        )


@admin.register(RewardDistribution)
class RewardDistributionAdmin(admin.ModelAdmin):
    list_display = ["reward", "user", "seen", "created_at"]
    list_filter = ["seen", "reward"]
    search_fields = ["user__email", "reward__name"]
    raw_id_fields = ["user", "reward"]

    def save_model(self, request, obj, form, change):
        is_new = not change
        super().save_model(request, obj, form, change)
        if is_new:
            balance, _ = UserBalance.objects.get_or_create(
                user=obj.user, defaults={"balance": Decimal("1000.00")}
            )
            UserBalance.objects.filter(pk=balance.pk).update(
                balance=models.F("balance") + obj.reward.amount
            )
