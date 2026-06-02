# Vendored parser

`edm.py` in this directory is **adapted from**:

- Upstream: https://github.com/2sec/python-edm
- Commit: `c790955e369eaf4b4173e9ff3bb8ff79c846db43` (master, June 2026)
- Author credits in-file: based on http://www.rows.ws/jpihack/ and https://github.com/wannamak/edmtools

## License status

The upstream repository **does not include a LICENSE file**. Under default copyright,
all rights are reserved by the upstream author.

This vendored copy is included here for personal, local use only. **Before deploying
this tool publicly, the license question must be resolved** — either by obtaining
explicit permission from the upstream author, or by replacing this parser with a
clean port from the Apache-2.0-licensed `wannamak/edmtools` (Java).

## Modifications made vs. upstream

1. Removed `import config` (line 13). Upstream's `config.py` carries plane-specific
   overrides for the upstream author's aircraft, irrelevant here.
2. Renamed local variable `config` → `cfg` inside `parseHeader` to avoid the shadow
   that previously hid the import (now also unnecessary).
3. `parseFlight` no longer writes a CSV to disk. Instead, decoded rows are appended
   to `self.flight_rows[fnum] = list[dict]` and surfaced for downstream consumers.
4. Default `convertEngineTemp` flipped from `True` → `False` so EGT/CHT/OILT/CLD/CRB
   stay in their native unit (Fahrenheit on this EDM-830). FlySto's CSV format uses F.
5. Removed `print('extracting flight', ...)` chatter inside `parseFlight`.
6. Removed the `if __name__ == "__main__":` CLI block at the bottom — our own
   `jpiconverter.cli` is the entry point.
7. **GPS LAT/LNG/ALT extraction added** — upstream emits none of these. The
   field-index mapping and accumulation scheme were derived from
   `openenginedata.org`'s browser-side JS converter (assets/jpi_parser/) by
   inspecting its public source on 2026-06-01. Specifically:
     * Initial latitude / longitude live in flight-header words 6-9 as two
       signed 32-bit ints (`(words[6]<<16)|words[7]` for LAT, words[8-9] for LNG),
       scale = decimal degrees × 6000. Zero = no GPS lock at flight start.
     * Per-record GPS deltas are 16-bit signed values combining a low byte at
       field index 86 (LNG) / 87 (LAT) with an optional high byte at index
       81 (LNG) / 82 (LAT). The low-byte field's signflag drives the sign of
       the combined value. Deltas accumulate from 0xF0 and are added to the
       initial position to produce per-sample lat/lng.
     * Altitude (`ALT`, ft) is a delta-encoded single byte at field index 83.
   The field-index numbers and scaling factors are facts about the JPI binary
   format (not copyrightable expression); we re-implemented the algorithm in
   Python rather than copying code.

Apart from the above, the binary-decode logic is byte-for-byte upstream.
