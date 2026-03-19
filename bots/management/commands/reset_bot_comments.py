"""Management command to wipe all bot-generated comments and metadata."""

from django.core.management.base import BaseCommand

from bots.models import BotComment
from discussions.models import Comment


class Command(BaseCommand):
    help = "Delete all bot-generated comments and BotComment tracking records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        comment_count = Comment.objects.filter(user__is_bot=True).count()
        bc_count = BotComment.objects.count()

        if comment_count == 0 and bc_count == 0:
            self.stdout.write("Nothing to delete — no bot comments found.")
            return

        self.stdout.write(
            f"Found {comment_count} bot comments and {bc_count} BotComment records."
        )

        if not options["yes"]:
            confirm = input("Delete all? [y/N] ")
            if confirm.lower() != "y":
                self.stdout.write("Aborted.")
                return

        deleted_comments, _ = Comment.objects.filter(user__is_bot=True).delete()
        deleted_bc, _ = BotComment.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_comments} comments and {deleted_bc} BotComment records."
            )
        )
