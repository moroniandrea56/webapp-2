"""
scan_devices.py
================
Scansiona i dispositivi Bluetooth Low Energy nelle vicinanze, per trovare
il bracciale/headband EEG prima ancora di sapere come leggerne i dati
(vedi eeg_device.py per i passi successivi).

Va eseguito su una macchina con Bluetooth reale, col dispositivo acceso e
vicino: in un ambiente cloud senza radio Bluetooth non troverà nulla.

Esecuzione:
    pip install -r requirements.txt
    python3 scan_devices.py
"""

from eeg_device import list_bluetooth_devices


def main():
    print("Scansione dispositivi Bluetooth in corso (5 secondi)...")
    try:
        devices = list_bluetooth_devices(timeout=5.0)
    except RuntimeError as err:
        print(f"Errore: {err}")
        return

    if not devices:
        print(
            "Nessun dispositivo trovato. Verifica che il bracciale sia acceso, "
            "vicino, e che il Bluetooth del computer sia attivo."
        )
        return

    print(f"\nTrovati {len(devices)} dispositivi:\n")
    for device in devices:
        rssi_info = f" (segnale: {device['rssi']} dBm)" if device["rssi"] is not None else ""
        print(f"  {device['name']:30s} {device['address']}{rssi_info}")


if __name__ == "__main__":
    main()
