"""Serialise decoded flights into FlySto V1 CSV bytes.

Output rules verified against ``JPI-V1-Template.csv``:
    * 39 columns (CLAUDE.md says 38, which miscounts; the template is 39).
    * CRLF line endings.
    * Row 1: header.
    * Row 2: tach summary (3 populated cells + 36 empty cells).
    * Rows 3+: one row per sample; INDEX monotonic across all flights;
      DATE = M/D/YYYY (no zero-pad on month/day); TIME = HH:MM:SS.
    * Missing optional fields → blank cell, EXCEPT USD2 which emits the
      literal ``NA`` (as in the template).
"""

from __future__ import annotations

import csv
import io
from typing import Callable, List

from .decode import Flight, Sample
from .geo import to_lat_dms, to_lng_dms


# Hardcoded so the package is self-contained when installed as a wheel.
# A test (test_header_matches_template) keeps this in sync with the canonical
# JPI-V1-Template.csv file at the repo root.
HEADER = [
    "INDEX", "DATE", "TIME",
    "E1", "E2", "E3", "E4", "E5", "E6",
    "C1", "C2", "C3", "C4", "C5", "C6",
    "T1", "OAT", "DIF", "CLD", "MAP", "RPM", "HP",
    "FF", "FF2", "FP", "OILP", "BAT", "AMP", "OILT",
    "USD", "USD2", "RFL", "LFL",
    "HRS", "SPD", "ALT", "LAT", "LNG", "MARK",
]
NUM_COLUMNS = len(HEADER)  # 39


def _fmt_int(v) -> str:
    return "" if v is None else str(int(v))


def _fmt_one_dec(v) -> str:
    return "" if v is None else f"{v:.1f}"


def _fmt_egt_dif(sample: Sample) -> str:
    vals = [v for v in sample.egt if v is not None]
    if not vals:
        return ""
    return str(int(max(vals) - min(vals)))


# (header_name, serialiser-from-sample)
# Order MUST match HEADER. _build_row asserts this at module-load time.
COLUMNS: list[tuple[str, Callable[[Sample, int], str]]] = [
    ("INDEX", lambda s, i: str(i)),
    ("DATE",  lambda s, i: f"{s.timestamp.month}/{s.timestamp.day}/{s.timestamp.year}"),
    ("TIME",  lambda s, i: s.timestamp.strftime("%H:%M:%S")),
    ("E1",    lambda s, i: _fmt_int(s.egt[0])),
    ("E2",    lambda s, i: _fmt_int(s.egt[1])),
    ("E3",    lambda s, i: _fmt_int(s.egt[2])),
    ("E4",    lambda s, i: _fmt_int(s.egt[3])),
    ("E5",    lambda s, i: _fmt_int(s.egt[4])),
    ("E6",    lambda s, i: _fmt_int(s.egt[5])),
    ("C1",    lambda s, i: _fmt_int(s.cht[0])),
    ("C2",    lambda s, i: _fmt_int(s.cht[1])),
    ("C3",    lambda s, i: _fmt_int(s.cht[2])),
    ("C4",    lambda s, i: _fmt_int(s.cht[3])),
    ("C5",    lambda s, i: _fmt_int(s.cht[4])),
    ("C6",    lambda s, i: _fmt_int(s.cht[5])),
    ("T1",    lambda s, i: _fmt_int(s.t1)),
    ("OAT",   lambda s, i: _fmt_int(s.oat)),
    ("DIF",   lambda s, i: _fmt_egt_dif(s)),
    ("CLD",   lambda s, i: _fmt_int(s.cld)),
    ("MAP",   lambda s, i: _fmt_one_dec(s.map)),
    ("RPM",   lambda s, i: _fmt_int(s.rpm)),
    ("HP",    lambda s, i: _fmt_int(s.hp)),
    ("FF",    lambda s, i: _fmt_one_dec(s.ff)),
    ("FF2",   lambda s, i: _fmt_one_dec(s.ff2)),
    ("FP",    lambda s, i: _fmt_one_dec(s.fp)),
    ("OILP",  lambda s, i: _fmt_int(s.oil_p)),
    ("BAT",   lambda s, i: _fmt_one_dec(s.bat)),
    ("AMP",   lambda s, i: _fmt_int(s.amp)),
    ("OILT",  lambda s, i: _fmt_int(s.oil_t)),
    ("USD",   lambda s, i: _fmt_one_dec(s.usd)),
    # USD2 uses the literal 'NA' when absent — matches the template.
    ("USD2",  lambda s, i: _fmt_one_dec(s.usd2) if s.usd2 is not None else "NA"),
    ("RFL",   lambda s, i: _fmt_int(s.rfl)),
    ("LFL",   lambda s, i: _fmt_int(s.lfl)),
    ("HRS",   lambda s, i: _fmt_one_dec(s.hrs)),
    ("SPD",   lambda s, i: _fmt_int(s.spd)),
    ("ALT",   lambda s, i: _fmt_int(s.alt)),
    ("LAT",   lambda s, i: to_lat_dms(s.lat)),
    ("LNG",   lambda s, i: to_lng_dms(s.lng)),
    ("MARK",  lambda s, i: "" if s.mark is None else str(int(s.mark))),
]

assert [name for name, _ in COLUMNS] == HEADER, (
    "COLUMNS order/names diverged from JPI-V1-Template.csv header"
)


def _tach_summary(flights: List[Flight]) -> list[str]:
    """Row 2: per the template, only the first 3 cells carry data; pad to 39."""
    all_hrs = [s.hrs for f in flights for s in f.samples if s.hrs is not None]
    if not all_hrs:
        # No HRS readings anywhere — emit blank summary but keep the row shape.
        return [""] * NUM_COLUMNS

    start = min(all_hrs)
    end = max(all_hrs)

    # Per-flight durations summed (so a multi-flight CSV reports engine-on time,
    # not wall-clock span between the first and last flight).
    duration = 0.0
    for f in flights:
        hrs = [s.hrs for s in f.samples if s.hrs is not None]
        if hrs:
            duration += max(hrs) - min(hrs)

    row = [
        f"Engine - Tach Start = {start:.1f}",
        f"Tach End = {end:.1f}",
        f"Tach Duration = {duration:.1f}",
    ]
    row.extend([""] * (NUM_COLUMNS - len(row)))
    return row


def _build_row(sample: Sample, index: int) -> list[str]:
    return [serialise(sample, index) for _, serialise in COLUMNS]


def to_flysto_csv(flights: List[Flight]) -> bytes:
    """Serialise a list of decoded flights to FlySto V1 CSV bytes (CRLF)."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")

    writer.writerow(HEADER)
    writer.writerow(_tach_summary(flights))

    index = 0
    for flight in flights:
        for sample in flight.samples:
            writer.writerow(_build_row(sample, index))
            index += 1

    return buf.getvalue().encode("utf-8")
