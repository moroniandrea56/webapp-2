"""
server.py
=========
Espone via HTTP la pipeline BrainArt (eeg_source -> signal_processing) e
serve la dashboard statica in dashboard/.

Le sessioni sono PERSISTENTI: quando un visitatore arriva senza un id di
sessione, ne viene creata una nuova e salvata su SQLite (db.py, file
data/brainart.sqlite3) — pensato per un uso quotidiano continuativo, non
solo i picchi di un evento: a differenza di un unico file JSON riscritto
per intero a ogni sessione, SQLite scala su mesi di dati e gestisce
correttamente più operatori che scrivono nello stesso momento. Da quel
momento la sua pagina personale (/s/<id>) mostrerà sempre lo stesso
quadro, esattamente come la dashboard reale raggiunta via QR code dopo
l'evento: ricaricare o condividere il link non genera una nuova opera.
Chi aveva già un data/sessions.json da una versione precedente può
importarlo con `python3 migrate_json_to_sqlite.py`, una tantum.

La rilevazione EEG è simulata ma CONTINUA (_record_simulated_eeg): invece
di un singolo chunk istantaneo, concatena un chunk al secondo — che
SimulatedMuseSource fa ciclare tra i suoi stati mentali simulati — per
tutta la durata dell'esperienza (variabile per tipo di stimolo, vedi
DURATION_RANGES_SECONDS), e calcola le metriche sull'intera registrazione.
La durata usata diventa anche il valore "minuti" mostrato in dashboard,
invece di un numero fittizio scollegato dalla simulazione. Quando arriverà
il Muse reale, basterà sostituire SimulatedMuseSource con la sorgente vera:
il resto della pipeline non cambia.

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

Ogni sessione avviata dal pannello operatore è collegata ai dati del
partecipante (nome, cognome, email; telefono e azienda facoltativi) con
consenso privacy obbligatorio — salvati insieme alla sessione nel database
(db.py). La pagina personale del partecipante (/s/<id>) espone
solo il nome, per il saluto: gli altri dati restano visibili solo a chi
ha creato la sessione dal pannello (risposta di POST /api/session), non
sono raggiungibili da un endpoint pubblico separato.

Il pannello /admin/sessions elenca tutte le sessioni con dati cliente
salvati (filtrabili per data di creazione, comodo con un uso quotidiano
che accumula sessioni nel tempo) e permette di cancellarle (diritto di
cancellazione), oppure di inviare via email il quadro al partecipante
(richiede la configurazione SMTP in email_sender.py — se assente,
l'endpoint risponde con un errore chiaro invece di fallire in silenzio).
Titolare e contatti mostrati nell'informativa privacy si configurano con
BRAINART_DATA_CONTROLLER_NAME e BRAINART_DATA_CONTROLLER_EMAIL — il testo
in dashboard/admin.html è un MODELLO generico, da far rivedere a un
legale/DPO prima di un uso reale.

L'informativa dichiara una conservazione di BRAINART_RETENTION_MONTHS
mesi (default 12): POST /api/sessions/cleanup (admin) cancella le
sessioni più vecchie di quel periodo, rendendo vera la dichiarazione
invece che solo scritta. Gira anche una volta automaticamente a ogni
avvio del server. Per un'automazione quotidiana senza riavviare il
server, va richiamato periodicamente (cron, o un vero deployment con uno
scheduler) — qui non c'è un processo in background che lo fa da solo.

Lo stimolo che genera la sessione non è per forza una lettura: il "come
funziona" ufficiale prevede musica, degustazione, fragranza o prodotto
oltre alla lettura. Il pannello operatore lo chiede all'avvio (STIMULUS_META
sotto), e la dashboard partecipante adatta titoli ed etichette di
conseguenza.

Ogni sessione creata viene anche trasmessa via OSC (osc_sender.py) verso
BRAINART_OSC_IP:BRAINART_OSC_PORT (default 127.0.0.1:9000): se un
TouchDesigner è in ascolto su quella porta, riceve le stesse metriche in
tempo reale per una proiezione più spettacolare allo stand. Se non c'è
nessuno in ascolto, la chiamata non fa nulla (comportamento già previsto
da OSCSender).

Esecuzione:
    pip install -r requirements.txt
    export BRAINART_ADMIN_USER=... BRAINART_ADMIN_PASSWORD=...
    export BRAINART_DATA_CONTROLLER_NAME=... BRAINART_DATA_CONTROLLER_EMAIL=...
    export BRAINART_OSC_IP=... BRAINART_OSC_PORT=...   # opzionale
    export BRAINART_SMTP_HOST=... BRAINART_SMTP_USER=... BRAINART_SMTP_PASSWORD=...  # opzionale
    export BRAINART_RETENTION_MONTHS=...  # opzionale, default 12
    python3 server.py
    apri http://localhost:5000        (dashboard partecipante)
    apri http://localhost:5000/admin  (pannello operatore, richiede login)
"""

