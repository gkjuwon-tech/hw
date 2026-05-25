"""Common types used by every analysis module."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


SEVERITY_NAMES = {
    0: "INFO",
    1: "ADVISORY",
    2: "WARNING",
    3: "MAJOR",
    4: "CRITICAL",
    5: "FIRE",  # literal smoke on power-up
}


@dataclass
class Finding:
    module: str       # which analysis produced this finding
    code: str         # short stable id, e.g. "PTC-UNDERSIZED"
    title: str
    severity: int     # 0..5 -- see SEVERITY_NAMES
    detail: str       # multi-line markdown
    refs: list[str] = field(default_factory=list)   # refdes, file paths, ...
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def banner(s: int) -> str:
    return SEVERITY_NAMES.get(s, f"S{s}")
