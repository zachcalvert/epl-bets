from decimal import Decimal

from django.db import migrations


def create_allin_alice_bot(apps, schema_editor):
    """Create the All In Alice bot user with balance, stats, and signup transaction."""
    User = apps.get_model("users", "User")
    UserBalance = apps.get_model("betting", "UserBalance")
    UserStats = apps.get_model("betting", "UserStats")
    BalanceTransaction = apps.get_model("betting", "BalanceTransaction")

    user, created = User.objects.update_or_create(
        email="allinalice@bots.eplbets.local",
        defaults={
            "display_name": "All In Alice",
            "is_bot": True,
            "is_active": True,
        },
    )

    if user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])

    UserBalance.objects.get_or_create(user=user)
    UserStats.objects.get_or_create(user=user)

    # Only create the signup transaction when the user has no transactions at all,
    # matching the guard used in 0008_backfill_signup_transactions.
    if not BalanceTransaction.objects.filter(user=user).exists():
        tx = BalanceTransaction.objects.create(
            user=user,
            amount=Decimal("1000.00"),
            balance_after=Decimal("1000.00"),
            transaction_type="SIGNUP",
            description="Initial signup bonus",
        )
        # Backdate created_at to date_joined so balance history is ordered correctly.
        BalanceTransaction.objects.filter(pk=tx.pk).update(created_at=user.date_joined)


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0001_initial"),
        ("betting", "0009_reconstruct_balance_history"),
        ("users", "0004_add_is_bot_to_user"),
    ]

    operations = [
        migrations.RunPython(
            create_allin_alice_bot,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
