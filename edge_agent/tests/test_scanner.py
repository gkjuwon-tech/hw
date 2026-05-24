"""Frame parser correctness: happy path, partial chunks, resync, CRC."""

from __future__ import annotations

import numpy as np

from edge_agent.scanner import (
    FRAME_MAGIC,
    Frame,
    FrameReader,
    crc16_ccitt,
    encode_frame,
)


def _frame(seq: int = 1, rows: int = 4, cols: int = 4) -> Frame:
    data = (np.arange(rows * cols, dtype=np.uint8) + seq).reshape(rows, cols)
    return Frame(seq=seq, timestamp_us=1000 * seq, rows=rows, cols=cols, data=data)


def test_round_trip_single_frame() -> None:
    frame = _frame()
    blob = encode_frame(frame)
    reader = FrameReader()
    out = list(reader.feed(blob))
    assert len(out) == 1
    got = out[0]
    assert got.seq == frame.seq
    assert got.rows == frame.rows
    assert got.cols == frame.cols
    assert (got.data == frame.data).all()
    assert reader.frames_ok == 1
    assert reader.frames_crc_failed == 0


def test_partial_chunks_assembled() -> None:
    frame = _frame(seq=42, rows=8, cols=8)
    blob = encode_frame(frame)
    reader = FrameReader()

    out_first = list(reader.feed(blob[:5]))
    assert out_first == []
    out_second = list(reader.feed(blob[5:30]))
    assert out_second == []
    out_third = list(reader.feed(blob[30:]))
    assert len(out_third) == 1
    assert out_third[0].seq == 42


def test_resync_on_garbage_prefix() -> None:
    frame = _frame(seq=7)
    blob = b"\xde\xad\xbe\xef garbage garbage \x00\x01\x02" + encode_frame(frame)
    reader = FrameReader()
    out = list(reader.feed(blob))
    assert len(out) == 1
    assert out[0].seq == 7
    assert reader.bytes_resynced > 0


def test_crc_mismatch_dropped() -> None:
    frame = _frame(seq=9, rows=4, cols=4)
    blob = bytearray(encode_frame(frame))
    # Flip one data byte after the 20-byte header.
    blob[25] ^= 0xFF
    reader = FrameReader()
    out = list(reader.feed(bytes(blob)))
    assert out == []
    assert reader.frames_crc_failed == 1


def test_two_back_to_back_frames() -> None:
    a = _frame(seq=1)
    b = _frame(seq=2)
    reader = FrameReader()
    out = list(reader.feed(encode_frame(a) + encode_frame(b)))
    assert [f.seq for f in out] == [1, 2]


def test_garbage_header_rows_zero_recovers() -> None:
    """Bad header (rows=0) should not stall the reader forever."""
    import struct

    from edge_agent.scanner import _HEADER

    bogus = _HEADER.pack(FRAME_MAGIC, 0, 0, 99, 0, 0, 0)
    good = encode_frame(_frame(seq=5))
    reader = FrameReader()
    out = list(reader.feed(bogus + good))
    assert [f.seq for f in out] == [5]
    # Sanity: pure-Python CRC matches struct round-trip.
    assert crc16_ccitt(b"") == 0xFFFF
    assert struct.pack("<I", FRAME_MAGIC) == b"TNOC"
