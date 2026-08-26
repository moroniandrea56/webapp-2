"""
server.py
=========
Espone via HTTP la pipeline BrainArt (eeg_source -> signal_processing) e
serve la dashboard statica in dashboard/.

Le sessioni sono PERSISTENTI: quando un visitatore arriva senza un id di
sessione, ne viene creata una nuova (un chunk EEG viene simulato e ridotto
a metriche una sola volta) e salvata su disco in data/sessions.json. Da
quel momento la sua pagina personale (/s/<id>) mostrerà sempre lo stesso
quadro, esattamente come la dashboard reale raggiunta via QR code dopo
l'evento: ricaricare o condividere il link non genera una nuova opera.

Quando arriverà il Muse reale, basterà sostituire SimulatedMuseSource con
la sorgente vera in _generate_session_data(): il resto dell'endpoint non
cambia.

Esecuzione:
    pip install -r requirements.txt
    python3 server.py
    apri http://localhost:5000
"""

import json
import os
import random
import threading
import uuid

from flask import Flask, abort, jsonify, request

from eeg_source import SimulatedMuseSource
from signal_processing import compute_metrics

app = Flask(__name__, static_folder="dashboard", static_url_path="")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
_sessions_lock = threading.Lock()

QUOTES = [
    "Mi prometto ogni tramonto che il desiderio di non lasciarsi sfuggire i momenti "
    "preziosi della vita non deve dare per scontato lo scorrere del tempo.",
    "C'è chi resta ad aspettare che il tempo cambi, e chi impara a camminare sotto "
    "la pioggia.",
    "Non è la felicità a cui devi mirare, ma l'amore con cui fai le cose.",
    "Ogni istante che lasci scorrere senza guardarlo è un istante che non torna più.",
]


def _load_sessions():
    if not os.path.exists(SESSIONS_FILE):
        return {}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_sessions(sessions):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


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


def _generate_session_data():
    """Simula una nuova sessione di lettura e ne calcola le metriche."""
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


@app.route("/api/session", methods=["POST"])
def create_session():
    """Crea una nuova sessione e la rende persistente con un id stabile."""
    payload = _generate_session_data()
    session_id = uuid.uuid4().hex[:10]

    with _sessions_lock:
        sessions = _load_sessions()
        sessions[session_id] = payload
        _save_sessions(sessions)

    return jsonify({**payload, "id": session_id}), 201


@app.route("/api/session/<session_id>")
def get_session(session_id):
    """Recupera una sessione già generata: la pagina resta identica ad ogni visita."""
    with _sessions_lock:
        sessions = _load_sessions()

    if session_id not in sessions:
        abort(404, description=f"Sessione '{session_id}' non trovata")

    return jsonify({**sessions[session_id], "id": session_id})


@app.errorhandler(404)
def handle_404(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(error.description)}), 404
    return error


@app.route("/s/<session_id>")
def dashboard_for_session(session_id):
    """Serve la pagina statica: l'id viene letto lato client dall'URL."""
    return app.send_static_file("index.html")


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
