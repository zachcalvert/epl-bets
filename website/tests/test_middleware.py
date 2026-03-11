import pytest
from django.test import override_settings


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=["www.eplbets.net", "eplbets.net", "testserver"],
    CANONICAL_HOST="eplbets.net",
)
def test_www_host_redirects_to_canonical_apex(client):
    response = client.get(
        "/fixtures/?page=2",
        HTTP_HOST="www.eplbets.net",
        secure=True,
    )

    assert response.status_code == 301
    assert response["Location"] == "https://eplbets.net/fixtures/?page=2"


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=["www.eplbets.net", "eplbets.net", "testserver"],
    CANONICAL_HOST="eplbets.net",
)
def test_apex_host_does_not_redirect(client):
    response = client.get(
        "/fixtures/",
        HTTP_HOST="eplbets.net",
        secure=True,
    )

    assert response.status_code == 200


@override_settings(
    DEBUG=True,
    ALLOWED_HOSTS=["www.eplbets.net", "eplbets.net", "testserver"],
    CANONICAL_HOST="eplbets.net",
)
def test_canonical_redirect_is_disabled_in_debug(client):
    response = client.get(
        "/fixtures/",
        HTTP_HOST="www.eplbets.net",
    )

    assert response.status_code == 200
