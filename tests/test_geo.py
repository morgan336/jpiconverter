from jpiconverter.geo import to_lat_dms, to_lng_dms


def test_template_sample_values():
    # The JPI-V1-Template ships with N35.35.35 / W120.20.20 as sample cells.
    # Reproduce them exactly so any future change here is loud.
    assert to_lat_dms(35 + 35 / 60 + 35 / 3600) == "N35.35.35"
    assert to_lng_dms(-(120 + 20 / 60 + 20 / 3600)) == "W120.20.20"


def test_hemisphere_flips():
    assert to_lat_dms(-10.5).startswith("S")
    assert to_lng_dms(10.5).startswith("E")


def test_equator_and_prime_meridian():
    assert to_lat_dms(0) == "N00.00.00"
    assert to_lng_dms(0) == "E000.00.00"


def test_single_digit_lat_degree_is_zero_padded():
    # N07.05.05 not N7.5.5 — defensive default until FlySto confirms.
    assert to_lat_dms(7 + 5 / 60 + 5 / 3600) == "N07.05.05"


def test_three_digit_lng_degree():
    assert to_lng_dms(120 + 20 / 60 + 20 / 3600) == "E120.20.20"


def test_second_carry_to_minute_and_degree():
    # 59 minutes 59.6 seconds should round up to next minute (and may cascade).
    # 35.999889 deg = 35 deg 59 min 59.6 sec -> rounds to 36 deg 00 min 00 sec.
    assert to_lat_dms(35 + 59 / 60 + 59.6 / 3600) == "N36.00.00"


def test_none_returns_blank():
    assert to_lat_dms(None) == ""
    assert to_lng_dms(None) == ""