import io
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import qrcode
from flask import Flask, Response, abort, jsonify, request, send_file

import artwork_renderer
import db
import email_sender
from eeg_source import SimulatedMuseSource
from osc_sender import OSCSender
from signal_processing import compute_metrics

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__, static_folder="dashboard", static_url_path="")
# Nessuna chiamata a db.init_db() qui: lo schema si crea da solo alla prima
# connessione reale (vedi db.py), non all'import del modulo — così importare
# server.py per testarne le funzioni pure non tocca il database sul disco.

RETENTION_MONTHS = int(os.environ.get("BRAINART_RETENTION_MONTHS", "12"))

ADMIN_USERNAME = os.environ.get("BRAINART_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("BRAINART_ADMIN_PASSWORD", "brainart")
_USING_DEFAULT_ADMIN_CREDENTIALS = (
    "BRAINART_ADMIN_USER" not in os.environ or "BRAINART_ADMIN_PASSWORD" not in os.environ
)

DATA_CONTROLLER_NAME = os.environ.get("BRAINART_DATA_CONTROLLER_NAME", "[Nome azienda da configurare]")
DATA_CONTROLLER_EMAIL = os.environ.get("BRAINART_DATA_CONTROLLER_EMAIL", "privacy@example.com")

OSC_IP = os.environ.get("BRAINART_OSC_IP", "127.0.0.1")
OSC_PORT = int(os.environ.get("BRAINART_OSC_PORT", "9000"))
_osc = OSCSender(ip=OSC_IP, port=OSC_PORT)

# Il "come funziona" ufficiale prevede più tipi di stimolazione sensoriale,
# non solo la lettura: ogni voce guida i titoli e le etichette che la
# dashboard partecipante mostra per quel tipo di esperienza.
STIMULUS_META = {
    # preTitle/postTitle contengono un "\n" nel punto in cui la dashboard va
    # a capo (due righe, come nel design originale a due righe fisse).
    "lettura": {
        "label": "Lettura",
        "preTitle": "TU, ANCORA PRIMA\nDEL TESTO",
        "postTitle": "L'EFFETTO DI CIÒ\nCHE HAI LETTO",
        "tagLabel": "La tua lettura",
        "quoteCaption": "Un estratto del brano che hai letto",
        "defaultDetail": None,  # ripiega su QUOTES
    },
    "musica": {
        "label": "Musica",
        "preTitle": "TU, ANCORA PRIMA\nDELL'ASCOLTO",
        "postTitle": "L'EFFETTO DI CIÒ\nCHE HAI ASCOLTATO",
        "tagLabel": "Il tuo ascolto",
        "quoteCaption": "Il brano che hai ascoltato",
        "defaultDetail": "Un brano musicale scelto per l'esperienza.",
    },
    "degustazione": {
        "label": "Degustazione",
        "preTitle": "TU, ANCORA PRIMA\nDELL'ASSAGGIO",
        "postTitle": "L'EFFETTO DI CIÒ\nCHE HAI DEGUSTATO",
        "tagLabel": "La tua degustazione",
        "quoteCaption": "Cosa hai degustato",
        "defaultDetail": "Un prodotto degustato durante l'esperienza.",
    },
    "fragranza": {
        "label": "Fragranza",
        "preTitle": "TU, ANCORA PRIMA\nDELLA FRAGRANZA",
        "postTitle": "L'EFFETTO DI\nQUESTA FRAGRANZA",
        "tagLabel": "La tua fragranza",
        "quoteCaption": "La fragranza che hai annusato",
        "defaultDetail": "Una fragranza proposta durante l'esperienza.",
    },
    "prodotto": {
        "label": "Prodotto",
        "preTitle": "TU, ANCORA PRIMA\nDELLA PROVA",
        "postTitle": "L'EFFETTO DI\nQUESTA PROVA",
        "tagLabel": "La tua prova prodotto",
        "quoteCaption": "Il prodotto che hai provato",
        "defaultDetail": "Un prodotto provato durante l'esperienza.",
    },
}
DEFAULT_STIMULUS_TYPE = "lettura"

# Durata simulata dell'esperienza (secondi), variabile per tipo di stimolo:
# una fragranza si annusa in pochi secondi, una lettura dura minuti. Guida
# quante "secondi" di EEG simulato si concatenano in _generate_session_data().
DURATION_RANGES_SECONDS = {
    "lettura": (300, 720),
    "musica": (180, 420),
    "degustazione": (60, 240),
    "fragranza": (30, 120),
    "prodotto": (120, 300),
}

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


def _build_quadro_explanation(asymmetry, activation, signature):
    """Spiegazione del quadro basata sui valori reali della sessione (passaggio 4:
    normalmente affidato al team a voce, qui reso anche in forma scritta e
    personalizzata, invece del solo testo generico valido per chiunque)."""
    warmth = "calde (approach)" if asymmetry >= 0 else "fredde (withdrawal)"
    direction = "avvicinamento" if asymmetry >= 0 else "ritiro"
    if activation > 0.66:
        movement = "molto mosso e denso"
    elif activation > 0.33:
        movement = "moderatamente mosso"
    else:
        movement = "quasi immobile e quieto"
    lobes = 3 + round(signature * 6)

    return (
        f"Il tuo quadro ha tonalità {warmth}: la tua risposta emotiva è stata di "
        f"{direction} ({asymmetry:+.2f}). Il tratto è {movement}, coerente con "
        f"un'attivazione cerebrale del {round(activation * 100)}%. La forma ha {lobes} "
        f"lobi: è la tua firma individuale in questa sessione, diversa da quella di "
        f"chiunque altro."
    )


def _record_simulated_eeg(stimulus_type):
    """Simula una rilevazione EEG CONTINUA per tutta la durata dell'esperienza,
    invece di un singolo chunk istantaneo: concatena un chunk al secondo (che
    SimulatedMuseSource fa ciclare tra i suoi stati mentali simulati) per la
    durata scelta in base al tipo di stimolo, poi calcola le metriche
    sull'intera registrazione — più fedele a una rilevazione "in tempo reale"
    lungo tutta l'esperienza che a un'istantanea di un secondo.

    Restituisce (metrics, duration_seconds).
    """
    low, high = DURATION_RANGES_SECONDS.get(stimulus_type, DURATION_RANGES_SECONDS[DEFAULT_STIMULUS_TYPE])
    duration_seconds = random.randint(low, high)

    eeg = SimulatedMuseSource(seed=random.randint(0, 1_000_000))
    chunks = [eeg.get_chunk(n_samples=eeg.SAMPLE_RATE)[0] for _ in range(duration_seconds)]
    full_recording = np.concatenate(chunks, axis=1)

    return compute_metrics(full_recording, eeg.CHANNELS), duration_seconds


def _generate_session_data(stimulus_type=DEFAULT_STIMULUS_TYPE, stimulus_detail=""):
    """Simula una nuova sessione e ne calcola le metriche, per il tipo di
    stimolo indicato (lettura, musica, degustazione, fragranza, prodotto)."""
    metrics, duration_seconds = _record_simulated_eeg(stimulus_type)

    asymmetry = metrics["asymmetry"]
    activation = metrics["activation"]
    signature = metrics["signature"]

    # Stat "di corredo" derivate dalle stesse metriche, per dare corpo
    # alle card della dashboard (in un sistema reale verrebbero da un
    # secondo stream di dati, es. un sensore di battito cardiaco).
    bpm = round(62 + activation * 30)
    bpm_delta = round(asymmetry * 0.05, 2)
    minutes = round(duration_seconds / 60, 1)
    flow_percent = round((signature * 0.6 + (1 - abs(asymmetry)) * 0.4) * 100)

    # "un indicatore del grado di engagement associato all'interazione con
    # l'attività proposta" (sezione Scienza e Tecnologia): è la stessa
    # `activation` che guida il movimento del quadro, qui resa esplicita
    # come metrica autonoma mostrata al partecipante, non solo un input
    # nascosto della visualizzazione.
    engagement_percent = round(activation * 100)

    meta = STIMULUS_META.get(stimulus_type, STIMULUS_META[DEFAULT_STIMULUS_TYPE])
    quote = stimulus_detail.strip() if stimulus_detail else None
    if not quote:
        quote = random.choice(QUOTES) if stimulus_type == "lettura" else meta["defaultDetail"]

    # Trasmette le metriche via OSC (es. a TouchDesigner): non fa nulla se
    # nessuno è in ascolto sulla porta configurata, va bene così.
    _osc.send_metrics({"asymmetry": asymmetry, "activation": activation, "signature": signature})

    return {
        "asymmetry": asymmetry,
        "activation": activation,
        "signature": signature,
        "engagementPercent": engagement_percent,
        "readingLabel": _reading_label(asymmetry, activation),
        "quote": quote,
        "quadroExplanation": _build_quadro_explanation(asymmetry, activation, signature),
        "stimulus": {
            "type": stimulus_type,
            "label": meta["label"],
            "preTitle": meta["preTitle"],
            "postTitle": meta["postTitle"],
            "tagLabel": meta["tagLabel"],
            "quoteCaption": meta["quoteCaption"],
        },
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


def _parse_stimulus(body):
    """Legge tipo e dettaglio dello stimolo dal payload; ripiega su 'lettura'
    se assente o non riconosciuto, per restare compatibile con chi non lo invia."""
    stimulus = (body or {}).get("stimulus") or {}
    stimulus_type = stimulus.get("type") or DEFAULT_STIMULUS_TYPE
    if stimulus_type not in STIMULUS_META:
        stimulus_type = DEFAULT_STIMULUS_TYPE
    stimulus_detail = str(stimulus.get("detail", "")).strip()
    return stimulus_type, stimulus_detail


def _parse_customer(body):
    """Valida i dati del partecipante inviati dal pannello operatore.

    Restituisce (customer_dict, error_message). `customer_dict` è None se
    il payload non conteneva alcun campo cliente (es. la sessione creata
    in autonomia dalla pagina partecipante, senza passare dal pannello):
    in quel caso non si applica nessuna validazione, per non rompere quel
    flusso pubblico esistente.
    """
    customer = (body or {}).get("customer")
    if not customer:
        return None, None

    first_name = str(customer.get("firstName", "")).strip()
    last_name = str(customer.get("lastName", "")).strip()
    email = str(customer.get("email", "")).strip()
    phone = str(customer.get("phone", "")).strip()
    company = str(customer.get("company", "")).strip()
    consent = customer.get("consent") is True

    if not first_name or not last_name:
        return None, "Nome e cognome del partecipante sono obbligatori."
    if not email or not _EMAIL_RE.match(email):
        return None, "Indirizzo email del partecipante mancante o non valido."
    if not consent:
        return None, "Il consenso privacy del partecipante è obbligatorio."

    return {
        "firstName": first_name,
        "lastName": last_name,
        "email": email,
        "phone": phone,
        "company": company,
        "consent": True,
    }, None


def _get_session_or_404(session_id):
    data = db.get_session(session_id)
    if data is None:
        abort(404, description=f"Sessione '{session_id}' non trovata")
    return data


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
    is_admin_route = request.path in (
        "/admin", "/admin.html", "/admin/sessions", "/admin-sessions.html",
    )
    is_admin_api = (
        request.path.startswith("/api/qrcode/")
        or request.path == "/api/sessions"
        or request.path == "/api/sessions/cleanup"
        or (request.path.startswith("/api/session/") and request.method == "DELETE")
        or request.path.endswith("/send-email")
    )
    if not (is_admin_route or is_admin_api):
        return None

    if not _admin_authorized(request.authorization):
        return Response(
            "Accesso al pannello operatore: credenziali richieste.",
            401,
            {"WWW-Authenticate": 'Basic realm="BrainArt Admin"'},
        )
    return None


@app.route("/api/config")
def config():
    """Dati non sensibili di configurazione, usati per popolare l'informativa privacy."""
    return jsonify({
        "dataControllerName": DATA_CONTROLLER_NAME,
        "dataControllerEmail": DATA_CONTROLLER_EMAIL,
        "retentionMonths": RETENTION_MONTHS,
    })


@app.route("/api/session", methods=["POST"])
def create_session():
    """Crea una nuova sessione e la rende persistente con un id stabile.

    Se il corpo della richiesta include un oggetto "customer" (nome, cognome,
    email, consenso privacy — inviato dal form del pannello operatore), viene
    validato e salvato insieme alla sessione. Se non presente, si comporta
    come prima: nessun dato personale, nessuna validazione (lo usa anche la
    pagina partecipante per crearsi da sola una sessione al primo accesso).
    """
    body = request.get_json(silent=True)
    customer, error = _parse_customer(body)
    if error:
        return jsonify({"error": error}), 400

    stimulus_type, stimulus_detail = _parse_stimulus(body)
    payload = _generate_session_data(stimulus_type, stimulus_detail)
    payload["customer"] = customer
    payload["createdAt"] = datetime.now(timezone.utc).isoformat()
    session_id = uuid.uuid4().hex[:10]

    db.save_session(session_id, payload)

    return jsonify({**payload, "id": session_id}), 201


@app.route("/api/session/<session_id>")
def get_session(session_id):
    """Recupera una sessione già generata: la pagina resta identica ad ogni visita.

    Espone solo il nome del partecipante (per il saluto in dashboard), non
    l'intero oggetto customer: email/telefono/azienda restano visibili solo
    a chi ha creato la sessione dal pannello operatore.
    """
    data = _get_session_or_404(session_id)
    customer = data.get("customer")
    public_data = {k: v for k, v in data.items() if k != "customer"}
    public_data["firstName"] = customer["firstName"] if customer else None
    return jsonify({**public_data, "id": session_id})


@app.route("/api/sessions")
def list_sessions():
    """Elenco delle sessioni con dati cliente salvati (pannello /admin/sessions).

    Le sessioni anonime (create dalla pagina partecipante senza passare dal
    pannello, quindi senza oggetto customer) non compaiono qui: non c'è un
    "cliente" da gestire.

    Filtrabile per data di creazione con i parametri di query ?from=YYYY-MM-DD
    e/o ?to=YYYY-MM-DD (comodo con un uso quotidiano che accumula sessioni
    nel tempo, invece di scorrere sempre l'elenco intero).
    """
    date_from = request.args.get("from") or None
    date_to = request.args.get("to") or None

    sessions = db.list_sessions_with_customer(date_from=date_from, date_to=date_to)
    items = [
        {
            "id": data["id"],
            "customer": data["customer"],
            "createdAt": data.get("createdAt"),
            "readingLabel": data.get("readingLabel"),
            "engagementPercent": data.get("engagementPercent"),
            "stimulus": data.get("stimulus"),
            "emailSentAt": data.get("emailSentAt"),
        }
        for data in sessions
    ]
    return jsonify(items)


@app.route("/api/session/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Cancella definitivamente una sessione e i dati del cliente collegati.

    Copre il diritto di cancellazione (art. 17 GDPR): dopo questa chiamata
    l'id non è più risolvibile né da /s/<id> né da nessun altro endpoint.
    """
    if not db.delete_session(session_id):
        abort(404, description=f"Sessione '{session_id}' non trovata")

    return jsonify({"deleted": session_id})


@app.route("/api/sessions/cleanup", methods=["POST"])
def cleanup_old_sessions():
    """Cancella le sessioni più vecchie del periodo di conservazione dichiarato
    nell'informativa privacy (BRAINART_RETENTION_MONTHS, default 12 mesi)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_MONTHS * 30)
    deleted = db.delete_sessions_older_than(cutoff.isoformat())
    return jsonify({"deleted": deleted, "cutoff": cutoff.isoformat(), "retentionMonths": RETENTION_MONTHS})


@app.route("/api/session/<session_id>/send-email", methods=["POST"])
def send_session_email(session_id):
    """Invia via email il quadro al partecipante (richiede SMTP configurato in email_sender.py)."""
    data = _get_session_or_404(session_id)
    customer = data.get("customer")
    if not customer:
        return jsonify({"error": "Questa sessione non ha un cliente collegato."}), 400

    png_bytes = artwork_renderer.render_artwork_png_bytes(
        data["asymmetry"], data["activation"], data["signature"], size=1600
    )
    personal_url = f"{request.url_root}s/{session_id}"
    stimulus_label = (data.get("stimulus") or {}).get("label", "la tua esperienza BrainArt")

    try:
        email_sender.send_artwork_email(
            to_email=customer["email"],
            to_first_name=customer["firstName"],
            personal_url=personal_url,
            stimulus_label=stimulus_label,
            png_bytes=png_bytes,
            filename=f"brainart-{session_id}.png",
        )
    except email_sender.EmailNotConfiguredError as err:
        return jsonify({"error": str(err)}), 501
    except Exception as err:  # smtplib può sollevare più eccezioni specifiche diverse
        return jsonify({"error": f"Invio fallito: {err}"}), 502

    sent_at = datetime.now(timezone.utc).isoformat()
    db.set_email_sent(session_id, sent_at)

    return jsonify({"sent": True, "sentAt": sent_at})


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


@app.route("/admin/sessions")
def admin_sessions():
    """Pannello operatore: elenco e cancellazione delle sessioni con dati cliente."""
    return app.send_static_file("admin-sessions.html")


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
    print(f"OSC: le metriche di ogni sessione vengono inviate a {OSC_IP}:{OSC_PORT}.")
    print(
        "Email: invio del quadro "
        + ("configurato." if email_sender.smtp_configured() else
           "non configurato (imposta BRAINART_SMTP_HOST/USER/PASSWORD per attivarlo).")
    )

    _cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_MONTHS * 30)
    _deleted = db.delete_sessions_older_than(_cutoff.isoformat())
    if _deleted:
        print(f"Pulizia dati: cancellate {_deleted} sessioni più vecchie di {RETENTION_MONTHS} mesi.")

    app.run(debug=True, port=5000)
