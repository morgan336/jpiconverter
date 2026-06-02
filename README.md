# JPI to FlySto CSV Converter

Converts J.P. Instruments (JPI) EDM engine-monitor `.JPI` files into CSVs
compatible with [FlySto.net](https://flysto.net).

Tested against an EDM-830 download (16 flights, 26k+ samples).

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

(Python 3.9 or newer.)

## Use it

### Web UI (recommended for non-technical users)

```sh
.venv/bin/flask --app jpiconverter.web.app run
```

Then open <http://127.0.0.1:5000>, drop in a `.JPI` file, and download the CSV.

### Command line

```sh
# single file
.venv/bin/jpi2csv path/to/file.JPI

# explicit output path
.venv/bin/jpi2csv path/to/file.JPI -o out.csv

# batch — convert every .JPI in a folder
.venv/bin/jpi2csv path/to/folder/
```

### Tests

```sh
.venv/bin/pytest
```

## What you get

One CSV per uploaded `.JPI`, with all flights concatenated. The CSV uses the
FlySto V1 template (39 columns, CRLF line endings):

- `INDEX` is monotonic across all flights (no per-flight reset).
- Row 2 holds the tach summary across the entire file:
  `Engine - Tach Start = ..., Tach End = ..., Tach Duration = ...` (duration is
  the sum of per-flight engine-on time, not the wall-clock span between flights).
- Optional columns the upstream parser does not extract (T1, FF2, FP, AMP,
  RFL, LFL, ALT, LAT, LNG, …) are left blank, except `USD2` which emits
  the literal `NA` matching the template.

## Known limitations

1. **No GPS position.** The vendored parser does not extract `LAT`/`LNG`/`ALT`,
   so those columns are always blank. Only `SPD` (groundspeed) is populated.
   FlySto's map view will not work; engine-data views should.
2. **OILT (oil temperature) is always blank.** The upstream parser emits 0 for
   every sample on this firmware, which we treat as "missing".
3. **LAT/LNG zero-padding is unproven.** When position decoding is added,
   the format is pinned to `NDD.MM.SS` / `WDDD.MM.SS` (zero-padded). Until
   FlySto accepts an upload, it is the conservative guess (see
   `src/jpiconverter/geo.py`).
4. **Multi-flight CSV.** FlySto's template appears single-flight; we concatenate
   on purpose, per project requirements. If FlySto rejects the upload, the fix
   is a `--per-flight` flag — the architecture already supports it.

## Deploying

For a hosted (multi-user) version:

```sh
gunicorn jpiconverter.web.app:app
```

…on any Python-friendly host (Render, Fly.io, Railway, PythonAnywhere).

**Before deploying publicly**, resolve the parser-licence question — see
`src/jpiconverter/parser/ATTRIBUTION.md`. The upstream `2sec/python-edm`
repository has no `LICENSE` file.

## Layout

```
src/jpiconverter/
├── parser/       # vendored from 2sec/python-edm + attribution
├── decode.py     # adapter: .JPI bytes -> list[Flight]
├── geo.py        # decimal degrees -> hemisphere-DMS string
├── flysto.py     # list[Flight] -> FlySto V1 CSV bytes
├── cli.py        # `jpi2csv` CLI
└── web/          # Flask app + upload page

tests/
├── fixtures/U260220.JPI   # real EDM-830 download
├── test_decode.py
├── test_geo.py
└── test_flysto.py
```
