"""TCP participant link to the FlatSat HITL bridge (PEROVSAT/hitl-bridge).

The bridge fans every frame out to every other participant, so frames sent
here reach the emulated devices on UART and replies come back on the same
socket. The wire envelope matches hitl-bridge ``link.py`` and the emulator's
``framing.c``: ``SOF 0xA5 | length u8 | frame | CRC-16/CCITT-FALSE LE``, the
CRC covering the frame only. Frame bytes come from the perovsat-protocol codec.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable

SOF = 0xA5
MAX_FRAME_LEN = 87


def parse_address(address: str) -> tuple[str, int]:
    """Split ``host:port`` on the last colon."""
    host, sep, port = address.rpartition(":")
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"bridge address must be host:port, got {address!r}")
    return host, int(port)


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode_envelope(frame: bytes) -> bytes:
    if not 0 < len(frame) <= MAX_FRAME_LEN:
        raise ValueError(f"frame length must be 1..{MAX_FRAME_LEN}, got {len(frame)}")
    return bytes((SOF, len(frame))) + frame + crc16_ccitt_false(frame).to_bytes(2, "little")


class Deframer:
    """Pull complete frames out of a byte stream, resynchronizing on bad SOFs."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        self._buffer.extend(data)
        buffer, frames = self._buffer, []
        while True:
            start = buffer.find(SOF)
            if start < 0:
                buffer.clear()
                return frames
            del buffer[:start]
            if len(buffer) < 2:
                return frames
            length = buffer[1]
            if not 0 < length <= MAX_FRAME_LEN:
                del buffer[:1]
                continue
            if len(buffer) < length + 4:
                return frames
            frame = bytes(buffer[2:2 + length])
            if int.from_bytes(buffer[2 + length:4 + length], "little") != crc16_ccitt_false(frame):
                del buffer[:1]
                continue
            frames.append(frame)
            del buffer[:length + 4]


class BridgeLink:
    """Send frames to the bridge; a reader thread hands every received frame to ``on_frame``."""

    def __init__(self, address: str, on_frame: Callable[[bytes], None],
                 connect_timeout_s: float = 3.0):
        host, port = parse_address(address)
        try:
            self._sock = socket.create_connection((host, port), connect_timeout_s)
        except OSError as exc:
            raise RuntimeError(f"Could not connect to HITL bridge at {address}: {exc}") from exc
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.settimeout(None)
        self.address = address
        self.sent = 0
        self._on_frame = on_frame
        self._closed = threading.Event()
        self._reader = threading.Thread(target=self._read, name="bridge-reader", daemon=True)
        self._reader.start()

    def send(self, frame: bytes) -> None:
        try:
            self._sock.sendall(encode_envelope(frame))
        except OSError as exc:
            raise RuntimeError(f"HITL bridge write failed: {exc}") from exc
        self.sent += 1

    def _read(self) -> None:
        deframer = Deframer()
        while not self._closed.is_set():
            try:
                data = self._sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            for frame in deframer.push(data):
                self._on_frame(frame)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()
        self._reader.join(timeout=1.0)
