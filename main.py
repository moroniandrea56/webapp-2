"""
main.py
=======
Prototipo BrainArt-style: collega tutta la pipeline.

    EEG (simulato) -> elaborazione segnale -> metriche
        -> invio OSC (per TouchDesigner, opzionale)
        -> visualizzazione generativa in tempo reale

COME EVOLVERLO QUANDO ARRIVA IL MUSE:
Dovrai solo sostituire SimulatedMuseSource con una classe che legge dati
veri (tramite la libreria BrainFlow, che supporta il Muse nativamente).
Tutto il resto — signal_processing.py, osc_sender.py, visual_engine.py —
resta identico, perché lavorano solo sui numeri (array a 4 canali),
non sanno se i dati sono veri o simulati.

Esecuzione:
    python3 main.py              # apre una finestra interattiva
    python3 main.py --save       # salva un video mp4/gif di prova (utile
                                  # in ambienti senza interfaccia grafica)
"""

import os
import sys

from eeg_source import SimulatedMuseSource
from signal_processing import compute_metrics
from osc_sender import OSCSender
from visual_engine import BrainArtVisualizer


def main():
    save_mode = "--save" in sys.argv

    eeg = SimulatedMuseSource(seed=42)
    osc = OSCSender(ip="127.0.0.1", port=9000)  # TouchDesigner ascolterà qui
    viz = BrainArtVisualizer()

    def get_current_metrics():
        chunk, state = eeg.get_chunk(n_samples=256)
        metrics = compute_metrics(chunk, eeg.CHANNELS)
        osc.send_metrics(metrics)  # non fa nulla se nessuno ascolta, va bene così
        print(
            f"stato simulato: {state:10s} | "
            f"asymmetry: {metrics['asymmetry']:+.2f} | "
            f"activation: {metrics['activation']:.2f} | "
            f"signature: {metrics['signature']:.2f}"
        )
        return metrics

    if save_mode:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        save_path = os.path.join(output_dir, "brainart_demo.gif")
        viz.run(get_current_metrics, interval_ms=100, n_frames=150,
                 save_path=save_path)
    else:
        viz.run(get_current_metrics, interval_ms=50)


if __name__ == "__main__":
    main()
