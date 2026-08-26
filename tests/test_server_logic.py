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
    stype, detail, duration = server._parse_stimulus({})
    assert stype == "lettura"
    assert detail == ""
    assert duration is None


def test_parse_stimulus_accepts_known_type():
    stype, detail, _ = server._parse_stimulus({"stimulus": {"type": "musica", "detail": "Clair de Lune"}})
    assert stype == "musica"
    assert detail == "Clair de Lune"


def test_parse_stimulus_falls_back_for_unknown_type():
    stype, _, _ = server._parse_stimulus({"stimulus": {"type": "sconosciuto"}})
    assert stype == "lettura"


def test_parse_stimulus_accepts_explicit_duration():
    _, _, duration = server._parse_stimulus({"stimulus": {"durationSeconds": 90}})
    assert duration == 90


def test_parse_stimulus_clamps_duration_to_valid_range():
    _, _, too_short = server._parse_stimulus({"stimulus": {"durationSeconds": 1}})
    assert too_short == server.MIN_DURATION_SECONDS

    _, _, too_long = server._parse_stimulus({"stimulus": {"durationSeconds": 100000}})
    assert too_long == server.MAX_DURATION_SECONDS


def test_parse_stimulus_ignores_invalid_duration():
    _, _, duration = server._parse_stimulus({"stimulus": {"durationSeconds": "non-un-numero"}})
    assert duration is None


# --- rilevazione EEG continua (simulata di default) -------------------------------

def test_record_eeg_duration_matches_stimulus_range():
    low, high = server.DURATION_RANGES_SECONDS["fragranza"]
    metrics, duration = server._record_eeg("fragranza")
    assert low <= duration <= high
    assert set(metrics.keys()) == {"asymmetry", "activation", "signature"}


def test_record_eeg_honors_explicit_duration():
    _, duration = server._record_eeg("lettura", duration_seconds=15)
    assert duration == 15


def test_record_eeg_ignores_real_device_flag_when_source_is_simulated():
    # BRAINART_EEG_SOURCE non è "muse" nell'ambiente di test: anche chiedendo
    # real_device=True deve restare sulla sorgente simulata, non tentare una
    # connessione Bluetooth reale (che fallirebbe comunque in CI).
    metrics, duration = server._record_eeg("lettura", duration_seconds=5, real_device=True)
    assert duration == 5
    assert set(metrics.keys()) == {"asymmetry", "activation", "signature"}


def test_record_eeg_requires_muse_address_when_source_is_muse(monkeypatch):
    monkeypatch.setattr(server, "EEG_SOURCE_MODE", "muse")
    monkeypatch.setattr(server, "MUSE_ADDRESS", None)
    try:
        server._record_eeg("lettura", duration_seconds=5, real_device=True)
        assert False, "doveva sollevare RuntimeError senza BRAINART_MUSE_ADDRESS"
    except RuntimeError as err:
        assert "BRAINART_MUSE_ADDRESS" in str(err)
