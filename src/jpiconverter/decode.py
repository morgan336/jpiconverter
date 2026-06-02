"""Adapt the vendored 2sec/python-edm parser into stable dataclasses.

Everything downstream of this module consumes ``list[Flight]`` and never touches
the vendored API directly. If we ever swap parsers (e.g. port from
wannamak/edmtools), only this file changes.

Unit scaling notes (verified empirically against tests/fixtures/U260220.JPI):
    raw / 10   →   MAP (inHg), VOLT (V), HOURS (tach hr), FF (GPH), USD (gal)
    raw as-is  →   EGT/CHT/OAT (°F), RPM, OILP (PSI), HP (%), GSPD (kt)

Known gaps in the upstream parser (callers see ``None``):
    OILT       — upstream emits 0 for every sample on this firmware.
    T1/FF2/FP/AMP/USD2/RFL/LFL/CLD/DIF — not extracted (DIF can be derived;
                                          others require firmware-specific work).

GPS (LAT/LNG/ALT) extraction added in our patches — see
src/jpiconverter/parser/ATTRIBUTION.md for the format details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .parser.edm import EDMData


@dataclass
class Sample:
    timestamp: datetime
    # Engine
    egt: List[Optional[float]] = field(default_factory=lambda: [None] * 6)  # E1..E6, °F
    cht: List[Optional[float]] = field(default_factory=lambda: [None] * 6)  # C1..C6, °F
    t1: Optional[float] = None       # auxiliary / TIT, °F
    oat: Optional[float] = None      # °F
    cld: Optional[float] = None      # °F/min
    oil_t: Optional[float] = None    # °F
    map: Optional[float] = None      # inHg
    rpm: Optional[int] = None
    hp: Optional[float] = None       # %
    ff: Optional[float] = None       # GPH
    ff2: Optional[float] = None      # GPH
    fp: Optional[float] = None       # PSI
    oil_p: Optional[float] = None    # PSI
    bat: Optional[float] = None      # V
    amp: Optional[float] = None      # A
    usd: Optional[float] = None      # gal
    usd2: Optional[float] = None     # gal
    rfl: Optional[float] = None      # gal
    lfl: Optional[float] = None      # gal
    hrs: Optional[float] = None      # tach hr
    # GPS
    spd: Optional[float] = None      # kt
    alt: Optional[float] = None      # ft
    lat: Optional[float] = None      # decimal degrees
    lng: Optional[float] = None      # decimal degrees
    # Pilot mark
    mark: Optional[int] = None


@dataclass
class Flight:
    number: int
    samples: List[Sample]


def decode(jpi_bytes: bytes, source_name: str = "upload.JPI") -> tuple[list[Flight], dict]:
    """Decode .JPI bytes into a list of flights, in flight-number order.

    Returns (flights, header_config) where header_config is the parser's
    config dict (tail no, EDM type, etc.) — useful for the web UI.
    """
    # Parse straight from memory — the bytes never touch the filesystem.
    edm = EDMData(source_name)
    edm.loadBytes(jpi_bytes)
    edm.parseHeader()
    edm.parseFlights(additional_columns=None)

    flights = [_to_flight(fnum, edm.flight_rows[fnum])
               for fnum in sorted(edm.flight_rows.keys())]
    return flights, dict(edm.config)


def _to_flight(fnum: int, raw_rows: list[dict]) -> Flight:
    return Flight(number=fnum, samples=[_to_sample(r) for r in raw_rows])


def _scale(raw, factor: float) -> Optional[float]:
    """Apply a divisor; 0 raw -> None so the writer emits a blank cell
    rather than a misleading 0.0. Engine-off samples often have 0s."""
    if raw is None or raw == 0:
        return None
    return raw / factor


def _passthrough(raw) -> Optional[float]:
    if raw is None or raw == 0:
        return None
    return raw


def _to_sample(r: dict) -> Sample:
    return Sample(
        timestamp=r["date"],
        egt=[_passthrough(r.get(f"EGT{i}")) for i in range(1, 7)],
        cht=[_passthrough(r.get(f"CHT{i}")) for i in range(1, 7)],
        # OAT can legitimately be 0 (freezing); don't treat 0 as missing.
        oat=r.get("OAT"),
        cld=_passthrough(r.get("CLD")),
        # OILT is always 0 in upstream output on this firmware → effectively None.
        oil_t=_passthrough(r.get("OILT")),
        map=_scale(r.get("MAP"), 10),
        rpm=_passthrough(r.get("RPM")),
        hp=_passthrough(r.get("HP")),
        ff=_scale(r.get("FF"), 10),
        oil_p=_passthrough(r.get("OILP")),
        bat=_scale(r.get("VOLT"), 10),
        usd=_scale(r.get("USD"), 10),
        hrs=_scale(r.get("HOURS"), 10),
        spd=_passthrough(r.get("GSPD")),
        alt=_passthrough(r.get("ALT")),
        lat=r.get("LAT"),  # may be None when no GPS lock; otherwise float decimal degrees
        lng=r.get("LNG"),
        # MARK: upstream emits an integer; only surface non-zero as a flag.
        mark=r.get("MARK") if r.get("MARK") else None,
    )
