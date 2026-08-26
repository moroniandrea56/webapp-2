"""
db.py
=====
Storage delle sessioni su SQLite, al posto del singolo file
data/sessions.json che veniva riscritto per intero a ogni lettura/
scrittura. Pensato per un uso quotidiano continuativo (non solo i picchi
di un evento): SQLite gestisce correttamente più scritture concorrenti e
non rallenta man mano che le sessioni si accumulano nei mesi.

Il payload "ricco" di ogni sessione (metriche, stimolo, preReading,
postReading, quote, spiegazione del quadro...) resta un blob JSON in
un'unica colonna: la sua struttura interna è identica a quella già
prodotta da server._generate_session_data(), quindi il resto del codice
non deve cambiare. Solo i campi su cui serve davvero filtrare/cercare
(data di creazione, nome/email del cliente) diventano colonne SQL
indicizzate.

Ogni funzione apre una connessione, fa il suo lavoro e la chiude: niente
connessione condivisa cache-ata, per restare semplice, corretta sotto più
thread, e facile da isolare nei test (basta cambiare DB_PATH prima della
chiamata — nessun ordine di inizializzazione da rispettare, vedi sotto).

La creazione dello schema (CREATE TABLE/INDEX IF NOT EXISTS) avviene a
ogni apertura di connessione, non con un init_db() separato da ricordarsi
di chiamare per primo: è idempotente e costa pochissimo, ma evita ogni
dipendenza dall'ordine con cui l'app o i test toccano il database (e
soprattutto: importare server.py per testarne le funzioni pure non deve,
da solo, creare il file del database reale).
"""

import json
import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "brainart.sqlite3")

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        customer_first_name TEXT,
        customer_last_name TEXT,
        customer_email TEXT,
        customer_company TEXT,
        email_sent_at TEXT,
        data TEXT NOT NULL
    )
"""


@contextmanager
def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")  # migliori scritture concorrenti
    conn.execute(_SCHEMA_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_customer_email ON sessions(customer_email)")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Forza la creazione dello schema senza fare altro. Non è più
    necessario chiamarla prima di usare le altre funzioni (lo schema si
    crea comunque alla prima connessione), ma resta comoda per un avvio
    esplicito (es. migrate_json_to_sqlite.py, i test)."""
    with get_connection():
        pass


def save_session(session_id, payload):
    """Salva una nuova sessione (o sovrascrive, se l'id esiste già).

    payload è il dict completo prodotto da server._generate_session_data(),
    con "customer" e "createdAt" già uniti — stessa forma già usata prima
    di questa migrazione, per non dover cambiare il resto di server.py.
    """
    customer = payload.get("customer") or {}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, created_at, customer_first_name, customer_last_name,
                                   customer_email, customer_company, email_sent_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                created_at=excluded.created_at,
                customer_first_name=excluded.customer_first_name,
                customer_last_name=excluded.customer_last_name,
                customer_email=excluded.customer_email,
                customer_company=excluded.customer_company,
                email_sent_at=excluded.email_sent_at,
                data=excluded.data
            """,
            (
                session_id,
                payload.get("createdAt"),
                customer.get("firstName"),
                customer.get("lastName"),
                customer.get("email"),
                customer.get("company"),
                payload.get("emailSentAt"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )


def get_session(session_id):
    """Restituisce il payload della sessione (senza "id", come nel vecchio
    formato), o None se non esiste."""
    with get_connection() as conn:
        row = conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def delete_session(session_id):
    """Cancella una sessione. Restituisce True se esisteva ed è stata cancellata."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return cur.rowcount > 0


def set_email_sent(session_id, sent_at):
    """Segna una sessione come 'quadro inviato via email il...'. Restituisce
    True se la sessione esisteva."""
    with get_connection() as conn:
        row = conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return False
        payload = json.loads(row["data"])
        payload["emailSentAt"] = sent_at
        conn.execute(
            "UPDATE sessions SET email_sent_at = ?, data = ? WHERE id = ?",
            (sent_at, json.dumps(payload, ensure_ascii=False), session_id),
        )
    return True


def list_sessions_with_customer(date_from=None, date_to=None):
    """Sessioni che hanno un cliente collegato (per /admin/sessions), più
    recenti prima. date_from/date_to sono stringhe 'YYYY-MM-DD': se
    indicate, filtrano per data di creazione (confronto lessicografico su
    stringhe ISO 8601, corretto perché created_at è sempre in quel formato).

    Ogni elemento restituito è il payload completo con "id" incluso.
    """
    query = "SELECT id, data FROM sessions WHERE customer_first_name IS NOT NULL"
    params = []
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to + "T23:59:59.999999+00:00")
    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{**json.loads(row["data"]), "id": row["id"]} for row in rows]


def delete_sessions_older_than(cutoff_iso):
    """Cancella tutte le sessioni create prima di cutoff_iso (stringa ISO
    8601). Usata per la pulizia automatica dei dati oltre il periodo di
    conservazione dichiarato nell'informativa privacy. Restituisce quante
    ne ha cancellate."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff_iso,))
    return cur.rowcount
