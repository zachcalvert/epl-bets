"""Tests for the simulate_prematch management command."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from betting.models import BetSlip
from betting.tests.factories import OddsFactory, UserBalanceFactory
from bots.models import BotComment
from bots.tests.factories import BotUserFactory
from matches.models import Match
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def make_upcoming_match(hours_from_now=24, **kwargs):
    """Scheduled match kicking off in the future."""
    return MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=timezone.now() + timedelta(hours=hours_from_now),
        **kwargs,
    )


class TestSimulatePreMatchNoMatches:
    def test_exits_early_when_no_upcoming_matches(self, capsys):
        # Only a finished match — nothing upcoming
        MatchFactory(status=Match.Status.FINISHED)

        call_command("simulate_prematch")

        assert "No upcoming matches found" in capsys.readouterr().out

    def test_exits_early_when_no_odds(self, capsys):
        make_upcoming_match()  # Match exists but no odds

        call_command("simulate_prematch")

        assert "No odds found" in capsys.readouterr().out


class TestSimulatePreMatchHappyPath:
    def test_places_bets_for_registered_bot(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.delay"):
            call_command("simulate_prematch", matches=1)

        assert BetSlip.objects.filter(user=bot, match=match).exists()

    def test_dispatches_prematch_comment_tasks(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.delay") as mock_delay, \
             patch("bots.comment_service.select_bots_for_match", return_value=[bot]):
            call_command("simulate_prematch", matches=1)

        assert mock_delay.called

    def test_comment_task_receives_bet_slip_id_when_bet_was_placed(self):
        """Phase 2 should pass the real bet_slip.pk so the comment is bet-aware."""
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.delay") as mock_delay, \
             patch("bots.comment_service.select_bots_for_match", return_value=[bot]):
            call_command("simulate_prematch", matches=1)

        bet = BetSlip.objects.filter(user=bot, match=match).first()
        assert bet is not None

        # Find the call for this bot+match and assert bet_slip_id was passed
        call_args_list = mock_delay.call_args_list
        matching_calls = [
            c for c in call_args_list
            if c.args[0] == bot.pk
            and c.args[1] == match.pk
            and c.args[2] == BotComment.TriggerType.PRE_MATCH
        ]
        assert matching_calls, "No comment task dispatched for this bot+match"
        assert matching_calls[0].args[3] == bet.pk

    def test_comment_task_receives_none_when_no_bet_placed(self):
        """Bots with no strategy (unregistered email) still get comment tasks with no bet slip."""
        bot = BotUserFactory(email="unknown@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.delay") as mock_delay, \
             patch("bots.comment_service.select_bots_for_match", return_value=[bot]):
            call_command("simulate_prematch", matches=1)

        assert not BetSlip.objects.filter(user=bot, match=match).exists()
        assert mock_delay.called
        # bet_slip_id arg should be None
        last_call = mock_delay.call_args
        assert last_call.args[3] is None


class TestSimulatePreMatchMatchesFlag:
    def test_targets_only_n_soonest_matches(self):
        """--matches 2 should only target the 2 nearest fixtures."""
        soon = make_upcoming_match(hours_from_now=2)
        middle = make_upcoming_match(hours_from_now=10)
        far = make_upcoming_match(hours_from_now=48)
        for m in [soon, middle, far]:
            OddsFactory(match=m, home_win="1.50", draw="3.20", away_win="4.50")

        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")

        with patch("bots.tasks.generate_bot_comment_task.delay") as mock_delay, \
             patch("bots.comment_service.select_bots_for_match", return_value=[bot]) as mock_select:
            call_command("simulate_prematch", matches=2)

        # select_bots_for_match should be called for the 2 nearest, not the far one
        called_match_ids = {c.args[0].pk for c in mock_select.call_args_list}
        assert soon.pk in called_match_ids
        assert middle.pk in called_match_ids
        assert far.pk not in called_match_ids

    def test_default_targets_three_matches(self, capsys):
        for i in range(5):
            m = make_upcoming_match(hours_from_now=i + 1)
            OddsFactory(match=m, home_win="1.50", draw="3.20", away_win="4.50")

        with patch("bots.tasks.generate_bot_comment_task.delay"), \
             patch("bots.comment_service.select_bots_for_match", return_value=[]):
            call_command("simulate_prematch")

        output = capsys.readouterr().out
        assert "Targeting 3 upcoming match" in output

    def test_skips_already_bet_matches(self):
        """Bots with an existing pending bet on a target match should not double-bet."""
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        # Pre-place a bet so the bot already has a pending slip
        existing_bet = BetSlip.objects.create(
            user=bot,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement="1.40",
            stake="10.00",
            status=BetSlip.Status.PENDING,
        )

        with patch("bots.tasks.generate_bot_comment_task.delay"):
            call_command("simulate_prematch", matches=1)

        # Still only the one original bet — no duplicate
        assert BetSlip.objects.filter(user=bot, match=match).count() == 1


class TestSimulatePreMatchOutput:
    def test_output_lists_target_matches(self, capsys):
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.50", draw="3.20", away_win="4.50")

        with patch("bots.tasks.generate_bot_comment_task.delay"), \
             patch("bots.comment_service.select_bots_for_match", return_value=[]):
            call_command("simulate_prematch", matches=1)

        output = capsys.readouterr().out
        assert match.home_team.name in output
        assert match.away_team.name in output

    def test_output_reports_done(self, capsys):
        match = make_upcoming_match()
        OddsFactory(match=match, home_win="1.50", draw="3.20", away_win="4.50")

        with patch("bots.tasks.generate_bot_comment_task.delay"), \
             patch("bots.comment_service.select_bots_for_match", return_value=[]):
            call_command("simulate_prematch", matches=1)

        output = capsys.readouterr().out
        assert "Done" in output
