"""Test per osc_sender.py: costruzione dei messaggi OSC e invio silenzioso
quando non c'è nessun listener."""

import struct

import pytest

from osc_sender import OSCSender, build_osc_message


def test_message_is_always_padded_to_a_multiple_of_four():
    msg = build_osc_message("/x")
    assert len(msg) % 4 == 0


def test_build_osc_message_float_argument_roundtrips():
    msg = build_osc_message("/brainart/asymmetry", 0.42)

    # indirizzo "/brainart/asymmetry" (19 char) + \0 -> 20 byte, già multiplo di 4
    address_block = 20
    assert msg[:19].decode() == "/brainart/asymmetry"

    # type tag ",f" + \0\0 di padding -> 4 byte
    assert msg[address_block:address_block + 2] == b",f"

    float_bytes = msg[address_block + 4:address_block + 8]
    assert struct.unpack(">f", float_bytes)[0] == pytest.approx(0.42, abs=1e-6)


def test_build_osc_message_rejects_unsupported_type():
    with pytest.raises(TypeError):
        build_osc_message("/x", [1, 2, 3])


def test_send_does_not_raise_without_a_listener():
    # nessun listener su questa porta: send() deve fallire in silenzio
    # (osc_sender.py cattura OSError apposta), non sollevare.
    sender = OSCSender(ip="127.0.0.1", port=59999)
    sender.send("/test", 1.0)


def test_send_metrics_sends_one_message_per_metric(monkeypatch):
    sender = OSCSender()
    calls = []
    monkeypatch.setattr(sender, "send", lambda *args: calls.append(args))

    sender.send_metrics({"asymmetry": 0.1, "activation": 0.2, "signature": 0.3})

    addresses = [call[0] for call in calls]
    assert addresses == ["/brainart/asymmetry", "/brainart/activation", "/brainart/signature"]
