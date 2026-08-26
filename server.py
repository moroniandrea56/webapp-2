"""
server.py
=========
Espone via HTTP la pipeline BrainArt (eeg_source -> signal_processing) e
serve la dashboard statica in dashboard/, così il quadro generativo e le
card mostrano metriche calcolate davvero, invece dei dati mock.

Ogni chiamata a /api/session simula una nuova lettura di un chunk EEG
(SimulatedMuseSource) e ne calcola le tre metriche con compute_metrics().
Quando arriverà il Muse reale, basterà sostituire SimulatedMuseSource con
la sorgente vera qui sotto: il resto dell'endpoint non cambia.

Esecuzione:
    pip install -r requirements.txt
    python3 server.py
    apri http://localhost:5000
"""

import random

from flask import Flask, jsonify

from eeg_source import SimulatedMuseSource
from signal_processing import compute_metrics

app = Flask(__name__, static_folder="dashboard", static_url_path="")

# In assenza di un vero testo letto durante la sessione, peschiamo una
# citazione da un piccolo archivio: nella versione reale sarà l'estratto
# effettivo del brano mostrato all'utente durante l'esperienza.
QUOTES = [
    "Mi prometto ogni tramonto che il desiderio di non lasciarsi sfuggire i momenti "
    "preziosi della vita non deve dare per scontato lo scorrere del tempo.",
    "C'è chi resta ad aspettare che il tempo cambi, e chi impara a camminare sotto "
    "la pioggia.",
    "Non è la felicità a cui devi mirare, ma l'amore con cui fai le cose.",
    "Ogni istante che lasci scorrere senza guardarlo è un istante che non torna più.",
]


def _reading_label(asymmetry, activation):
    """Etichetta sintetica dello stato durante la lettura (colore + attivazione)."""
    if activation > 0.55:
        return "ENTUSIASMO" if asymmetry >= 0 else "TENSIONE"
    return "SERENITA" if asymmetry >= 0 else "MALINCONIA"


def _pre_reading_label(activation):
    """Stato fisiologico rilevato prima ancora di iniziare la lettura."""
    if activation > 0.65:
        return "INTENSO"
    if activation > 0.35:
        return "VIGILE"
    return "CALMO"


def _post_reading_label(activation, signature):
    """Stato di chiusura, dopo l'effetto del testo sulla persona."""
    if activation < 0.35:
        return "QUIETE"
    if signature > 0.6:
        return "FLOW"
    return "EQUILIBRIO"


def build_session_payload():
    """Genera una sessione completa a partire da un chunk EEG simulato."""
    eeg = SimulatedMuseSource(seed=random.randint(0, 1_000_000))
    chunk, _state = eeg.get_chunk(n_samples=256)
    metrics = compute_metrics(chunk, eeg.CHANNELS)

    asymmetry = metrics["asymmetry"]
    activation = metrics["activation"]
    signature = metrics["signature"]

    # Stat "di corredo" derivate dalle stesse metriche, per dare corpo
    # alle card della dashboard (in un sistema reale verrebbero da un
    # secondo stream di dati, es. un sensore di battito cardiaco).
    bpm = round(62 + activation * 30)
    bpm_delta = round(asymmetry * 0.05, 2)
    minutes = round(6 + signature * 8, 1)
    flow_percent = round((signature * 0.6 + (1 - abs(asymmetry)) * 0.4) * 100)

    return {
        "asymmetry": asymmetry,
        "activation": activation,
        "signature": signature,
        "readingLabel": _reading_label(asymmetry, activation),
        "quote": random.choice(QUOTES),
        "preReading": {
            "label": _pre_reading_label(activation),
            "minutes": minutes,
            "bpm": bpm,
            "bpmDelta": bpm_delta,
        },
        "postReading": {
            "label": _post_reading_label(activation, signature),
            "flowPercent": flow_percent,
        },
    }


@app.route("/api/session")
def session():
    return jsonify(build_session_payload())


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
