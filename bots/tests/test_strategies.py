"""Tests for bot betting strategies."""

from decimal import Decimal

import pytest

from betting.models import BetSlip
from bots.strategies import (
    ChaosAgentStrategy,
    DrawSpecialistStrategy,
    FrontrunnerStrategy,
    ParlayStrategy,
    UnderdogStrategy,
    ValueHunterStrategy,
    _clamp_stake,
)
from matches.tests.factories import MatchFactory


def _odds_map(*entries):
    """Build an odds map from (match_id, home, draw, away) tuples."""
    return {
        mid: {"home_win": Decimal(str(h)), "draw": Decimal(str(d)), "away_win": Decimal(str(a))}
        for mid, h, d, a in entries
    }


@pytest.mark.django_db
class TestFrontrunnerStrategy:
    def test_bets_on_favorite_when_clear_favorite_exists(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.50, 4.00, 6.00))
        strategy = FrontrunnerStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert len(picks) == 1
        assert picks[0].selection == "HOME_WIN"
        assert picks[0].match_id == match.pk

    def test_skips_match_without_clear_favorite(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.10, 3.30, 3.90))  # Favorite is 2.10, above threshold
        strategy = FrontrunnerStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert picks == []

    def test_picks_away_win_when_away_is_favorite(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 5.00, 3.50, 1.40))
        strategy = FrontrunnerStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert picks[0].selection == "AWAY_WIN"

    def test_stake_capped_at_100(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.30, 4.00, 7.00))
        strategy = FrontrunnerStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("5000"))

        assert all(p.stake <= Decimal("100") for p in picks)

    def test_skips_match_with_no_odds(self):
        match = MatchFactory()
        strategy = FrontrunnerStrategy()

        picks = strategy.pick_bets([match], {}, Decimal("1000"))

        assert picks == []


@pytest.mark.django_db
class TestUnderdogStrategy:
    def test_bets_on_underdog_when_clear_underdog_exists(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.50, 3.20, 5.00))
        strategy = UnderdogStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert len(picks) == 1
        assert picks[0].selection == "AWAY_WIN"

    def test_skips_when_no_outcome_meets_threshold(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.80, 2.90, 2.80))  # All below 3.00
        strategy = UnderdogStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert picks == []

    def test_stake_capped_at_50(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.40, 3.00, 6.00))
        strategy = UnderdogStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("5000"))

        assert all(p.stake <= Decimal("50") for p in picks)

    def test_skips_match_with_no_odds(self):
        match = MatchFactory()
        strategy = UnderdogStrategy()

        picks = strategy.pick_bets([match], {}, Decimal("1000"))

        assert picks == []


@pytest.mark.django_db
class TestParlayStrategy:
    def _make_matches_with_odds(self, count, home=1.80, draw=3.20, away=2.10):
        matches = [MatchFactory() for _ in range(count)]
        odds = _odds_map(*[(m.pk, home, draw, away) for m in matches])
        return matches, odds

    def test_returns_no_single_bets(self):
        matches, odds = self._make_matches_with_odds(5)
        strategy = ParlayStrategy()

        singles = strategy.pick_bets(matches, odds, Decimal("1000"))

        assert singles == []

    def test_builds_parlay_when_enough_candidates(self):
        matches, odds = self._make_matches_with_odds(5, home=1.80)  # 1.80 in value range
        strategy = ParlayStrategy()

        parlays = strategy.pick_parlays(matches, odds, Decimal("1000"))

        assert len(parlays) == 1
        assert ParlayStrategy.MIN_LEGS <= len(parlays[0].legs) <= ParlayStrategy.MAX_LEGS

    def test_skips_when_not_enough_candidates(self):
        matches, odds = self._make_matches_with_odds(2, home=1.10)  # 1.10 below MIN_ODDS
        strategy = ParlayStrategy()

        parlays = strategy.pick_parlays(matches, odds, Decimal("1000"))

        assert parlays == []

    def test_stake_capped_at_30(self):
        matches, odds = self._make_matches_with_odds(5)
        strategy = ParlayStrategy()

        parlays = strategy.pick_parlays(matches, odds, Decimal("5000"))

        assert all(p.stake <= Decimal("30") for p in parlays)

    def test_skips_match_with_no_odds_in_parlay(self):
        match = MatchFactory()
        strategy = ParlayStrategy()

        parlays = strategy.pick_parlays([match], {}, Decimal("1000"))

        assert parlays == []

    def test_each_match_appears_at_most_once_in_parlay(self):
        matches, odds = self._make_matches_with_odds(5)
        strategy = ParlayStrategy()

        parlays = strategy.pick_parlays(matches, odds, Decimal("1000"))

        if parlays:
            match_ids = [lg["match_id"] for lg in parlays[0].legs]
            assert len(match_ids) == len(set(match_ids))


@pytest.mark.django_db
class TestDrawSpecialistStrategy:
    def test_bets_draw_in_sweet_spot(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.00, 3.20, 4.00))  # Draw 3.20 in range
        strategy = DrawSpecialistStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert len(picks) == 1
        assert picks[0].selection == "DRAW"

    def test_skips_draw_below_minimum(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 1.50, 2.50, 5.00))  # Draw 2.50 < 2.80
        strategy = DrawSpecialistStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert picks == []

    def test_skips_draw_above_maximum(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 3.00, 4.20, 3.00))  # Draw 4.20 > 3.80
        strategy = DrawSpecialistStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("1000"))

        assert picks == []

    def test_stake_capped_at_75(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.00, 3.00, 3.50))
        strategy = DrawSpecialistStrategy()

        picks = strategy.pick_bets([match], odds, Decimal("5000"))

        assert all(p.stake <= Decimal("75") for p in picks)

    def test_skips_match_with_no_odds(self):
        match = MatchFactory()
        strategy = DrawSpecialistStrategy()

        picks = strategy.pick_bets([match], {}, Decimal("1000"))

        assert picks == []


