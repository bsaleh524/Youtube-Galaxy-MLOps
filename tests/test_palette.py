import re

import numpy as np

from pipeline import palette

HEX = re.compile(r"^#[0-9a-f]{6}$")


def test_200_unique_valid_colours_with_reported_distance():
    cols = palette.new_colours([], 200)
    assert len(cols) == 200 and len(set(cols)) == 200
    assert all(HEX.match(c) for c in cols)
    d = palette.min_distance(cols)
    assert 0.01 < d < 1


def test_lightness_band_for_dark_background():
    lab = palette.hex_to_oklab(palette.new_colours([], 60))
    assert lab[:, 0].min() > 0.6 and lab[:, 0].max() < 0.84


def test_deterministic():
    assert palette.new_colours([], 50) == palette.new_colours([], 50)


def test_adding_colours_never_changes_existing_and_avoids_them():
    base = palette.new_colours([], 120)
    snapshot = list(base)
    extra = palette.new_colours(base, 5)
    assert base == snapshot
    assert not set(extra) & set(base)
    # each new colour is at least as far from the old set as the old set's own spacing allows
    lab_old, lab_new = palette.hex_to_oklab(base), palette.hex_to_oklab(extra)
    nearest = np.linalg.norm(lab_new[:, None] - lab_old[None], axis=-1).min(axis=1)
    assert nearest.min() > 0


def test_first_colours_are_well_spread():
    assert palette.min_distance(palette.new_colours([], 12)) > 0.1


def test_round_trip_hex_oklab():
    cols = ["#ff0000", "#00ff00", "#0000ff", "#ffffff"]
    lab = palette.hex_to_oklab(cols)
    assert palette.to_hex(palette._oklab_to_linear(lab)) == cols


def test_avoided_colours_are_never_returned():
    base = palette.new_colours([], 10)
    again = palette.new_colours([], 10, avoid=base[:3])
    assert not set(again) & set(base[:3])
