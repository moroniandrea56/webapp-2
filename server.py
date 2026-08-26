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

Il pannello operatore (/admin) è pensato per lo staff durante l'evento: un
tasto "nuova sessione" genera l'id, e /api/qrcode/<id> ne renderizza il QR
già puntato alla pagina personale, pronto da mostrare o stampare per il
partecipante. Il pannello e il suo endpoint QR sono protetti da HTTP Basic
Auth: le credenziali si impostano con le variabili d'ambiente
BRAINART_ADMIN_USER e BRAINART_ADMIN_PASSWORD (senza, valgono i default
"admin"/"brainart", validi solo per lo sviluppo locale — cambiali prima di
usare questo prototipo a un evento reale).

Il funzionamento BrainArt descritto sul sito prevede 6 passaggi; questo
server copre digitalmente il 2° e 3° (rilevazione onde cerebrali ->
elaborazione/visualizzazione, via eeg_source.py + signal_processing.py) e
ora anche il 5° e 6°:
  - /api/artwork/<id>.png  -> il quadro renderizzato ad alta risoluzione
    (artwork_renderer.py), indipendente dallo schermo del partecipante:
    è il file da mandare in stampa o da consegnare per i social.
  - /s/<id>/print           -> pagina pronta per la stampa in loco, con lo
    stesso file ad alta risoluzione impaginato per un pieghevole.
Il 1° (stimolazione sensoriale) e il 4° (spiegazione a voce del quadro)
restano passaggi condotti dal team durante l'evento, non digitali.

Esecuzione:
    pip install -r requirements.txt
    export BRAINART_ADMIN_USER=... BRAINART_ADMIN_PASSWORD=...
    python3 server.py
    apri http://localhost:5000       (dashboard partecipante)
    apri http://localhost:5000/admin (pannello operatore, richiede login)
"""

import io
import json
import os
import random
import threading
import uuid

import qrcode
from flask import Flask, Response, abort, jsonify, request, send_file

import artwork_renderer
from eeg_source import SimulatedMuseSource
from signal_processing import compute_metrics

app = Flask(__name__, static_folder="dashboard", static_url_path="")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
_sessions_lock = threading.Lock()

ADMIN_USERNAME = os.environ.get("BRAINART_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("BRAINART_ADMIN_PASSWORD", "brainart")
_USING_DEFAULT_ADMIN_CREDENTIALS = (
    "BRAINART_ADMIN_USER" not in os.environ or "BRAINART_ADMIN_PASSWORD" not in os.environ
)

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


def _get_session_or_404(session_id):
    with _sessions_lock:
        sessions = _load_sessions()
    if session_id not in sessions:
        abort(404, description=f"Sessione '{session_id}' non trovata")
    return sessions[session_id]


def _admin_authorized(auth):
    return (
        auth is not None
        and auth.username == ADMIN_USERNAME
        and auth.password == ADMIN_PASSWORD
    )


@app.before_request
def _require_admin_login():
    """Protegge il pannello operatore e il suo endpoint QR con HTTP Basic Auth.

    La dashboard partecipante (/, /s/<id>, /api/session) resta pubblica: la
    protezione riguarda solo la superficie usata dallo staff dell'evento.
    """
    is_admin_route = request.path == "/admin" or request.path == "/admin.html"
    is_admin_api = request.path.startswith("/api/qrcode/")
    if not (is_admin_route or is_admin_api):
        return None

    if not _admin_authorized(request.authorization):
        return Response(
            "Accesso al pannello operatore: credenziali richieste.",
            401,
            {"WWW-Authenticate": 'Basic realm="BrainArt Admin"'},
        )
    return None


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
    data = _get_session_or_404(session_id)
    return jsonify({**data, "id": session_id})


@app.route("/api/qrcode/<session_id>")
def session_qrcode(session_id):
    """Genera al volo il QR code che punta alla pagina personale della sessione."""
    _get_session_or_404(session_id)

    url = f"{request.url_root}s/{session_id}"
    img = qrcode.make(url, border=2)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.route("/api/artwork/<session_id>.png")
def session_artwork(session_id):
    """Il quadro renderizzato ad alta risoluzione (passaggio 5 e 6: stampa e download social).

    A differenza dello screenshot del canvas del browser, questo file ha
    qualità e risoluzione costanti indipendentemente dal dispositivo del
    partecipante, ed è ciò che il QR code dovrebbe davvero consegnare.
    """
    data = _get_session_or_404(session_id)
    png_bytes = artwork_renderer.render_artwork_png_bytes(
        data["asymmetry"], data["activation"], data["signature"], size=1600
    )
    return send_file(
        io.BytesIO(png_bytes),
        mimetype="image/png",
        download_name=f"brainart-{session_id}.png",
    )


@app.errorhandler(404)
def handle_404(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": str(error.description)}), 404
    return error


@app.route("/s/<session_id>")
def dashboard_for_session(session_id):
    """Serve la pagina statica: l'id viene letto lato client dall'URL."""
    return app.send_static_file("index.html")


@app.route("/s/<session_id>/print")
def print_session(session_id):
    """Pagina pronta per la stampa in loco (passaggio 5): l'id viene letto lato client."""
    return app.send_static_file("print.html")


@app.route("/admin")
def admin():
    """Pannello operatore: avvia nuove sessioni e distribuisce il relativo QR code."""
    return app.send_static_file("admin.html")


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    if _USING_DEFAULT_ADMIN_CREDENTIALS:
        print(
            "ATTENZIONE: /admin usa le credenziali di default (admin / brainart). "
            "Impostale con BRAINART_ADMIN_USER e BRAINART_ADMIN_PASSWORD prima di "
            "usare questo prototipo a un evento reale."
        )
    app.run(debug=True, port=5000)
