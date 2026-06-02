"""CLI: jpi2csv path/to/file.JPI  OR  jpi2csv path/to/dir/

Writes one CSV per .JPI next to the input (or into --output-dir if given).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .decode import Flight, decode
from .flysto import to_flysto_csv


def _convert_one(jpi_path: Path, out_path: Path) -> bool:
    """Returns True if any sample had GPS position (LAT/LNG). False otherwise."""
    flights, _ = decode(jpi_path.read_bytes(), source_name=jpi_path.name)
    out_path.write_bytes(to_flysto_csv(flights))
    return _has_position(flights)


def _has_position(flights: list[Flight]) -> bool:
    for f in flights:
        for s in f.samples:
            if s.lat is not None or s.lng is not None:
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jpi2csv",
        description="Convert JPI .JPI engine-monitor files to FlySto-compatible CSV.",
    )
    parser.add_argument("input", type=Path,
                        help="Path to a .JPI file, or a directory containing .JPI files.")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output CSV path (single-file mode) or output directory (batch mode).")
    args = parser.parse_args(argv)

    src: Path = args.input
    if not src.exists():
        print(f"error: {src} does not exist", file=sys.stderr)
        return 2

    if src.is_dir():
        jpis = sorted(p for p in src.iterdir() if p.suffix.upper() == ".JPI")
        if not jpis:
            print(f"error: no .JPI files found in {src}", file=sys.stderr)
            return 2
        out_dir = args.output or src
        out_dir.mkdir(parents=True, exist_ok=True)
        for jpi in jpis:
            _emit(jpi, out_dir / (jpi.stem + ".csv"))
    else:
        out = args.output or src.with_suffix(".csv")
        if out.is_dir():
            out = out / (src.stem + ".csv")
        _emit(src, out)

    return 0


def _emit(jpi: Path, out: Path) -> None:
    try:
        had_position = _convert_one(jpi, out)
    except Exception as e:
        print(f"error: failed to convert {jpi.name}: {e}", file=sys.stderr)
        raise
    print(f"wrote {out}")
    if not had_position:
        print(
            f"WARNING: no GPS position (LAT/LNG) decoded for {jpi.name}; "
            "those columns are blank and FlySto's map features will not work.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
