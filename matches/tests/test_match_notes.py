"""Tests for MatchNotes model, views, and bot prompt injection."""

from unittest.mock import MagicMock

import pytest
from django.db import IntegrityError
from django.urls import reverse

from bots.comment_service import _build_user_prompt
from bots.models import BotComment
from matches.models import MatchNotes
from matches.tests.factories import MatchFactory, MatchNotesFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ── Model ────────────────────────────────────────────────────────────────────


class TestMatchNotesModel:
    def test_str(self):
        notes = MatchNotesFactory()
        assert str(notes) == f"Notes for {notes.match}"

    def test_one_to_one_constraint(self):
        notes = MatchNotesFactory()
        with pytest.raises(IntegrityError):
            MatchNotesFactory(match=notes.match)

    def test_accessible_via_match_reverse_relation(self):
        notes = MatchNotesFactory()
        assert notes.match.notes == notes


# ── View: match detail shows notes form for superuser ────────────────────────


class TestMatchNotesInDetail:
    def test_superuser_sees_notes_form(self, client):
        user = UserFactory(is_superuser=True, is_staff=True)
        client.force_login(user)
        match = MatchFactory()

        response = client.get(reverse("matches:match_detail", args=[match.slug]))

        assert response.status_code == 200
        assert "match_notes_form" in response.context

    def test_regular_user_does_not_see_notes_form(self, client):
        user = UserFactory()
        client.force_login(user)
        match = MatchFactory()

        response = client.get(reverse("matches:match_detail", args=[match.slug]))

        assert response.status_code == 200
        assert "match_notes_form" not in response.context

    def test_anonymous_user_does_not_see_notes_form(self, client):
        match = MatchFactory()

        response = client.get(reverse("matches:match_detail", args=[match.slug]))

        assert response.status_code == 200
        assert "match_notes_form" not in response.context

    def test_existing_notes_prepopulate_form(self, client):
        user = UserFactory(is_superuser=True, is_staff=True)
        client.force_login(user)
        notes = MatchNotesFactory(body="Maguire red card 80'")

        response = client.get(reverse("matches:match_detail", args=[notes.match.slug]))

        assert response.context["match_notes"].body == "Maguire red card 80'"


# ── View: saving notes ──────────────────────────────────────────────────────


class TestMatchNotesView:
    def test_superuser_can_create_notes(self, client):
        user = UserFactory(is_superuser=True, is_staff=True)
        client.force_login(user)
        match = MatchFactory()

        response = client.post(
            reverse("matches:match_notes", args=[match.slug]),
            {"body": "Bruno screamer from 30 yards"},
        )

        assert response.status_code == 200
        assert MatchNotes.objects.filter(match=match).exists()
        assert MatchNotes.objects.get(match=match).body == "Bruno screamer from 30 yards"

    def test_superuser_can_update_notes(self, client):
        user = UserFactory(is_superuser=True, is_staff=True)
        client.force_login(user)
        notes = MatchNotesFactory(body="First half boring")

        response = client.post(
            reverse("matches:match_notes", args=[notes.match.slug]),
            {"body": "First half boring. Second half madness."},
        )

        assert response.status_code == 200
        notes.refresh_from_db()
        assert notes.body == "First half boring. Second half madness."

    def test_regular_user_forbidden(self, client):
        user = UserFactory()
        client.force_login(user)
        match = MatchFactory()

        response = client.post(
            reverse("matches:match_notes", args=[match.slug]),
            {"body": "sneaky notes"},
        )

        assert response.status_code == 403
        assert not MatchNotes.objects.filter(match=match).exists()

    def test_anonymous_user_redirected(self, client):
        match = MatchFactory()

        response = client.post(
            reverse("matches:match_notes", args=[match.slug]),
            {"body": "sneaky notes"},
        )

        assert response.status_code == 302

    def test_saved_response_contains_success_message(self, client):
        user = UserFactory(is_superuser=True, is_staff=True)
        client.force_login(user)
        match = MatchFactory()

        response = client.post(
            reverse("matches:match_notes", args=[match.slug]),
            {"body": "Great match"},
        )

        assert b"Notes saved" in response.content


# ── Bot prompt injection ─────────────────────────────────────────────────────


class TestMatchNotesInPrompt:
    def test_post_match_prompt_includes_notes(self):
        match = MatchFactory(home_score=2, away_score=1, status="FINISHED")
        MatchNotesFactory(match=match, body="Red card at 80'. Penalty drama.")

        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH)

        assert "Match notes (from a real viewer):" in prompt
        assert "Red card at 80'. Penalty drama." in prompt

    def test_reply_prompt_includes_notes(self):
        match = MatchFactory(home_score=1, away_score=1, status="FINISHED")
        MatchNotesFactory(match=match, body="VAR disallowed a goal in stoppage time")
        parent = MagicMock()
        parent.body = "What a match!"
        parent.user.display_name = "TestUser"
        parent.parent = None

        prompt = _build_user_prompt(
            match, BotComment.TriggerType.REPLY, parent_comment=parent
        )

        assert "Match notes (from a real viewer):" in prompt
        assert "VAR disallowed a goal" in prompt

    def test_pre_match_prompt_excludes_notes(self):
        match = MatchFactory()
        MatchNotesFactory(match=match, body="Should not appear")

        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)

        assert "Match notes" not in prompt
        assert "Should not appear" not in prompt

    def test_post_bet_prompt_excludes_notes(self):
        match = MatchFactory()
        MatchNotesFactory(match=match, body="Should not appear")
        bet_slip = MagicMock()
        bet_slip.get_selection_display.return_value = "Home Win"
        bet_slip.odds_at_placement = "2.50"
        bet_slip.stake = 100

        prompt = _build_user_prompt(
            match, BotComment.TriggerType.POST_BET, bet_slip=bet_slip
        )

        assert "Match notes" not in prompt

    def test_prompt_without_notes_has_no_notes_section(self):
        match = MatchFactory(home_score=3, away_score=0, status="FINISHED")

        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH)

        assert "Match notes" not in prompt

    def test_empty_notes_body_excluded_from_prompt(self):
        match = MatchFactory(home_score=1, away_score=0, status="FINISHED")
        MatchNotesFactory(match=match, body="   ")

        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH)

        assert "Match notes" not in prompt
