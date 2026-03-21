import random
import string

from django.db import migrations
from django.utils.text import slugify


def generate_short_id():
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(8))


def populate_user_slugs(apps, schema_editor):
    User = apps.get_model("users", "User")
    existing_hashes = set()
    for user in User.objects.all():
        # Generate unique id_hash
        id_hash = generate_short_id()
        while id_hash in existing_hashes:
            id_hash = generate_short_id()
        existing_hashes.add(id_hash)
        user.id_hash = id_hash

        # Generate slug
        name_part = slugify(user.display_name or user.email.split("@")[0])
        user.slug = f"{name_part}-{id_hash}"
        user.save(update_fields=["id_hash", "slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_user_id_hash_slug"),
    ]

    operations = [
        migrations.RunPython(populate_user_slugs, migrations.RunPython.noop),
    ]
