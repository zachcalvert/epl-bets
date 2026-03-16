"""Tests for bot services: bet placement, odds helpers, top-up."""

from decimal import Decimal

import pytest

from betting.models import (
    Bailout,
    Bankruptcy,
    BetSlip,
    Parlay,
    UserBalance,
)
from betting.tests.factories import OddsFactory, UserBalanceFactory
from bots.services import (
    get_available_matches_for_bot,
    get_best_odds_map,
    get_full_odds_map,
    maybe_topup_bot,
    place_bot_bet,
    place_bot_parlay,
)
from bots.tests.factories import BotUserFactory
from matches.models import Match
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


class TestGetAvailableMatchesForBot:
    def test_returns_scheduled_and_timed_matches(self):
        bot = BotUserFactory()
        scheduled = MatchFactory(status=Match.Status.SCHEDULED)
        timed = MatchFactory(status=Match.Status.TIMED)
        MatchFactory(status=Match.Status.FINISHED)
        MatchFactory(status=Match.Status.IN_PLAY)

        result = get_available_matches_for_bot(bot)
        ids = set(result.values_list("pk", flat=True))

        assert scheduled.pk in ids
        assert timed.pk in ids
        assert len(ids) == 2

    def test_excludes_matches_with_pending_bet(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("10"))

        result = get_available_matches_for_bot(bot)

        assert match.pk not in result.values_list("pk", flat=True)

    def test_excludes_matches_in_pending_parlay(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match1 = MatchFactory(status=Match.Status.SCHEDULED)
        match2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match1)
        OddsFactory(match=match2)

        place_bot_parlay(
            bot,
            [
                {"match_id": match1.pk, "selection": "HOME_WIN"},
                {"match_id": match2.pk, "selection": "AWAY_WIN"},
            ],
            Decimal("10"),
        )

        result = get_available_matches_for_bot(bot)
        ids = set(result.values_list("pk", flat=True))

        assert match1.pk not in ids
        assert match2.pk not in ids

    def test_includes_match_if_settled_bet_exists(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        BetSlip.objects.create(
            user=bot,
            match=match,
            selection="HOME_WIN",
            odds_at_placement=Decimal("2.00"),
            stake=Decimal("10"),
            status=BetSlip.Status.WON,
        )

        result = get_available_matches_for_bot(bot)

        assert match.pk in result.values_list("pk", flat=True)


class TestGetBestOddsMap:
    def test_returns_min_odds_per_match_across_bookmakers(self):
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="A", home_win="2.50", draw="3.20", away_win="4.00")
        OddsFactory(match=match, bookmaker="B", home_win="2.20", draw="3.40", away_win="4.20")

        result = get_best_odds_map([match.pk])

        assert result[match.pk]["home_win"] == Decimal("2.20")
        assert result[match.pk]["draw"] == Decimal("3.20")
        assert result[match.pk]["away_win"] == Decimal("4.00")

    def test_returns_empty_for_match_with_no_odds(self):
        match = MatchFactory()

        result = get_best_odds_map([match.pk])

        assert match.pk not in result

    def test_handles_multiple_matches(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        result = get_best_odds_map([m1.pk, m2.pk])

        assert m1.pk in result
        assert m2.pk in result


class TestGetFullOddsMap:
    def test_returns_all_bookmaker_rows_per_match(self):
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="Bet365", home_win="2.50", draw="3.20", away_win="4.00")
        OddsFactory(match=match, bookmaker="Betfair", home_win="2.20", draw="3.40", away_win="4.20")

        result = get_full_odds_map([match.pk])

        assert match.pk in result
        assert len(result[match.pk]) == 2
        bookmakers = {row["bookmaker"] for row in result[match.pk]}
        assert bookmakers == {"Bet365", "Betfair"}

    def test_returns_empty_for_match_with_no_odds(self):
        match = MatchFactory()

        result = get_full_odds_map([match.pk])

        assert match.pk not in result


