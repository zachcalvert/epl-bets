from django.contrib import admin

from board.models import BoardPost


@admin.register(BoardPost)
class BoardPostAdmin(admin.ModelAdmin):
    list_display = ["author", "post_type", "short_body", "parent", "is_hidden", "created_at"]
    list_filter = ["post_type", "is_hidden"]
    search_fields = ["author__email", "body"]
    raw_id_fields = ["author", "parent"]

    def short_body(self, obj):
        return obj.body[:80] + "..." if len(obj.body) > 80 else obj.body

    short_body.short_description = "Body"
