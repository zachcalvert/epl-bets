from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from betting.context_processors import bankruptcy
from betting.models import Bankruptcy as BankruptcyModel
from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, UserBalanceFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestBankruptcyContextProcessor:
    def setup_method(self):
        self.factory = RequestFactory()

    def _make_request(self, user=None):
        request = self.factory.get("/")
        if user:
            request.user = user
        else:
            request.user = AnonymousUser()
        return request

    def test_returns_empty_for_anonymous_user(self):
        request = self._make_request()
        assert bankruptcy(request) == {}

    def test_returns_empty_when_balance_above_min_bet(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="100.00")

        request = self._make_request(user)
        assert bankruptcy(request) == {}

    def test_returns_empty_when_balance_equals_min_bet(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.50")

        request = self._make_request(user)
        assert bankruptcy(request) == {}

    def test_returns_empty_when_no_balance_exists(self):
        user = UserFactory()

        request = self._make_request(user)
        assert bankruptcy(request) == {}

    def test_returns_empty_when_bankrupt_but_has_pending_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.00")
        BetSlipFactory(user=user, status=BetSlip.Status.PENDING)

        request = self._make_request(user)
        assert bankruptcy(request) == {}

    def test_returns_bankrupt_context_when_broke_with_no_pending_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.25")

        request = self._make_request(user)
        context = bankruptcy(request)

        assert context["is_bankrupt"] is True
        assert context["bankrupt_balance"] == Decimal("0.25")
        assert context["bankruptcy_count"] == 0

    def test_bankruptcy_count_reflects_prior_bankruptcies(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.00")
        BankruptcyModel.objects.create(user=user, balance_at_bankruptcy=Decimal("0.10"))
        BankruptcyModel.objects.create(user=user, balance_at_bankruptcy=Decimal("0.00"))

        request = self._make_request(user)
        context = bankruptcy(request)

        assert context["bankruptcy_count"] == 2

    def test_settled_bets_do_not_block_bankruptcy(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.00")
        BetSlipFactory(user=user, status=BetSlip.Status.LOST)
        BetSlipFactory(user=user, status=BetSlip.Status.WON)

        request = self._make_request(user)
        context = bankruptcy(request)

        assert context["is_bankrupt"] is True
