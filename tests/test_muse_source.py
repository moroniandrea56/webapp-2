"""Test della decodifica del protocollo BLE del Muse: pura matematica sui
byte, verificabile con dati sintetici senza un bracciale reale collegato.
Il resto di MuseEEGSource (connessione Bluetooth vera) non è testabile
qui — va provato su una macchina con Bluetooth fisico e il dispositivo."""

import numpy as np

from muse_source import _build_command, _unpack_eeg_channel


def _pack_12bit_values(packet_index, values):
    """Costruisce a mano un pacchetto BLE come lo manderebbe il Muse, per
    poter verificare che _unpack_eeg_channel lo decodifichi correttamente:
    l'inverso esatto della decodifica che il codice di produzione fa."""
    assert len(values) == 12
    bits = []
    for v in values:
        bits.extend([(v >> shift) & 1 for shift in range(11, -1, -1)])
    bits = np.array(bits, dtype=np.uint8)
    payload = np.packbits(bits).tobytes()
    return packet_index.to_bytes(2, "big") + payload


def test_unpack_eeg_channel_roundtrips_known_values():
    raw_values = [0, 2048, 4095, 1, 4094, 100, 2000, 3000, 500, 1500, 2500, 3500]
    packet = _pack_12bit_values(packet_index=42, values=raw_values)

    packet_index, samples = _unpack_eeg_channel(packet)

    assert packet_index == 42
    assert len(samples) == 12
    expected_microvolts = 0.48828125 * (np.array(raw_values, dtype=np.float64) - 2048)
    np.testing.assert_allclose(samples, expected_microvolts)


def test_unpack_eeg_channel_midpoint_is_zero_microvolts():
    packet = _pack_12bit_values(packet_index=0, values=[2048] * 12)
    _, samples = _unpack_eeg_channel(packet)
    np.testing.assert_allclose(samples, np.zeros(12))


def test_unpack_eeg_channel_packet_length_is_20_bytes():
    packet = _pack_12bit_values(packet_index=7, values=list(range(0, 4095, 341))[:12])
    assert len(packet) == 20


def test_build_command_encodes_length_prefix_and_newline():
    assert _build_command("d") == b"\x02d\n"
    assert _build_command("h") == b"\x02h\n"
