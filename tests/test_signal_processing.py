"""Test per signal_processing.py: metriche calcolate da segnali sintetici noti,
non da rumore casuale, così i risultati attesi sono verificabili."""

import numpy as np

from signal_processing import band_power, compute_metrics, spectral_entropy

FS = 256
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]


def _sine(freq, n_samples=512, fs=FS, amplitude=1.0):
    t = np.arange(n_samples) / fs
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_band_power_concentrates_energy_in_expected_band():
    alpha_signal = _sine(10)  # 10 Hz è dentro la banda alpha (8-13 Hz)
    powers = band_power(alpha_signal)
    assert powers["alpha"] > powers["delta"]
    assert powers["alpha"] > powers["beta"]
    assert powers["alpha"] > powers["gamma"]


def test_spectral_entropy_pure_tone_is_lower_than_white_noise():
    pure_tone = _sine(10, n_samples=1024)
    entropy_pure = spectral_entropy(pure_tone)

    rng = np.random.default_rng(0)
    white_noise = rng.normal(0, 1, 1024)
    entropy_noise = spectral_entropy(white_noise)

    assert 0 <= entropy_pure <= 1
    assert entropy_pure < entropy_noise


def test_spectral_entropy_silence_is_zero():
    assert spectral_entropy(np.zeros(256)) == 0.0


def test_compute_metrics_returns_expected_keys_and_ranges():
    rng = np.random.default_rng(1)
    data = rng.normal(0, 1, (4, 512))

    metrics = compute_metrics(data, CHANNELS)

    assert set(metrics.keys()) == {"asymmetry", "activation", "signature"}
    assert -1 <= metrics["asymmetry"] <= 1
    assert 0 <= metrics["activation"] <= 1
    assert 0 <= metrics["signature"] <= 1


def test_compute_metrics_asymmetry_sign_follows_dominant_hemisphere():
    n = 512
    silence = np.zeros(n)
    strong_alpha = _sine(10, n_samples=n, amplitude=5.0)
    weak_alpha = _sine(10, n_samples=n, amplitude=0.1)

    # più alpha a destra (AF8) che a sinistra (AF7) -> asymmetry positiva (approach)
    data_right_dominant = np.array([silence, weak_alpha, strong_alpha, silence])
    assert compute_metrics(data_right_dominant, CHANNELS)["asymmetry"] > 0

    # il contrario -> asymmetry negativa (withdrawal)
    data_left_dominant = np.array([silence, strong_alpha, weak_alpha, silence])
    assert compute_metrics(data_left_dominant, CHANNELS)["asymmetry"] < 0
