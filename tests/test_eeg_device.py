"""Test per eeg_device.py: il contratto EEGSource e lo scaffold del dispositivo
reale. I test sulla scansione Bluetooth simulano bleak (via monkeypatch) invece
di dipendere da un vero adattatore, così restano deterministici su qualunque
macchina esegua la suite (con o senza Bluetooth fisico)."""

import pytest

import eeg_device
from eeg_device import BluetoothEEGSource, EEGSource, list_bluetooth_devices


def test_eeg_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        EEGSource()


def test_bluetooth_source_is_instantiable_but_not_functional_yet():
    src = BluetoothEEGSource(address="AA:BB:CC:DD:EE:FF")
    with pytest.raises(NotImplementedError):
        src.connect()
    with pytest.raises(NotImplementedError):
        src.get_chunk(256)


def test_list_bluetooth_devices_wraps_missing_dependency(monkeypatch):
    def fake_scan_async(timeout):
        raise ImportError("no bleak")

    monkeypatch.setattr(eeg_device, "_scan_async", fake_scan_async)
    with pytest.raises(RuntimeError, match="bleak"):
        list_bluetooth_devices(timeout=0.1)


def test_list_bluetooth_devices_wraps_scan_failure(monkeypatch):
    def fake_scan_async(timeout):
        raise OSError("no adapter")

    monkeypatch.setattr(eeg_device, "_scan_async", fake_scan_async)
    with pytest.raises(RuntimeError, match="Scansione Bluetooth non riuscita"):
        list_bluetooth_devices(timeout=0.1)
