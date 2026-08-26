"""Test per le funzioni pure di server.py: soglie delle etichette di stato,
validazione dati cliente/stimolo, testo della spiegazione personalizzata.
Nessuna chiamata HTTP qui — per quelle vedi test_server_api.py."""

import server


# --- etichette di stato -------------------------------------------------------

def test_reading_label_thresholds():
    assert server._reading_label(asymmetry=0.1, activation=0.6) == "ENTUSIASMO"
    assert server._reading_label(asymmetry=-0.1, activation=0.6) == "TENSIONE"
    assert server._reading_label(asymmetry=0.1, activation=0.3) == "SERENITA"
    assert server._reading_label(asymmetry=-0.1, activation=0.3) == "MALINCONIA"


def test_pre_reading_label_thresholds():
    assert server._pre_reading_label(0.8) == "INTENSO"
    assert server._pre_reading_label(0.5) == "VIGILE"
    assert server._pre_reading_label(0.1) == "CALMO"


def test_post_reading_label_thresholds():
    assert server._post_reading_label(activation=0.2, signature=0.9) == "QUIETE"
    assert server._post_reading_label(activation=0.5, signature=0.9) == "FLOW"
    assert server._post_reading_label(activation=0.5, signature=0.3) == "EQUILIBRIO"


# --- spiegazione personalizzata del quadro -------------------------------------

def test_build_quadro_explanation_mentions_real_values():
    text = server._build_quadro_explanation(asymmetry=0.5, activation=0.5, signature=0.5)
    assert "+0.50" in text
    assert "lobi" in text
    assert "50%" in text


# --- validazione dati cliente ---------------------------------------------------

def test_parse_customer_returns_none_when_absent():
    customer, error = server._parse_customer({})
    assert customer is None
    assert error is None


def test_parse_customer_accepts_valid_data(valid_customer):
    customer, error = server._parse_customer({"customer": valid_customer})
    assert error is None
    assert customer["firstName"] == "Mario"
    assert customer["consent"] is True


def test_parse_customer_rejects_missing_name(valid_customer):
    valid_customer["firstName"] = ""
    customer, error = server._parse_customer({"customer": valid_customer})
    assert customer is None
    assert "obbligatori" in error


def test_parse_customer_rejects_invalid_email(valid_customer):
    valid_customer["email"] = "non-una-email"
    customer, error = server._parse_customer({"customer": valid_customer})
    assert customer is None
    assert "email" in error.lower()


def test_parse_customer_rejects_missing_consent(valid_customer):
    valid_customer["consent"] = False
    customer, error = server._parse_customer({"customer": valid_customer})
    assert customer is None
    assert "consenso" in error.lower()


# --- validazione tipo di stimolo -------------------------------------------------

def test_parse_stimulus_defaults_to_lettura_when_absent():
    stype, detail = server._parse_stimulus({})
    assert stype == "lettura"
    assert detail == ""


def test_parse_stimulus_accepts_known_type():
    stype, detail = server._parse_stimulus({"stimulus": {"type": "musica", "detail": "Clair de Lune"}})
    assert stype == "musica"
    assert detail == "Clair de Lune"


def test_parse_stimulus_falls_back_for_unknown_type():
    stype, _ = server._parse_stimulus({"stimulus": {"type": "sconosciuto"}})
    assert stype == "lettura"


# --- rilevazione EEG simulata continua -------------------------------------------

def test_record_simulated_eeg_duration_matches_stimulus_range():
    low, high = server.DURATION_RANGES_SECONDS["fragranza"]
    metrics, duration = server._record_simulated_eeg("fragranza")
    assert low <= duration <= high
    assert set(metrics.keys()) == {"asymmetry", "activation", "signature"}
