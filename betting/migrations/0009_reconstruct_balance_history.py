"""
Full balance history reconstruction.

Clears all BalanceTransaction records and rebuilds them from scratch by
replaying each user's betting history in chronological order:

  SIGNUP          → user.date_joined, +1000
  BET_PLACEMENT   → bet.created_at, -stake         (all bets)
  BET_WIN         → bet.updated_at, +payout         (WON bets)
  BET_VOID        → bet.updated_at, +stake          (VOID bets)
  PARLAY_PLACEMENT→ parlay.created_at, -stake       (all parlays)
  PARLAY_WIN      → parlay.updated_at, +payout      (WON parlays)
  PARLAY_VOID     → parlay.updated_at, +stake       (VOID parlays)
  BAILOUT         → bailout.created_at, +amount
  REWARD          → reward_distribution.created_at, +amount
  CHALLENGE_REWARD→ user_challenge.completed_at, +reward_amount

If the reconstructed running balance doesn't match the user's actual current
balance after all known events, an ADMIN_RESET adjustment is appended to
bridge the gap. This covers pre-instrumentation admin actions (e.g. simulate
bankruptcy) that had no transaction log.
"""

from decimal import Decimal

from django.db import migrations


def reconstruct_balance_history(apps, schema_editor):
    UserBalance = apps.get_model("betting", "UserBalance")
    BalanceTransaction = apps.get_model("betting", "BalanceTransaction")
    BetSlip = apps.get_model("betting", "BetSlip")
    Parlay = apps.get_model("betting", "Parlay")
    Bailout = apps.get_model("betting", "Bailout")
    RewardDistribution = apps.get_model("rewards", "RewardDistribution")
    UserChallenge = apps.get_model("challenges", "UserChallenge")

    BalanceTransaction.objects.all().delete()

    from django.db import connection

    for ub in UserBalance.objects.select_related("user").all():
        user = ub.user
        events = []  # (timestamp, type, amount, description)

        # SIGNUP
        events.append((
            user.date_joined,
            "SIGNUP",
            Decimal("1000.00"),
            "Initial signup bonus",
        ))

        # BET_PLACEMENT — deducted at placement for all bets regardless of outcome
        for bet in BetSlip.objects.filter(user=user).select_related(
            "match__home_team", "match__away_team"
        ):
            home = bet.match.home_team.short_name or bet.match.home_team.name
            away = bet.match.away_team.short_name or bet.match.away_team.name
            events.append((
                bet.created_at,
                "BET_PLACEMENT",
                -bet.stake,
                f"Bet on {home} vs {away}",
            ))

        # BET_WIN — payout credited at settlement time (updated_at)
        for bet in BetSlip.objects.filter(user=user, status="WON"):
            events.append((
                bet.updated_at,
                "BET_WIN",
                bet.payout,
                f"Bet {bet.id_hash} won",
            ))

        # BET_VOID — stake refunded at settlement time
        for bet in BetSlip.objects.filter(user=user, status="VOID"):
            events.append((
                bet.updated_at,
                "BET_VOID",
                bet.stake,
                f"Bet {bet.id_hash} voided",
            ))

        # PARLAY_PLACEMENT — deducted at placement for all parlays
        for parlay in Parlay.objects.filter(user=user):
            leg_count = parlay.legs.count()
            events.append((
                parlay.created_at,
                "PARLAY_PLACEMENT",
                -parlay.stake,
                f"Parlay {parlay.id_hash} ({leg_count} legs)",
            ))

        # PARLAY_WIN
        for parlay in Parlay.objects.filter(user=user, status="WON"):
            events.append((
                parlay.updated_at,
                "PARLAY_WIN",
                parlay.payout,
                f"Parlay {parlay.id_hash} won",
            ))

        # PARLAY_VOID
        for parlay in Parlay.objects.filter(user=user, status="VOID"):
            events.append((
                parlay.updated_at,
                "PARLAY_VOID",
                parlay.stake,
                f"Parlay {parlay.id_hash} voided",
            ))

        # BAILOUT
        for bailout in Bailout.objects.filter(user=user):
            events.append((
                bailout.created_at,
                "BAILOUT",
                bailout.amount,
                "Bankruptcy bailout",
            ))

        # REWARD distributions
        for dist in RewardDistribution.objects.filter(user=user).select_related("reward"):
            events.append((
                dist.created_at,
                "REWARD",
                dist.reward.amount,
                f"Reward: {dist.reward.name}",
            ))

        # CHALLENGE completions (only ones that actually credited the balance)
        for uc in UserChallenge.objects.filter(
            user=user, status="COMPLETED", reward_credited=True
        ).select_related("challenge__template"):
            if uc.completed_at:
                events.append((
                    uc.completed_at,
                    "CHALLENGE_REWARD",
                    uc.challenge.template.reward_amount,
                    f"Challenge: {uc.challenge.template.title}",
                ))

        events.sort(key=lambda e: e[0])

        # Build running balance
        running_balance = Decimal("0.00")
        for ts, tx_type, amount, description in events:
            running_balance += amount

        # If the reconstructed balance doesn't match the actual current balance,
        # append an ADMIN_RESET adjustment. This covers pre-instrumentation admin
        # actions (e.g. simulate bankruptcy) that left no transaction log.
        drift = ub.balance - running_balance
        if drift != 0:
            # Use the timestamp of the last event as an approximation
            last_ts = events[-1][0] if events else user.date_joined
            events.append((
                last_ts,
                "ADMIN_RESET",
                drift,
                "Historical adjustment (pre-instrumentation admin action)",
            ))

        # Create transaction objects with running balance_after
        running_balance = Decimal("0.00")
        to_create = []
        for _ts, tx_type, amount, description in events:
            running_balance += amount
            to_create.append(BalanceTransaction(
                user=user,
                amount=amount,
                balance_after=running_balance,
                transaction_type=tx_type,
                description=description,
                # created_at is auto_now_add — fixed via raw SQL below
            ))

        created = BalanceTransaction.objects.bulk_create(to_create)

        # Fix created_at to match historical timestamps
        with connection.cursor() as cursor:
            for obj, (timestamp, _, _, _) in zip(created, events):
                cursor.execute(
                    "UPDATE betting_balancetransaction SET created_at = %s WHERE id = %s",
                    [timestamp, obj.pk],
                )


class Migration(migrations.Migration):

    dependencies = [
        ("betting", "0008_backfill_signup_transactions"),
        ("rewards", "0001_initial"),
        ("challenges", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            reconstruct_balance_history,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
