"""Decimal degrees -> hemisphere-DMS string for FlySto CSV LAT/LNG cells.

Format pinned to match the JPI-V1-Template sample (`N35.35.35`, `W120.20.20`):
    LAT: <N|S>DD.MM.SS   (2-digit deg, 2-digit min, 2-digit sec)
    LNG: <E|W>DDD.MM.SS  (3-digit deg, 2-digit min, 2-digit sec)

If FlySto rejects, the only place to change is here.
"""

from __future__ import annotations


def _to_dms(deg: float, deg_digits: int, positive_hemi: str, negative_hemi: str) -> str:
    if deg is None:
        return ""
    hemi = positive_hemi if deg >= 0 else negative_hemi
    total_seconds = round(abs(deg) * 3600)
    d, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{hemi}{d:0{deg_digits}d}.{m:02d}.{s:02d}"


def to_lat_dms(deg: float | None) -> str:
    return _to_dms(deg, deg_digits=2, positive_hemi="N", negative_hemi="S")


def to_lng_dms(deg: float | None) -> str:
    return _to_dms(deg, deg_digits=3, positive_hemi="E", negative_hemi="W")
