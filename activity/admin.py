from django.contrib import admin

from .models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "message", "created_at", "broadcast_at")
    list_filter = ("event_type", "broadcast_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
