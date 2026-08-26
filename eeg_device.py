"""
eeg_device.py
=============
EEGSource formalizza il contratto comune a qualunque sorgente EEG, simulata
o reale: CHANNELS, SAMPLE_RATE, get_chunk(n_samples) -> (data, state). Lo
rispettano sia SimulatedMuseSource (eeg_source.py, dati finti) sia
MuseEEGSource (muse_source.py, dati REALI letti via Bluetooth da un
bracciale/cuffiette Muse) — il resto della pipeline (signal_processing.py
in poi) non cambia, perché lavora solo sull'array numpy restituito da
get_chunk(), non sa se la sorgente è simulata o reale.

list_bluetooth_devices() fa una scansione Bluetooth reale (libreria bleak)
per elencare i dispositivi nelle vicinanze — utile per verificare che il
bracciale sia visibile e trovarne l'indirizzo, da usare come
BRAINART_MUSE_ADDRESS (vedi server.py e muse_source.py).

ESEGUIBILE SOLO SU UNA MACCHINA CON BLUETOOTH FISICO: in un container
cloud senza radio Bluetooth (come l'ambiente in cui questo codice è stato
scritto) la scansione non troverà nulla o segnalerà l'assenza di un
adattatore — va provato sul tuo computer, con il bracciale acceso e
vicino. Vedi anche scan_devices.py per un piccolo comando pronto all'uso.
"""

import asyncio
from abc import ABC, abstractmethod


class EEGSource(ABC):
    """Contratto comune a qualunque sorgente EEG, simulata o reale."""

    CHANNELS = []
    SAMPLE_RATE = None

    @abstractmethod
    def get_chunk(self, n_samples):
        """Restituisce (data, state).

        data: array numpy di forma (n_canali, n_samples), stesso formato
        per qualunque sorgente. state: etichetta opzionale (str o None) —
        ha senso solo per sorgenti simulate; una sorgente reale può
        restituire sempre None.
        """
        raise NotImplementedError


async def _scan_async(timeout):
    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=timeout)
    return [
        {
            "name": device.name or "(senza nome)",
            "address": device.address,
            "rssi": getattr(device, "rssi", None),
        }
        for device in devices
    ]


def list_bluetooth_devices(timeout=5.0):
    """Scansiona i dispositivi Bluetooth Low Energy nelle vicinanze.

    Restituisce una lista di dict {name, address, rssi}. Richiede la
    libreria 'bleak' (in requirements.txt) e un adattatore Bluetooth reale
    attivo sulla macchina che esegue lo script. Solleva RuntimeError con un
    messaggio comprensibile se bleak non è installato o se non c'è nessun
    adattatore Bluetooth disponibile (es. in un container cloud).
    """
    try:
        return asyncio.run(_scan_async(timeout))
    except ImportError as err:
        raise RuntimeError("Libreria 'bleak' non installata: esegui 'pip install bleak'.") from err
    except Exception as err:
        raise RuntimeError(
            f"Scansione Bluetooth non riuscita ({err}). Verifica che il Bluetooth "
            "del computer sia attivo: questa funzione richiede un adattatore fisico, "
            "non funziona in un ambiente cloud senza radio Bluetooth."
        ) from err
