"""Test end-to-end sugli endpoint HTTP di server.py, tramite il test client
di Flask (nessun server reale in ascolto): validazione via API, protezione
delle rotte admin, ed endpoint pubblici."""

import pytest


def _create_session(client, customer=None, stimulus=None):
    body = {}
    if customer is not None:
        body["customer"] = customer
    if stimulus is not None:
        body["stimulus"] = stimulus
    return client.post("/api/session", json=body)


# --- creazione sessione e validazione cliente -----------------------------------

def test_create_session_without_customer_is_public_and_anonymous(client):
    res = _create_session(client)
    assert res.status_code == 201
    assert res.get_json()["customer"] is None


def test_create_session_with_valid_customer(client, valid_customer):
    res = _create_session(client, customer=valid_customer)
    assert res.status_code == 201
    data = res.get_json()
    assert data["customer"]["firstName"] == "Mario"
    assert "id" in data


@pytest.mark.parametrize("missing_field", ["firstName", "lastName", "email"])
def test_create_session_rejects_missing_required_field(client, valid_customer, missing_field):
    valid_customer[missing_field] = ""
    res = _create_session(client, customer=valid_customer)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_create_session_rejects_invalid_email(client, valid_customer):
    valid_customer["email"] = "non-una-email"
    res = _create_session(client, customer=valid_customer)
    assert res.status_code == 400


def test_create_session_rejects_missing_consent(client, valid_customer):
    valid_customer["consent"] = False
    res = _create_session(client, customer=valid_customer)
    assert res.status_code == 400


# --- stimolo -------------------------------------------------------------------

def test_create_session_defaults_to_lettura_stimulus(client, valid_customer):
    res = _create_session(client, customer=valid_customer)
    assert res.get_json()["stimulus"]["type"] == "lettura"


def test_create_session_uses_given_stimulus_detail_as_quote(client, valid_customer):
    res = _create_session(client, customer=valid_customer, stimulus={"type": "musica", "detail": "Test"})
    data = res.get_json()
    assert data["stimulus"]["type"] == "musica"
    assert data["quote"] == "Test"


# --- lettura sessione ------------------------------------------------------------

def test_get_session_hides_full_customer_object(client, valid_customer):
    created = _create_session(client, customer=valid_customer).get_json()
    res = client.get(f"/api/session/{created['id']}")
    data = res.get_json()
    assert res.status_code == 200
    assert "customer" not in data
    assert data["firstName"] == "Mario"


def test_get_session_returns_identical_data_on_repeated_reads(client):
    created = _create_session(client).get_json()
    first = client.get(f"/api/session/{created['id']}").get_json()
    second = client.get(f"/api/session/{created['id']}").get_json()
    assert first == second


def test_get_unknown_session_returns_404_json(client):
    res = client.get("/api/session/does-not-exist")
    assert res.status_code == 404
    assert "error" in res.get_json()


# --- protezione delle rotte admin -------------------------------------------------

ADMIN_ROUTES_GET = ["/admin", "/admin.html", "/admin/sessions", "/admin-sessions.html", "/api/sessions"]


@pytest.mark.parametrize("path", ADMIN_ROUTES_GET)
def test_admin_routes_require_login(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ADMIN_ROUTES_GET)
def test_admin_routes_accept_correct_login(client, admin_auth, path):
    assert client.get(path, headers=admin_auth).status_code == 200


def test_delete_session_requires_login(client, valid_customer):
    created = _create_session(client, customer=valid_customer).get_json()
    res = client.delete(f"/api/session/{created['id']}")
    assert res.status_code == 401


def test_delete_session_removes_it(client, admin_auth, valid_customer):
    created = _create_session(client, customer=valid_customer).get_json()
    res = client.delete(f"/api/session/{created['id']}", headers=admin_auth)
    assert res.status_code == 200

    assert client.get(f"/api/session/{created['id']}").status_code == 404


def test_list_sessions_excludes_anonymous_sessions(client, admin_auth, valid_customer):
    _create_session(client)  # anonima, senza customer
    _create_session(client, customer=valid_customer)

    items = client.get("/api/sessions", headers=admin_auth).get_json()
    assert len(items) == 1
    assert items[0]["customer"]["firstName"] == "Mario"


def test_qrcode_requires_login(client):
    created = _create_session(client).get_json()
    assert client.get(f"/api/qrcode/{created['id']}").status_code == 401


def test_qrcode_returns_png_when_authorized(client, admin_auth):
    created = _create_session(client).get_json()
    res = client.get(f"/api/qrcode/{created['id']}", headers=admin_auth)
    assert res.status_code == 200
    assert res.content_type == "image/png"


# --- endpoint pubblici -------------------------------------------------------------

def test_artwork_is_public(client):
    created = _create_session(client).get_json()
    res = client.get(f"/api/artwork/{created['id']}.png")
    assert res.status_code == 200
    assert res.content_type == "image/png"


def test_config_is_public(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "dataControllerEmail" in res.get_json()


# --- invio email -------------------------------------------------------------------

def test_send_email_requires_login(client, valid_customer):
    created = _create_session(client, customer=valid_customer).get_json()
    res = client.post(f"/api/session/{created['id']}/send-email")
    assert res.status_code == 401


def test_send_email_without_smtp_returns_clear_501(client, admin_auth, valid_customer, monkeypatch):
    import email_sender

    monkeypatch.setattr(email_sender, "SMTP_HOST", "")
    monkeypatch.setattr(email_sender, "SMTP_USER", "")
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", "")

    created = _create_session(client, customer=valid_customer).get_json()
    res = client.post(f"/api/session/{created['id']}/send-email", headers=admin_auth)
    assert res.status_code == 501
    assert "error" in res.get_json()
