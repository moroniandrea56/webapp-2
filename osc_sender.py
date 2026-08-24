"""
osc_sender.py
=============
Implementazione minimale (senza librerie esterne) del protocollo OSC
(Open Sound Control), lo standard usato per far comunicare software
diversi in tempo reale — es. Python -> TouchDesigner.

Quando avrai TouchDesigner installato, dovrai solo creare un OSC In CHOP
sulla stessa porta (default 9000) e riceverai automaticamente questi dati.
"""

import socket
import struct


def _pad(data: bytes) -> bytes:
    """OSC richiede che ogni blocco sia allineato a 4 byte."""
    while len(data) % 4 != 0:
        data += b"\x00"
    return data


def _osc_string(s: str) -> bytes:
    return _pad(s.encode("utf-8") + b"\x00")


def build_osc_message(address: str, *args) -> bytes:
    """
    Costruisce un messaggio OSC.
    address: es. "/brainart/asymmetry"
    args: valori float o int da inviare
    """
    msg = _osc_string(address)

    type_tags = ","
    arg_bytes = b""
    for arg in args:
        if isinstance(arg, float):
            type_tags += "f"
            arg_bytes += struct.pack(">f", arg)
        elif isinstance(arg, int):
            type_tags += "i"
            arg_bytes += struct.pack(">i", arg)
        elif isinstance(arg, str):
            type_tags += "s"
            arg_bytes += _osc_string(arg)
        else:
            raise TypeError(f"Tipo non supportato per OSC: {type(arg)}")

    msg += _osc_string(type_tags)
    msg += arg_bytes
    return msg


class OSCSender:
    def __init__(self, ip="127.0.0.1", port=9000):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, *args):
        packet = build_osc_message(address, *args)
        try:
            self.sock.sendto(packet, (self.ip, self.port))
        except OSError:
            # Se non c'è nessuno in ascolto (es. TouchDesigner non aperto),
            # non bloccare il programma: è normale durante lo sviluppo.
            pass

    def send_metrics(self, metrics: dict):
        """Invia tutte le metriche BrainArt con un indirizzo OSC dedicato ciascuna."""
        self.send("/brainart/asymmetry", float(metrics["asymmetry"]))
        self.send("/brainart/activation", float(metrics["activation"]))
        self.send("/brainart/signature", float(metrics["signature"]))
