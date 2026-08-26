"""
conftest.py
============
Fixture condivise per la suite di test (tests/).

La fixture `app` isola ogni test dal file data/sessions.json reale:
reindirizza server.py verso una cartella temporanea per la durata del
singolo test, così i test non toccano né dipendono da sessioni salvate in
precedenza (e non lasciano residui nel repo).
"""

import base64

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    import server

    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "SESSIONS_FILE", str(tmp_path / "sessions.json"))
    server.app.config.update(TESTING=True)
    return server.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_auth():
    """Header Basic Auth con le credenziali admin di default (admin/brainart)."""
    import server

    token = base64.b64encode(f"{server.ADMIN_USERNAME}:{server.ADMIN_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def valid_customer():
    """Un dato cliente valido, fresco a ogni test (nessuno stato condiviso tra test)."""
    return {
        "firstName": "Mario",
        "lastName": "Rossi",
        "email": "mario@example.com",
        "consent": True,
    }
