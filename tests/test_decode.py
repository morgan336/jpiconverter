from datetime import datetime
from pathlib import Path

from jpiconverter.decode import decode
from jpiconverter.parser.edm import EDMData

FIXTURE = Path(__file__).parent / "fixtures" / "U260220.JPI"


def test_smoke_vendored_parser_runs():
    edm = EDMData(str(FIXTURE))
    edm.read()
    edm.parseHeader()
    edm.parseFlights(additional_columns=None)

    assert edm.config["TAIL NO"] == "N218CD"
    assert edm.config["EDM TYPE"] == 830

    # The $D directory in this file lists 16 flights, numbered 351..366.
    assert sorted(edm.flight_rows.keys()) == list(range(351, 367))

    # Every flight should have at least one decoded sample.
    for fnum, rows in edm.flight_rows.items():
        assert len(rows) > 0, f"flight {fnum} decoded zero rows"
        first = rows[0]
        assert "date" in first
        assert "EGT1" in first
        assert "HOURS" in first


def test_gps_decode_matches_ground_truth():
    """At 2026-01-30 19:18:58 (flight 354 sample 778) the openenginedata.org
    converter reports lat 41.292333 / long -73.266333. Our decoder must match
    exactly."""
    flights, _ = decode(FIXTURE.read_bytes())
    flight_354 = next(f for f in flights if f.number == 354)
    target = datetime(2026, 1, 30, 19, 18, 58)
    sample = next(s for s in flight_354.samples if s.timestamp == target)

    # 6-decimal precision is what openenginedata displays; we keep full float.
    assert round(sample.lat, 6) == 41.292333
    assert round(sample.lng, 6) == -73.266333
    assert sample.alt is not None and sample.alt > 0  # altitude is also populated
