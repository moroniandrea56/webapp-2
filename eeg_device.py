"""
eeg_device.py
=============
Impalcatura per collegare un dispositivo Bluetooth reale (bracciale o
headband EEG) alla pipeline, senza ancora sapere quale modello verrà
scelto.

EEGSource formalizza il contratto che SimulatedMuseSource (eeg_source.py)
già rispetta: CHANNELS, SAMPLE_RATE, get_chunk(n_samples) -> (data, state).
Quando il dispositivo sarà scelto, BluetoothEEGSource va completato con il
suo protocollo specifico (UUID del servizio/caratteristica BLE, formato dei
byte trasmessi) — il resto della pipeline (signal_processing.py in poi) non
cambia, perché lavora solo sull'array numpy restituito da get_chunk(), non
sa se la sorgente è simulata o reale.

list_bluetooth_devices() invece FUNZIONA GIÀ ORA: fa una scansione
Bluetooth reale (libreria bleak) per elencare i dispositivi nelle
vicinanze — utile per verificare che il bracciale sia visibile e trovarne
nome/indirizzo, prima ancora di sapere come leggerne i dati.

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


class BluetoothEEGSource(EEGSource):
    """Scaffold per il dispositivo reale — DA COMPLETARE quando sarà scelto.

    Passi per completarlo:
      1. Esegui list_bluetooth_devices() (o `python3 scan_devices.py`) col
         bracciale acceso e vicino: annota il suo 'address' (o il nome, se
         stabile).
      2. Nella documentazione del produttore, trova l'UUID del servizio e
         della caratteristica BLE che trasmettono i dati EEG grezzi, e il
         formato dei byte (quanti canali, bit per campione, ordine).
      3. Riempi CHANNELS e SAMPLE_RATE con i valori reali del dispositivo
         scelto (sostituendo quelli di SimulatedMuseSource in eeg_source.py
         ovunque vengano letti, es. server.py).
      4. In connect(), usa bleak.BleakClient per connetterti a self.address
         e sottoscriverti alla caratteristica; in get_chunk(), accumula i
         byte ricevuti finché non hai n_samples campioni per canale, poi
         convertili in un array numpy (n_canali, n_samples) — stesso
         formato restituito da SimulatedMuseSource.get_chunk().
    """

    CHANNELS = []       # TODO: nomi dei canali del dispositivo scelto
    SAMPLE_RATE = None  # TODO: frequenza di campionamento del dispositivo scelto

    def __init__(self, address):
        self.address = address
        self._client = None

    def connect(self):
        raise NotImplementedError(
            "BluetoothEEGSource non è ancora collegato a un dispositivo specifico. "
            "Vedi la docstring della classe per i passi da completare."
        )

    def disconnect(self):
        raise NotImplementedError

    def get_chunk(self, n_samples):
        raise NotImplementedError(
            "BluetoothEEGSource.get_chunk() va implementato per il protocollo "
            "del dispositivo scelto. Vedi la docstring della classe."
        )