@pytest.mark.django_db
class TestValueHunterStrategy:
    def _full_odds(self, match, rows):
        return {"_full": {match.pk: rows}}

    def test_bets_outcome_with_largest_spread(self):
        match = MatchFactory()
        rows = [
            {"home_win": Decimal("2.00"), "draw": Decimal("3.00"), "away_win": Decimal("3.50")},
            {"home_win": Decimal("2.50"), "draw": Decimal("3.10"), "away_win": Decimal("3.60")},
        ]
        # home spread = 0.50, draw = 0.10, away = 0.10 → HOME_WIN has biggest spread
        odds_map = self._full_odds(match, rows)
        strategy = ValueHunterStrategy()

        picks = strategy.pick_bets([match], odds_map, Decimal("1000"))

        assert len(picks) == 1
        assert picks[0].selection == "HOME_WIN"

    def test_skips_when_spread_below_minimum(self):
        match = MatchFactory()
        rows = [
            {"home_win": Decimal("2.00"), "draw": Decimal("3.00"), "away_win": Decimal("3.50")},
            {"home_win": Decimal("2.05"), "draw": Decimal("3.05"), "away_win": Decimal("3.55")},
        ]
        # All spreads are 0.05, below MIN_SPREAD of 0.30
        odds_map = self._full_odds(match, rows)
        strategy = ValueHunterStrategy()

        picks = strategy.pick_bets([match], odds_map, Decimal("1000"))

        assert picks == []

    def test_skips_when_only_one_bookmaker(self):
        match = MatchFactory()
        rows = [{"home_win": Decimal("2.00"), "draw": Decimal("3.00"), "away_win": Decimal("3.50")}]
        odds_map = self._full_odds(match, rows)
        strategy = ValueHunterStrategy()

        picks = strategy.pick_bets([match], odds_map, Decimal("1000"))

        assert picks == []

    def test_skips_match_with_no_full_odds(self):
        match = MatchFactory()
        strategy = ValueHunterStrategy()

        picks = strategy.pick_bets([match], {"_full": {}}, Decimal("1000"))

        assert picks == []

    def test_stake_capped_at_80(self):
        match = MatchFactory()
        rows = [
            {"home_win": Decimal("1.50"), "draw": Decimal("3.00"), "away_win": Decimal("5.00")},
            {"home_win": Decimal("2.00"), "draw": Decimal("3.10"), "away_win": Decimal("5.10")},
        ]
        odds_map = self._full_odds(match, rows)
        strategy = ValueHunterStrategy()

        picks = strategy.pick_bets([match], odds_map, Decimal("5000"))

        assert all(p.stake <= Decimal("80") for p in picks)


@pytest.mark.django_db
class TestChaosAgentStrategy:
    def test_only_bets_matches_with_odds(self):
        match_with_odds = MatchFactory()
        match_without_odds = MatchFactory()
        odds = _odds_map((match_with_odds.pk, 2.00, 3.20, 3.80))
        strategy = ChaosAgentStrategy()

        # Run enough times to get some bets
        all_picks = []
        for _ in range(20):
            all_picks.extend(strategy.pick_bets([match_with_odds, match_without_odds], odds, Decimal("1000")))

        bet_match_ids = {p.match_id for p in all_picks}
        assert match_without_odds.pk not in bet_match_ids

    def test_stake_within_bounds(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.00, 3.20, 3.80))
        strategy = ChaosAgentStrategy()

        all_picks = []
        for _ in range(50):
            all_picks.extend(strategy.pick_bets([match], odds, Decimal("1000")))

        for pick in all_picks:
            assert Decimal("1") <= pick.stake <= Decimal("100")

    def test_skips_bet_when_balance_below_minimum_stake(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.00, 3.20, 3.80))
        strategy = ChaosAgentStrategy()

        # Balance of 0.50 — randomint(5,100) will always exceed this, so stake < 1.00
        picks = strategy.pick_bets([match], odds, Decimal("0.50"))

        # stake = min(random 5-100, 0.50) = 0.50 which is < 1.00, so all skipped
        assert picks == []

    def test_uses_valid_selections(self):
        match = MatchFactory()
        odds = _odds_map((match.pk, 2.00, 3.20, 3.80))
        strategy = ChaosAgentStrategy()
        valid = {BetSlip.Selection.HOME_WIN, BetSlip.Selection.DRAW, BetSlip.Selection.AWAY_WIN}

        all_picks = []
        for _ in range(50):
            all_picks.extend(strategy.pick_bets([match], odds, Decimal("1000")))

        for pick in all_picks:
            assert pick.selection in valid


class TestClampStake:
    def test_returns_value_within_bounds(self):
        assert _clamp_stake(Decimal("50")) == Decimal("50")

    def test_clamps_below_floor(self):
        assert _clamp_stake(Decimal("0.10")) == Decimal("1.00")

    def test_clamps_above_ceiling(self):
        assert _clamp_stake(Decimal("200"), ceiling=Decimal("100")) == Decimal("100")

    def test_custom_floor(self):
        assert _clamp_stake(Decimal("0.30"), floor=Decimal("0.50")) == Decimal("0.50")
