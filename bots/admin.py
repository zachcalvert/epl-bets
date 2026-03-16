from django.contrib import admin

from bots.models import HomerBotConfig


@admin.register(HomerBotConfig)
class HomerBotConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "draw_underdog_threshold")
    list_select_related = ("user", "team")
    autocomplete_fields = ("user", "team")
