"""
signal_processing.py
=====================
Trasforma il segnale EEG grezzo in metriche numeriche interpretabili.

Le tre metriche calcolate ricalcano quelle descritte da BrainArt:
- COLORE       -> risposta emotiva (frontal asymmetry: approach/withdrawal)
- COMPLESSITA  -> livello di attivazione cerebrale (rapporto beta+gamma / totale)
- FORMA        -> "firma" individuale (entropia spettrale, cambia da persona a persona)

Riferimento scientifico per la frontal asymmetry:
Davidson (1992) e Harmon-Jones & Gable (2017) — più alfa a sinistra rispetto
alla destra è associato a stati di "approach" (motivazione positiva),
il contrario a stati di "withdrawal".
"""

import numpy as np

BANDS = {
    "delta": (1, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta": (13, 30),
    "gamma": (30, 45),
}

SAMPLE_RATE = 256


def band_power(signal_1ch, fs=SAMPLE_RATE):
    """Calcola la potenza per ciascuna banda di frequenza su un canale."""
    n = len(signal_1ch)
    freqs = np.fft.rfftfreq(n, d=1 / fs)
    power_spectrum = np.abs(np.fft.rfft(signal_1ch)) ** 2

    powers = {}
    for band_name, (low, high) in BANDS.items():
        mask = (freqs >= low) & (freqs < high)
        powers[band_name] = float(np.sum(power_spectrum[mask]))
    return powers


def spectral_entropy(signal_1ch, fs=SAMPLE_RATE):
    """
    Misura quanto è 'complesso' / distribuito lo spettro di frequenza.
    Valori alti = energia distribuita su molte frequenze (mente più attiva/complessa)
    Valori bassi = energia concentrata in poche frequenze (stato più 'puro')
    """
    power_spectrum = np.abs(np.fft.rfft(signal_1ch)) ** 2
    power_spectrum = power_spectrum[1:]  # rimuovi componente DC
    total = np.sum(power_spectrum)
    if total <= 0:
        return 0.0
    p = power_spectrum / total
    p = p[p > 0]
    entropy = -np.sum(p * np.log2(p))
    max_entropy = np.log2(len(p)) if len(p) > 1 else 1
    return float(entropy / max_entropy)  # normalizzato 0-1


def compute_metrics(data, channel_names):
    """
    data: array (n_canali, n_campioni)
    channel_names: lista nomi canali, es. ["TP9", "AF7", "AF8", "TP10"]

    Restituisce un dizionario con le tre metriche pronte per la
    mappatura visiva, tutte normalizzate indicativamente tra -1 e 1
    (asymmetry) o 0 e 1 (le altre due).
    """
    idx = {name: i for i, name in enumerate(channel_names)}

    # --- 1. Frontal asymmetry (colore / risposta emotiva) ---
    left_power = band_power(data[idx["AF7"]])["alpha"]
    right_power = band_power(data[idx["AF8"]])["alpha"]
    # log ratio, standard in letteratura per la frontal asymmetry
    asymmetry = float(np.log(right_power + 1e-9) - np.log(left_power + 1e-9))
    asymmetry = float(np.clip(asymmetry / 3.0, -1, 1))  # normalizzato

    # --- 2. Livello di attivazione (complessità visiva) ---
    all_powers = [band_power(data[i]) for i in range(data.shape[0])]
    avg_powers = {
        band: np.mean([p[band] for p in all_powers]) for band in BANDS
    }
    total = sum(avg_powers.values()) + 1e-9
    activation = (avg_powers["beta"] + avg_powers["gamma"]) / total
    activation = float(np.clip(activation, 0, 1))

    # --- 3. Firma individuale (forma) ---
    entropies = [spectral_entropy(data[i]) for i in range(data.shape[0])]
    signature = float(np.mean(entropies))

    return {
        "asymmetry": asymmetry,   # -1 (withdrawal) .. +1 (approach)
        "activation": activation, # 0 (calmo) .. 1 (molto attivo)
        "signature": signature,   # 0 .. 1, "impronta" dell'utente
    }
