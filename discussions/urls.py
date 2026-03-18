from django.urls import path

from discussions.views import (
    CommentListView,
    CreateCommentView,
    CreateReplyView,
    DeleteCommentView,
)

app_name = "discussions"

urlpatterns = [
    path(
        "match/<int:match_pk>/comments/",
        CommentListView.as_view(),
        name="comment_list",
    ),
    path(
        "match/<int:match_pk>/comments/create/",
        CreateCommentView.as_view(),
        name="create_comment",
    ),
    path(
        "match/<int:match_pk>/comments/<int:comment_pk>/reply/",
        CreateReplyView.as_view(),
        name="create_reply",
    ),
    path(
        "match/<int:match_pk>/comments/<int:comment_pk>/delete/",
        DeleteCommentView.as_view(),
        name="delete_comment",
    ),
]
