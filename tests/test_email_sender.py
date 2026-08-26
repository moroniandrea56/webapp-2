"""Test per email_sender.py: rilevamento di una configurazione SMTP mancante,
senza inviare email reali."""

import pytest

import email_sender


def test_smtp_configured_false_when_credentials_missing(monkeypatch):
    monkeypatch.setattr(email_sender, "SMTP_HOST", "")
    monkeypatch.setattr(email_sender, "SMTP_USER", "")
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", "")
    assert email_sender.smtp_configured() is False


def test_smtp_configured_true_when_all_present(monkeypatch):
    monkeypatch.setattr(email_sender, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_sender, "SMTP_USER", "user@example.com")
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", "secret")
    assert email_sender.smtp_configured() is True


def test_send_artwork_email_raises_clear_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(email_sender, "SMTP_HOST", "")
    monkeypatch.setattr(email_sender, "SMTP_USER", "")
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", "")

    with pytest.raises(email_sender.EmailNotConfiguredError):
        email_sender.send_artwork_email(
            to_email="test@example.com",
            to_first_name="Test",
            personal_url="http://example.com/s/abc",
            stimulus_label="Lettura",
            png_bytes=b"",
            filename="test.png",
        )
