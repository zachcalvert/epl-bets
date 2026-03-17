from decimal import Decimal

from django.db import migrations


def create_allin_alice_bot(apps, schema_editor):
    """Create the All In Alice bot user with balance, stats, and signup transaction."""
    User = apps.get_model("users", "User")
    UserBalance = apps.get_model("betting", "UserBalance")
    UserStats = apps.get_model("betting", "UserStats")
    BalanceTransaction = apps.get_model("betting", "BalanceTransaction")

    user, created = User.objects.get_or_create(
        email="allinalice@bots.eplbets.local",
        defaults={
            "display_name": "All In Alice",
            "is_bot": True,
            "is_active": True,
        },
    )

    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])

    UserBalance.objects.get_or_create(user=user)
    UserStats.objects.get_or_create(user=user)

    if not BalanceTransaction.objects.filter(user=user, transaction_type="SIGNUP").exists():
        BalanceTransaction.objects.create(
            user=user,
            amount=Decimal("1000.00"),
            balance_after=Decimal("1000.00"),
            transaction_type="SIGNUP",
            description="Initial signup bonus",
        )


def reverse_allin_alice_bot(apps, schema_editor):
    """Remove the All In Alice bot user created by this migration."""
    User = apps.get_model("users", "User")
    User.objects.filter(email="allinalice@bots.eplbets.local").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0001_initial"),
        ("betting", "0009_reconstruct_balance_history"),
    ]

    operations = [
        migrations.RunPython(
            create_allin_alice_bot,
            reverse_code=reverse_allin_alice_bot,
        ),
    ]
