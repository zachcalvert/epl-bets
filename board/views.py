import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.views import View

from board.forms import BoardPostForm
from board.models import BoardPost, PostType

logger = logging.getLogger(__name__)

POSTS_PER_PAGE = 20


def _visible_top_level_qs(post_type=None):
    """Top-level, non-hidden posts — optionally filtered by type."""
    qs = BoardPost.objects.filter(parent__isnull=True, is_hidden=False)
    if post_type and post_type in PostType.values:
        qs = qs.filter(post_type=post_type)
    return qs


class BoardView(View):
    def get(self, request):
        active_type = request.GET.get("type", "")
        context = {
            "form": BoardPostForm(),
            "active_type": active_type,
            "post_types": PostType,
        }
        return TemplateResponse(request, "board/board.html", context)


class PostListView(View):
    def get(self, request):
        post_type = request.GET.get("type", "")
        try:
            offset = max(0, int(request.GET.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0

        replies_qs = (
            BoardPost.objects.filter(is_hidden=False)
            .select_related("author")
            .order_by("created_at")
        )
        visible_qs = _visible_top_level_qs(post_type)
        posts = list(
            visible_qs.select_related("author")
            .prefetch_related(
                Prefetch("replies", queryset=replies_qs, to_attr="prefetched_replies")
            )
            .order_by("-created_at")[offset : offset + POSTS_PER_PAGE]
        )

        total_count = visible_qs.count()
        has_more = (offset + POSTS_PER_PAGE) < total_count
        next_offset = offset + POSTS_PER_PAGE

        context = {
            "posts": posts,
            "post_count": total_count,
            "has_more": has_more,
            "next_offset": next_offset,
            "active_type": post_type,
            "request": request,
        }

        if offset > 0:
            html = render_to_string(
                "board/partials/post_page.html", context, request=request
            )
        else:
            html = render_to_string(
                "board/partials/post_list.html", context, request=request
            )
        return HttpResponse(html)


class CreatePostView(LoginRequiredMixin, View):
    def post(self, request):
        form = BoardPostForm(request.POST)
        if not form.is_valid():
            html = render_to_string(
                "board/partials/post_form.html",
                {"form": form},
                request=request,
            )
            return HttpResponse(html, status=422)

        post = BoardPost.objects.create(
            author=request.user,
            post_type=form.cleaned_data["post_type"],
            body=form.cleaned_data["body"],
        )
        post.prefetched_replies = []

        new_count = _visible_top_level_qs().count()

        html = render_to_string(
            "board/partials/post_single.html",
            {"post": post, "is_reply": False},
            request=request,
        )
        html += render_to_string(
            "board/partials/post_count_oob.html",
            {"post_count": new_count},
        )
        return HttpResponse(html)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        parent = get_object_or_404(BoardPost, id_hash=id_hash, parent__isnull=True)

        if parent.parent_id is not None:
            return HttpResponse("Cannot reply to a reply.", status=400)

        body = request.POST.get("body", "").strip()
        if not body:
            html = (
                f'<div id="reply-error-{parent.id_hash}" hx-swap-oob="true" '
                f'class="text-red-400 text-xs mt-1">Reply cannot be empty.</div>'
            )
            return HttpResponse(html, status=422)
        if len(body) > 2000:
            html = (
                f'<div id="reply-error-{parent.id_hash}" hx-swap-oob="true" '
                f'class="text-red-400 text-xs mt-1">Reply is too long (max 2000 characters).</div>'
            )
            return HttpResponse(html, status=422)

        reply = BoardPost.objects.create(
            author=request.user,
            post_type=parent.post_type,
            body=body,
            parent=parent,
        )
        reply.prefetched_replies = []

        html = render_to_string(
            "board/partials/post_single.html",
            {"post": reply, "is_reply": True},
            request=request,
        )
        return HttpResponse(html)


class HidePostView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        post = get_object_or_404(BoardPost, id_hash=id_hash)

        if not request.user.is_superuser:
            return HttpResponseForbidden()

        post.is_hidden = not post.is_hidden
        post.save(update_fields=["is_hidden", "updated_at"])

        if post.is_hidden:
            # Return empty div to remove from view (or dimmed placeholder for superuser)
            html = render_to_string(
                "board/partials/post_hidden.html",
                {"post": post},
                request=request,
            )
        else:
            post.prefetched_replies = list(
                post.replies.filter(is_hidden=False)
                .select_related("author")
                .order_by("created_at")
            )
            html = render_to_string(
                "board/partials/post_single.html",
                {"post": post, "is_reply": post.parent_id is not None},
                request=request,
            )
        return HttpResponse(html)
