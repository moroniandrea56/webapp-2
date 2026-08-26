"""Test per db.py: storage SQLite delle sessioni, isolato dal database reale
tramite la fixture `app` (conftest.py), che reindirizza db.DB_PATH."""

import db


def test_save_and_get_round_trips(app):
    payload = {"asymmetry": 0.1, "customer": {"firstName": "Mario"}, "createdAt": "2026-01-01T00:00:00+00:00"}
    db.save_session("abc123", payload)

    result = db.get_session("abc123")
    assert result == payload


def test_get_missing_session_returns_none(app):
    assert db.get_session("does-not-exist") is None


def test_save_session_overwrites_same_id(app):
    db.save_session("abc123", {"asymmetry": 0.1, "customer": None, "createdAt": "2026-01-01T00:00:00+00:00"})
    db.save_session("abc123", {"asymmetry": 0.9, "customer": None, "createdAt": "2026-01-01T00:00:00+00:00"})

    assert db.get_session("abc123")["asymmetry"] == 0.9


def test_delete_session_removes_it_and_reports_existence(app):
    db.save_session("abc123", {"asymmetry": 0.1, "customer": None, "createdAt": "2026-01-01T00:00:00+00:00"})

    assert db.delete_session("abc123") is True
    assert db.get_session("abc123") is None
    assert db.delete_session("abc123") is False  # già cancellata


def test_set_email_sent_updates_payload(app):
    db.save_session("abc123", {"asymmetry": 0.1, "customer": {"email": "a@b.com"}, "createdAt": "2026-01-01T00:00:00+00:00"})

    assert db.set_email_sent("abc123", "2026-02-01T00:00:00+00:00") is True
    assert db.get_session("abc123")["emailSentAt"] == "2026-02-01T00:00:00+00:00"


def test_list_sessions_with_customer_excludes_anonymous(app):
    db.save_session("with-customer", {"customer": {"firstName": "Mario"}, "createdAt": "2026-01-01T00:00:00+00:00"})
    db.save_session("anonymous", {"customer": None, "createdAt": "2026-01-01T00:00:00+00:00"})

    items = db.list_sessions_with_customer()
    assert len(items) == 1
    assert items[0]["id"] == "with-customer"


def test_list_sessions_with_customer_orders_newest_first(app):
    db.save_session("older", {"customer": {"firstName": "A"}, "createdAt": "2026-01-01T00:00:00+00:00"})
    db.save_session("newer", {"customer": {"firstName": "B"}, "createdAt": "2026-06-01T00:00:00+00:00"})

    items = db.list_sessions_with_customer()
    assert [item["id"] for item in items] == ["newer", "older"]


def test_list_sessions_with_customer_filters_by_date_range(app):
    db.save_session("january", {"customer": {"firstName": "A"}, "createdAt": "2026-01-15T00:00:00+00:00"})
    db.save_session("june", {"customer": {"firstName": "B"}, "createdAt": "2026-06-15T00:00:00+00:00"})

    items = db.list_sessions_with_customer(date_from="2026-03-01")
    assert [item["id"] for item in items] == ["june"]

    items = db.list_sessions_with_customer(date_to="2026-03-01")
    assert [item["id"] for item in items] == ["january"]


def test_delete_sessions_older_than_cutoff(app):
    db.save_session("old", {"customer": None, "createdAt": "2020-01-01T00:00:00+00:00"})
    db.save_session("recent", {"customer": None, "createdAt": "2026-01-01T00:00:00+00:00"})

    deleted = db.delete_sessions_older_than("2025-01-01T00:00:00+00:00")

    assert deleted == 1
    assert db.get_session("old") is None
    assert db.get_session("recent") is not None
