# JPI to FlySto CSV Converter

Converts J.P. Instruments (JPI) EDM engine-monitor `.JPI` files into CSVs
compatible with [FlySto.net](https://flysto.net).

Tested against several EDM-830 downloads (one clean fixture of 16 flights /
26k+ samples, plus four real-world files exercising the firmware's
repeat-compression and malformed-record edge cases).

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
- GPS (`LAT`/`LNG`/`ALT`/`SPD`) is decoded when the EDM had a GPS feed at
  flight time — typically 95–97% of rows on flights with a GPS lock at engine
  start. Rows without a lock have those cells blank.
- Optional columns the source does not log (`T1`, `FF2`, `FP`, `AMP`, `RFL`,
  `LFL`) are left blank, except `USD2` which emits the literal `NA` to match
  the template.

## Known limitations

1. **LAT/LNG cell format is unproven against FlySto.** The decode itself is
   verified (matches `openenginedata.org`'s output exactly), but the
   `Ndd.mm.ss` / `Wddd.mm.ss` zero-padded integer-DMS format used in the CSV
   is the conservative guess based on the template. CS-520 was the historical
   FlySto blocker; until a real upload succeeds, the format is unproven. The
   only file to change if rejected is `src/jpiconverter/geo.py`.
2. **OILT (oil temperature) is always blank.** Upstream emits 0 for every
   sample on this firmware; we treat it as missing.
3. **Multi-flight CSV.** FlySto's template appears single-flight; we
   concatenate on purpose per project requirements. If FlySto rejects, a
   `--per-flight` flag is a small change — the architecture supports it.
4. **Partial decode on malformed records.** Newer EDM-830 firmware sometimes
   emits records the parser can't fully interpret (repeat-compression sentinels
   and decodeflags-mismatch records). The converter recovers as much of the
   affected flight as possible, logs a warning, and moves on. In practice
   this affects roughly one flight in fifteen, and only truncates the tail of
   that single flight.

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
