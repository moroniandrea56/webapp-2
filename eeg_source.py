"""
eeg_source.py
=============
Sorgente dati EEG. In questo prototipo i dati sono SIMULATI, ma la funzione
get_chunk() ha la stessa "forma" (stessa interfaccia) che avrà quando
collegherai un dispositivo reale via Bluetooth.

SimulatedMuseSource implementa EEGSource (eeg_device.py), il contratto
comune a qualunque sorgente EEG: quando il dispositivo reale sarà scelto,
la nuova classe che lo legge (BluetoothEEGSource, già abbozzata in
eeg_device.py) rispetterà lo stesso contratto — il resto della pipeline
(signal processing, mappatura visiva, invio OSC) NON cambia.

Canali simulati: TP9, AF7, AF8, TP10 (gli stessi 4 elettrodi del Muse,
due frontali e due temporali — servono per calcolare la "frontal asymmetry").
Se il dispositivo scelto avrà canali diversi, andranno aggiornati qui.
"""

import numpy as np

from eeg_device import EEGSource


class SimulatedMuseSource(EEGSource):
    """
    Genera un flusso continuo di dati EEG plausibili, con "stati mentali"
    che cambiano nel tempo per rendere il test più realistico
    (es. una fase più rilassata, poi una più attiva/eccitata).
    """

    CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
    SAMPLE_RATE = 256  # Hz, tipico per il Muse

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        # Definiamo alcune "fasi" simulate che si alternano nel tempo,
        # per simulare la reazione della mente a uno stimolo che cambia.
        # Usiamo il tempo SIMULATO (self.t, basato sui campioni generati)
        # e non l'orologio reale: così il ciclo di stati è coerente sia
        # in tempo reale sia quando si genera velocemente un video demo.
        self._current_state = "neutro"

    def _mental_state(self, elapsed):
        """Cambia stato simulato ogni ~4 secondi (di audio simulato), in un ciclo."""
        cycle = int(elapsed // 4) % 3
        return ["neutro", "rilassato", "attivato"][cycle]

    def get_chunk(self, n_samples=256):
        """
        Restituisce un chunk di dati EEG grezzi.
        Shape: (n_canali, n_samples)

        Nella versione reale con Muse + BrainFlow, questa funzione
        verrà sostituita da una lettura del buffer BrainFlow, ma il
        formato restituito resterà lo stesso: un array (4, n_samples).
        """
        state = self._mental_state(self.t)

        fs = self.SAMPLE_RATE
        t = np.arange(n_samples) / fs + self.t
        self.t += n_samples / fs

        # Ampiezze di base per ciascuna banda (delta, theta, alpha, beta, gamma)
        # variano a seconda dello stato mentale simulato
        band_amplitudes = {
            "neutro":    dict(delta=1.0, theta=1.0, alpha=1.2, beta=1.0, gamma=0.5),
            "rilassato": dict(delta=0.8, theta=1.2, alpha=2.0, beta=0.6, gamma=0.3),
            "attivato":  dict(delta=0.6, theta=0.7, alpha=0.8, beta=2.2, gamma=1.5),
        }[state]

        band_freqs = dict(delta=2, theta=6, alpha=10, beta=20, gamma=40)

        data = np.zeros((len(self.CHANNELS), n_samples))
        for ch_idx, ch_name in enumerate(self.CHANNELS):
            signal = np.zeros(n_samples)
            for band, amp in band_amplitudes.items():
                freq = band_freqs[band]
                phase = self.rng.uniform(0, 2 * np.pi)
                # leggera asimmetria emisferica per rendere interessante
                # il calcolo della frontal asymmetry (AF7 = sinistra, AF8 = destra)
                side_bias = 1.0
                if ch_name == "AF7":
                    side_bias = 1.0 + (0.3 if state == "attivato" else -0.1)
                elif ch_name == "AF8":
                    side_bias = 1.0 + (-0.2 if state == "attivato" else 0.2)
                signal += amp * side_bias * np.sin(2 * np.pi * freq * t + phase)
            noise = self.rng.normal(0, 0.5, n_samples)
            data[ch_idx] = signal + noise

        return data, state
