"""Host-side parser for the USB-CDC ``frame_t`` records emitted by the MCU.

The on-the-wire format is fixed in ``firmware/README.md`` and is little-endian:

    magic       u32  0x434F4E54 ('CONT')
    rows        u16
    cols        u16
    seq         u32  monotonic
    timestamp_us u32 µs since MCU boot
    crc         u16  CRC-16/CCITT over the data bytes
    _pad        u16
    data        u8 * rows * cols  row-major, 8 bits per cell

This module re-syncs on the magic if the input stream is partial / corrupt,
and is independently unit tested without any serial port hardware via the
``FrameReader.feed`` byte-stream entry point.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import numpy as np

FRAME_MAGIC = 0x434F4E54  # 'CONT'
_HEADER = struct.Struct("<I H H I I H H")
HEADER_BYTES = _HEADER.size  # 20


@dataclass(frozen=True)
class Frame:
    """One parsed tactile frame ready for inference / upload."""

    seq: int
    timestamp_us: int
    rows: int
    cols: int
    data: np.ndarray  # uint8, shape (rows, cols)

    def to_list(self) -> list[float]:
        """Row-major float list, ready to drop into a ``FrameIn`` payload."""
        return self.data.astype(np.float32).reshape(-1).tolist()


def crc16_ccitt(buf: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """CRC-16/CCITT (XMODEM variant). Pure Python; ~µs per 256-byte frame.

    Used to validate the firmware-side CRC on each frame. Mismatched frames
    are dropped at the reader; partial/short streams cause the reader to fall
    back to magic re-sync.
    """
    crc = init & 0xFFFF
    for b in buf:
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class FrameReader:
    """Stateful byte-stream → ``Frame`` reassembler.

    Designed to be fed in arbitrary chunks (so it works equally well with a
    pyserial blocking ``read()``, an in-memory test buffer, or a TCP socket).
    On every ``feed()`` it yields all *complete* frames it could parse.

    Implementation strategy: keep a small rolling byte buffer, scan for the
    magic, decode the fixed header, wait until ``rows*cols`` payload bytes
    have arrived, validate the CRC, yield the frame.
    """

    # Hard cap on rows*cols. Prevents a single bad header from causing the
    # reader to wait for gigabytes of payload before re-syncing.
    _MAX_CELLS = 512 * 512

    def __init__(self) -> None:
        self._buf = bytearray()
        # Stats for the telemetry layer to surface.
        self.frames_ok = 0
        self.frames_crc_failed = 0
        self.bytes_resynced = 0

    def feed(self, chunk: bytes) -> Iterator[Frame]:
        if chunk:
            self._buf.extend(chunk)

        while True:
            progress, frame = self._try_one()
            if frame is not None:
                yield frame
            if not progress:
                return

    def _try_one(self) -> tuple[bool, Frame | None]:
        """Attempt to parse one frame.

        Returns ``(progress, frame_or_None)``:

        - ``progress=True`` means the buffer was shortened (frame yielded,
          garbage dropped, or CRC-failed frame consumed) and the caller
          should call again.
        - ``progress=False`` means we are stuck waiting on more bytes and
          the outer ``feed`` loop should return until the next chunk.
        """
        # Need at least a header to make any progress.
        if len(self._buf) < HEADER_BYTES:
            return (False, None)

        # Locate the magic at the head of the buffer; if it isn't there, scan
        # forward for the next occurrence and drop the bytes before it.
        magic_le = struct.pack("<I", FRAME_MAGIC)
        if bytes(self._buf[0:4]) != magic_le:
            idx = self._buf.find(magic_le)
            if idx < 0:
                # No magic in current buffer. Keep at most 3 bytes — the
                # magic might be split across this and the next chunk.
                drop = max(0, len(self._buf) - 3)
                if drop <= 0:
                    return (False, None)
                self.bytes_resynced += drop
                del self._buf[:drop]
                return (True, None)
            self.bytes_resynced += idx
            del self._buf[:idx]
            return (True, None)

        if len(self._buf) < HEADER_BYTES:
            return (False, None)

        magic, rows, cols, seq, ts_us, crc, _pad = _HEADER.unpack_from(self._buf, 0)
        if magic != FRAME_MAGIC:
            # Belt-and-suspenders; if some impostor passed `find` but failed
            # `unpack`, drop one byte and retry.
            self.bytes_resynced += 1
            del self._buf[:1]
            return (True, None)

        cells = rows * cols
        if rows <= 0 or cols <= 0 or cells > self._MAX_CELLS:
            # Garbage header. Drop the magic and let the next iteration
            # re-sync to the next CONT-tagged frame.
            self.bytes_resynced += 4
            del self._buf[:4]
            return (True, None)

        total = HEADER_BYTES + cells
        if len(self._buf) < total:
            return (False, None)

        data_bytes = bytes(self._buf[HEADER_BYTES:total])
        actual_crc = crc16_ccitt(data_bytes)
        # Consume the frame from the buffer either way; if CRC fails we drop it.
        del self._buf[:total]

        if actual_crc != crc:
            self.frames_crc_failed += 1
            return (True, None)

        data = np.frombuffer(data_bytes, dtype=np.uint8).reshape(rows, cols)
        self.frames_ok += 1
        return (True, Frame(seq=seq, timestamp_us=ts_us, rows=rows, cols=cols, data=data))


# ── synthetic frame source (for tests + dev) ──


def encode_frame(frame: Frame) -> bytes:
    """Inverse of :class:`FrameReader` — produce wire bytes for a frame.

    Useful in unit tests and in the simulator that backs the on-host
    development loop. Production code never calls this; the MCU does.
    """
    data_bytes = bytes(frame.data.astype(np.uint8).reshape(-1).tolist())
    crc = crc16_ccitt(data_bytes)
    header = _HEADER.pack(
        FRAME_MAGIC, frame.rows, frame.cols, frame.seq, frame.timestamp_us, crc, 0
    )
    return header + data_bytes


class SerialLike(Protocol):
    """The narrow slice of pyserial.Serial that the agent uses."""

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


def open_serial(port: str, baudrate: int) -> SerialLike:
    """Open the USB-CDC port with sane defaults for a 200 Hz scanner stream.

    Imported lazily so test environments without pyserial can still import
    this module.
    """
    import serial  # type: ignore[import-not-found]

    return serial.Serial(port=port, baudrate=baudrate, timeout=0.5)
