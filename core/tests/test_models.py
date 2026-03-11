import re

from core.models import BaseModel, generate_short_id


def test_generate_short_id_returns_eight_character_alphanumeric_string():
    short_id = generate_short_id()

    assert len(short_id) == 8
    assert re.fullmatch(r"[A-Za-z0-9]{8}", short_id)


def test_base_model_is_abstract():
    assert BaseModel._meta.abstract is True

