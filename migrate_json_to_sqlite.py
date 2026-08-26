"""
migrate_json_to_sqlite.py
==========================
Importa le sessioni salvate nel vecchio formato (data/sessions.json) nel
nuovo storage SQLite (db.py). Va eseguito UNA SOLA VOLTA, solo se esiste
già un data/sessions.json da prima di questa migrazione — un'installazione
nuova non ne ha bisogno.

Il vecchio file, dopo l'importazione, viene rinominato in
data/sessions.json.migrated (non cancellato) così resta una copia di
sicurezza, ma non verrà più letto da nessuna parte del codice.

Esecuzione:
    python3 migrate_json_to_sqlite.py
"""

import json
import os

import db

OLD_SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions.json")


def main():
    if not os.path.exists(OLD_SESSIONS_FILE):
        print("Nessun data/sessions.json trovato: niente da migrare.")
        return

    with open(OLD_SESSIONS_FILE, "r", encoding="utf-8") as f:
        old_sessions = json.load(f)

    db.init_db()
    for session_id, payload in old_sessions.items():
        db.save_session(session_id, payload)

    print(f"Migrate {len(old_sessions)} sessioni in {db.DB_PATH}.")

    backup_path = OLD_SESSIONS_FILE + ".migrated"
    os.rename(OLD_SESSIONS_FILE, backup_path)
    print(f"Il vecchio file è stato rinominato in {backup_path} (non verrà più letto).")


if __name__ == "__main__":
    main()
