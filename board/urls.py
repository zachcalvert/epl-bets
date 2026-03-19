from django.urls import path

from board.views import (
    BoardView,
    CreatePostView,
    CreateReplyView,
    HidePostView,
    PostListView,
)

app_name = "board"

urlpatterns = [
    path("", BoardView.as_view(), name="board"),
    path("posts/", PostListView.as_view(), name="post_list"),
    path("posts/create/", CreatePostView.as_view(), name="create_post"),
    path("posts/<str:id_hash>/reply/", CreateReplyView.as_view(), name="create_reply"),
    path("posts/<str:id_hash>/hide/", HidePostView.as_view(), name="hide_post"),
]
