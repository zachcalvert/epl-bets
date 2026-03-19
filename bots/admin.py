from django.contrib import admin

from bots.models import BotComment


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "match", "trigger_type", "filtered", "created_at")
    list_filter = ("trigger_type", "filtered")
    list_select_related = ("user", "match")
    readonly_fields = ("prompt_used", "raw_response")
