"""tegrastats parsing — happy path + missing-field tolerance."""

from __future__ import annotations

from edge_agent.telemetry import parse_tegrastats, stub_tegrastats_line


def test_parse_stub_line() -> None:
    line = stub_tegrastats_line(
        cpu_pct=21.0,
        gpu_pct=14.0,
        cpu_temp_c=49.5,
        gpu_temp_c=53.0,
        ram_used_mb=2400,
        ram_total_mb=7775,
        power_mw=4800,
    )
    snap = parse_tegrastats(line)
    assert snap.cpu_pct == 21.0
    assert snap.gpu_pct == 14.0
    assert snap.cpu_temp_c == 49.5
    assert snap.gpu_temp_c == 53.0
    assert snap.ram_used_mb == 2400
    assert snap.ram_total_mb == 7775
    assert snap.power_mw == 4800


def test_parse_partial_line_zero_filled() -> None:
    snap = parse_tegrastats("RAM 100/200MB CPU [5%@900]")
    assert snap.ram_used_mb == 100
    assert snap.ram_total_mb == 200
    assert snap.cpu_pct == 5.0
    assert snap.gpu_pct == 0.0
    assert snap.power_mw == 0


def test_parse_garbage_safe() -> None:
    snap = parse_tegrastats("hello world this is not tegrastats")
    assert snap.cpu_pct == 0.0
    assert snap.ram_total_mb == 0
