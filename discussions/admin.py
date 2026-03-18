from django.contrib import admin

from discussions.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "short_body", "parent", "is_deleted", "created_at"]
    list_filter = ["is_deleted"]
    search_fields = ["user__email", "body"]
    raw_id_fields = ["user", "match", "parent"]

    def short_body(self, obj):
        return obj.body[:80] + "..." if len(obj.body) > 80 else obj.body

    short_body.short_description = "Body"
