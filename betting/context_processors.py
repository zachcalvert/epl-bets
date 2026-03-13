from decimal import Decimal

from betting.models import Bankruptcy, BetSlip, UserBalance

MIN_BET = Decimal("0.50")


def bankruptcy(request):
    if not request.user.is_authenticated:
        return {}

    try:
        balance = UserBalance.objects.get(user=request.user)
    except UserBalance.DoesNotExist:
        return {}

    if balance.balance >= MIN_BET:
        return {}

    has_pending_bets = BetSlip.objects.filter(
        user=request.user, status=BetSlip.Status.PENDING
    ).exists()

    if has_pending_bets:
        return {}

    bankruptcy_count = Bankruptcy.objects.filter(user=request.user).count()

    return {
        "is_bankrupt": True,
        "bankrupt_balance": balance.balance,
        "bankruptcy_count": bankruptcy_count,
    }
