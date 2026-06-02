import csv
import io
from datetime import datetime

from jpiconverter.decode import Flight, Sample
from jpiconverter.flysto import HEADER, NUM_COLUMNS, to_flysto_csv


def _make_sample(ts: datetime, **overrides) -> Sample:
    s = Sample(timestamp=ts)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_header_is_39_columns():
    assert NUM_COLUMNS == 39
    assert HEADER[0] == "INDEX"
    assert HEADER[-1] == "MARK"


def test_header_matches_template():
    """Hardcoded HEADER must stay in sync with JPI-V1-Template.csv."""
    from pathlib import Path
    template = Path(__file__).resolve().parent.parent / "JPI-V1-Template.csv"
    with template.open(newline="") as f:
        template_header = next(csv.reader(f))
    assert HEADER == template_header


def test_round_trip_minimal_two_sample_flight():
    flight = Flight(
        number=1,
        samples=[
            _make_sample(
                datetime(2026, 1, 31, 14, 30, 15),
                egt=[1234, 1256, 1262, 1287, 1246, 1257],
                cht=[281, 255, 270, 243, 254, 291],
                oat=15, map=30.2, rpm=2000, hp=95, ff=9.9,
                oil_p=55, bat=27.8, hrs=321.8, spd=120,
            ),
            _make_sample(
                datetime(2026, 1, 31, 14, 30, 16),
                egt=[1235, 1257, 1263, 1288, 1247, 1258],
                cht=[282, 256, 271, 244, 255, 292],
                oat=15, map=30.3, rpm=2001, hp=95, ff=10.0,
                oil_p=56, bat=27.9, hrs=321.9, spd=121,
            ),
        ],
    )

    csv_bytes = to_flysto_csv([flight])

    # CRLF only — no bare LF.
    text = csv_bytes.decode("utf-8")
    assert "\r\n" in text
    assert text.count("\n") == text.count("\r\n"), "found a bare LF"

    rows = list(csv.reader(io.StringIO(text)))
    assert len(rows) == 4, "header + tach + 2 data rows"
    assert rows[0] == HEADER
    assert all(len(r) == NUM_COLUMNS for r in rows)

    # Tach row populated correctly
    assert rows[1][0] == "Engine - Tach Start = 321.8"
    assert rows[1][1] == "Tach End = 321.9"
    assert rows[1][2] == "Tach Duration = 0.1"
    assert all(c == "" for c in rows[1][3:])

    # Data row 0 spot checks
    r0 = dict(zip(HEADER, rows[2]))
    assert r0["INDEX"] == "0"
    assert r0["DATE"] == "1/31/2026"   # no zero-pad on month/day
    assert r0["TIME"] == "14:30:15"
    assert r0["E1"] == "1234"
    assert r0["MAP"] == "30.2"
    assert r0["BAT"] == "27.8"
    assert r0["HRS"] == "321.8"
    assert r0["USD2"] == "NA"          # template literal for missing 2nd tank
    assert r0["LAT"] == ""             # no GPS position in this sample
    assert r0["LNG"] == ""
    assert r0["MARK"] == ""
    assert r0["DIF"] == str(1287 - 1234)  # derived from EGT span


def test_index_monotonic_across_multiple_flights():
    flights = [
        Flight(number=1, samples=[_make_sample(datetime(2026, 1, 1, 10, 0, 0), hrs=10.0)]),
        Flight(number=2, samples=[
            _make_sample(datetime(2026, 1, 2, 10, 0, 0), hrs=10.5),
            _make_sample(datetime(2026, 1, 2, 10, 0, 6), hrs=10.6),
        ]),
    ]
    rows = list(csv.reader(io.StringIO(to_flysto_csv(flights).decode("utf-8"))))
    data_rows = rows[2:]
    indexes = [r[0] for r in data_rows]
    assert indexes == ["0", "1", "2"]


def test_tach_duration_sums_per_flight():
    flights = [
        Flight(number=1, samples=[
            _make_sample(datetime(2026, 1, 1, 10, 0, 0), hrs=100.0),
            _make_sample(datetime(2026, 1, 1, 10, 30, 0), hrs=100.5),
        ]),
        Flight(number=2, samples=[
            _make_sample(datetime(2026, 1, 2, 10, 0, 0), hrs=101.0),
            _make_sample(datetime(2026, 1, 2, 11, 0, 0), hrs=102.0),
        ]),
    ]
    rows = list(csv.reader(io.StringIO(to_flysto_csv(flights).decode("utf-8"))))
    assert rows[1][0] == "Engine - Tach Start = 100.0"
    assert rows[1][1] == "Tach End = 102.0"
    # 0.5 + 1.0 = 1.5 (not 2.0 which would be wall-clock span)
    assert rows[1][2] == "Tach Duration = 1.5"
