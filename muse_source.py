"""
muse_source.py
===============
Sorgente EEG REALE per bracciali/cuffiette Muse (2016, Muse 2, Muse S) via
Bluetooth Low Energy, con la libreria bleak (già usata per la scansione in
eeg_device.py).

Implementa il protocollo BLE del Muse — UUID del servizio di controllo e
delle quattro caratteristiche EEG, comando testuale per avviare/fermare lo
stream, formato a 12 bit dei campioni — che è lo stesso usato pubblicamente
da progetti come muse-lsl e muse-js: non è specifico di questo prototipo,
è come il dispositivo parla via Bluetooth a qualunque software lo legga.

MuseEEGSource rispetta il contratto EEGSource (eeg_device.py): stessi
CHANNELS di SimulatedMuseSource (TP9, AF7, AF8, TP10), get_chunk(n_samples)
-> (data, state) con state sempre None (non c'è uno "stato mentale
simulato" da restituire, il segnale è quello vero). Il resto della
pipeline (signal_processing.py) non sa e non deve sapere da dove vengono
i dati.

NON TESTABILE in un ambiente senza Bluetooth fisico (come il container
cloud in cui questo codice è stato scritto): va provato sul tuo Mac con il
Muse acceso, indossato e vicino. La decodifica dei bit (_unpack_eeg_channel)
è invece pura matematica e viene verificata con dati sintetici in
tests/test_muse_source.py, senza bisogno di hardware.

Se il dispositivo non risponde in tempo o la connessione cade, get_chunk()
solleva RuntimeError con un messaggio comprensibile invece di restituire
dati finti: chi usa il pannello operatore deve saperlo subito, non ricevere
un quadro basato su una lettura fallita.
"""

import asyncio
import time

import numpy as np

from eeg_device import EEGSource

# UUID standard del servizio di controllo e delle quattro caratteristiche EEG
# del Muse: stessi per ogni bracciale Muse, non dipendono dall'esemplare.
_CONTROL_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
_EEG_UUIDS = {
    "TP9": "273e0003-4c4d-454d-96be-f03bac821358",
    "AF7": "273e0004-4c4d-454d-96be-f03bac821358",
    "AF8": "273e0005-4c4d-454d-96be-f03bac821358",
    "TP10": "273e0006-4c4d-454d-96be-f03bac821358",
}

_SAMPLES_PER_PACKET = 12
# 12 bit per campione su un range di 2 mVpp: 2000 microvolt / 4096 livelli.
_MICROVOLTS_PER_COUNT = 0.48828125


def _unpack_eeg_channel(packet):
    """Decodifica un pacchetto BLE di un canale EEG del Muse.

    Formato (20 byte): 2 byte di indice pacchetto (uint16 big-endian) + 18
    byte contenenti 12 campioni impacchettati a 12 bit ciascuno (144 bit),
    MSB-first, senza allineamento a byte tra un campione e il successivo.

    Restituisce (indice_pacchetto, array numpy di 12 campioni in microvolt).
    """
    packet_index = int.from_bytes(bytes(packet[0:2]), "big")
    payload = np.frombuffer(bytes(packet[2:20]), dtype=np.uint8)
    bits = np.unpackbits(payload).reshape(_SAMPLES_PER_PACKET, 12)
    weights = 1 << np.arange(11, -1, -1)
    raw = bits.dot(weights).astype(np.float64)
    samples = _MICROVOLTS_PER_COUNT * (raw - 2048)
    return packet_index, samples


def _build_command(cmd):
    """Incapsula un comando testuale nel formato atteso dalla caratteristica
    di controllo del Muse: un byte di lunghezza seguito dal testo e da '\\n'."""
    payload = (cmd + "\n").encode("ascii")
    return bytes([len(payload)]) + payload


class MuseEEGSource(EEGSource):
    """Sorgente EEG reale: legge i campioni via Bluetooth da un bracciale o
    cuffiette Muse invece di generarli, e li restituisce nello stesso
    formato di SimulatedMuseSource."""

    CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
    SAMPLE_RATE = 256  # Hz, standard su tutti i modelli Muse

    def __init__(self, address, connect_timeout=15.0, extra_wait_seconds=10.0):
        self.address = address
        self.connect_timeout = connect_timeout
        self.extra_wait_seconds = extra_wait_seconds
        self._buffers = {ch: [] for ch in self.CHANNELS}

    def _on_notification(self, channel_name):
        def handler(_sender, data):
            _, samples = _unpack_eeg_channel(data)
            self._buffers[channel_name].extend(samples.tolist())
        return handler

    async def _connect_and_collect(self, n_samples):
        from bleak import BleakClient

        for buf in self._buffers.values():
            buf.clear()

        async with BleakClient(self.address, timeout=self.connect_timeout) as client:
            for channel_name, uuid in _EEG_UUIDS.items():
                await client.start_notify(uuid, self._on_notification(channel_name))

            await client.write_gatt_char(_CONTROL_UUID, _build_command("d"))

            deadline = time.monotonic() + (n_samples / self.SAMPLE_RATE) + self.extra_wait_seconds
            while min(len(buf) for buf in self._buffers.values()) < n_samples:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Il bracciale Muse non ha inviato abbastanza dati EEG entro "
                        "il tempo previsto: verifica che sia acceso, indossato "
                        "correttamente (elettrodi a contatto con la pelle) e vicino "
                        "al computer."
                    )
                await asyncio.sleep(0.05)

            try:
                await client.write_gatt_char(_CONTROL_UUID, _build_command("h"))
                for uuid in _EEG_UUIDS.values():
                    await client.stop_notify(uuid)
            except Exception:
                pass  # la disconnessione del client (gestita dal `async with`) basta comunque

        return np.array([self._buffers[ch][:n_samples] for ch in self.CHANNELS])

    def get_chunk(self, n_samples):
        """Si connette al Muse, avvia lo streaming reale e raccoglie n_samples
        campioni per canale (non simulati). Restituisce (data, None): a
        differenza della sorgente simulata non c'è uno "stato mentale" da
        etichettare, il segnale è quello letto davvero dal dispositivo."""
        try:
            data = asyncio.run(self._connect_and_collect(n_samples))
        except RuntimeError:
            raise
        except ImportError as err:
            raise RuntimeError("Libreria 'bleak' non installata: esegui 'pip install bleak'.") from err
        except Exception as err:
            raise RuntimeError(
                f"Impossibile leggere dati dal bracciale Muse ({err}). Verifica che sia "
                "acceso, indossato, con il Bluetooth del computer attivo, e che "
                f"l'indirizzo configurato (BRAINART_MUSE_ADDRESS={self.address!r}) sia corretto "
                "— usa 'python3 scan_devices.py' per ritrovarlo."
            ) from err
        return data, None