class TestPlaceBotBet:
    def test_creates_bet_and_deducts_balance(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win="2.00", draw="3.20", away_win="4.00")

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("25.00"))

        assert bet is not None
        assert bet.user == bot
        assert bet.selection == "HOME_WIN"
        assert bet.stake == Decimal("25.00")
        assert bet.status == BetSlip.Status.PENDING
        assert UserBalance.objects.get(user=bot).balance == Decimal("475.00")

    def test_returns_none_when_insufficient_balance(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="5.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        result = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))

        assert result is None
        assert BetSlip.objects.filter(user=bot).count() == 0
        assert UserBalance.objects.get(user=bot).balance == Decimal("5.00")

    def test_returns_none_for_finished_match(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)

        result = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("10.00"))

        assert result is None

    def test_returns_none_when_no_odds_available(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)

        result = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("10.00"))

        assert result is None

    def test_uses_best_odds_across_bookmakers(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, bookmaker="A", home_win="2.50")
        OddsFactory(match=match, bookmaker="B", home_win="2.10")

        bet = place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("10.00"))

        assert bet.odds_at_placement == Decimal("2.10")

    def test_returns_none_for_invalid_selection(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)

        result = place_bot_bet(bot, match.pk, "INVALID", Decimal("10.00"))

        assert result is None

    def test_returns_none_for_nonexistent_match(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")

        result = place_bot_bet(bot, 99999, "HOME_WIN", Decimal("10.00"))

        assert result is None


class TestPlaceBotParlay:
    def test_creates_parlay_with_legs(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1, home_win="2.00")
        OddsFactory(match=m2, away_win="3.00")

        parlay = place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "AWAY_WIN"},
            ],
            Decimal("20.00"),
        )

        assert parlay is not None
        assert parlay.user == bot
        assert parlay.stake == Decimal("20.00")
        assert parlay.legs.count() == 2
        assert UserBalance.objects.get(user=bot).balance == Decimal("480.00")

    def test_combined_odds_is_product_of_legs(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1, home_win="2.00")
        OddsFactory(match=m2, home_win="3.00")

        parlay = place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "HOME_WIN"},
            ],
            Decimal("10.00"),
        )

        assert parlay.combined_odds == Decimal("6.00")

    def test_returns_none_when_insufficient_balance(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="5.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        result = place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "HOME_WIN"},
            ],
            Decimal("50.00"),
        )

        assert result is None
        assert Parlay.objects.filter(user=bot).count() == 0

    def test_returns_none_with_only_one_leg(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)

        result = place_bot_parlay(bot, [{"match_id": m1.pk, "selection": "HOME_WIN"}], Decimal("10.00"))

        assert result is None

    def test_returns_none_when_parlay_leg_has_no_odds(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        # m2 has no odds

        result = place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "HOME_WIN"},
            ],
            Decimal("10.00"),
        )

        assert result is None

    def test_returns_none_when_match_not_bettable(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        result = place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "HOME_WIN"},
            ],
            Decimal("10.00"),
        )

        assert result is None


class TestMaybeTopupBot:
    def test_does_not_topup_when_balance_is_sufficient(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="100.00")

        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 0

    def test_tops_up_when_balance_is_low_and_no_pending_bets(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="10.00")

        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 1
        assert Bailout.objects.filter(user=bot).count() == 1
        updated_balance = UserBalance.objects.get(user=bot).balance
        assert updated_balance >= Decimal("1010.00")  # 10 + at least 1000

    def test_does_not_topup_when_pending_bets_exist(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="10.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("5.00"))

        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 0

    def test_does_not_topup_when_pending_parlay_exists(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="30.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        place_bot_parlay(
            bot,
            [
                {"match_id": m1.pk, "selection": "HOME_WIN"},
                {"match_id": m2.pk, "selection": "AWAY_WIN"},
            ],
            Decimal("10.00"),
        )

        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 0

    def test_does_not_topup_when_recheck_balance_is_sufficient(self):
        """Race condition guard: balance topped up between outer check and locked check."""
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="10.00")

        # Simulate another process topping up the balance before the lock is acquired
        # by patching the locked re-fetch to return a sufficient balance
        original_get = UserBalance.objects.get

        call_count = [0]

        def patched_get(*args, **kwargs):
            obj = original_get(*args, **kwargs)
            if call_count[0] == 0 and kwargs.get("user") == bot:
                obj.balance = Decimal("200.00")
                call_count[0] += 1
            return obj

        from unittest.mock import patch

        with patch("bots.services.UserBalance.objects.select_for_update") as mock_sfq:
            mock_sfq.return_value.get.return_value = type(
                "FakeBalance", (), {"balance": Decimal("200.00")}
            )()
            maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 0

    def test_does_nothing_when_no_balance_record(self):
        bot = BotUserFactory()

        # Should not raise
        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        assert Bankruptcy.objects.filter(user=bot).count() == 0
