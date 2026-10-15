import numpy as np
from shapely.geometry import LineString

from meteotracker_qc.corridors_v2 import core

LINE = LineString([(0, 0), (1000, 0)])
P = core.PassageParams()


def track(x0, x1, off=0.0, step=10.0, dt=1.0):
    x = np.arange(x0, x1 + (step if x1 > x0 else -step) / 2, step if x1 > x0 else -step, dtype=float)
    return x, np.full_like(x, off), np.arange(len(x)) * dt


def test_three_overlapping_tracks_offsets_and_opposite_direction():
    runs = []
    for x0, x1, off in [(0, 1000, 0.0), (50, 900, 12.0), (1000, 0, -15.0)]:
        runs += core.detect_passages(LINE, *track(x0, x1, off), P)
    assert len(runs) == 3
    assert sorted(r.direction for r in runs) == ["against", "along", "along"]


def test_track_beyond_tolerance_ignored():
    assert core.detect_passages(LINE, *track(0, 1000, 35.0), P) == []


def test_short_touch_is_not_a_passage():
    assert core.detect_passages(LINE, *track(300, 400), P) == []


def test_small_gap_bridged_large_gap_splits():
    x, y, t = track(0, 1000)
    y_small = y.copy(); y_small[(x > 500) & (x < 530)] = 50  # 30 m off-corridor -> bridged
    assert len(core.detect_passages(LINE, x, y_small, t, P)) == 1
    y_big = y.copy(); y_big[(x > 450) & (x < 560)] = 50  # ~110 m gap -> two runs of >=250 m
    r = core.detect_passages(LINE, x, y_big, t, P)
    assert len(r) == 2


def test_time_gap_splits():
    x, y, t = track(0, 1000)
    t = t.copy(); t[x > 500] += 300
    r = core.detect_passages(LINE, x, y, t, P)
    assert len(r) == 2


def test_u_turn_gives_two_passages():
    xa, ya, ta = track(0, 600)
    xb, yb, tb = track(600, 0)
    r = core.detect_passages(LINE, np.r_[xa, xb[1:]], np.r_[ya, yb[1:]], np.r_[ta, ta[-1] + 1 + tb[1:]], P)
    assert [q.direction for q in r] == ["along", "against"]


def test_bins_covered():
    assert core.bins_covered((0, 260), 1000, 100) == [0, 1, 2]  # 60 m of bin 2 >= 50%
    assert core.bins_covered((0, 240), 1000, 100) == [0, 1]  # 40 m of bin 2 < 50%
    assert core.bins_covered((0, 1000), 1000, 250) == [0, 1, 2, 3]


def test_skeleton_of_bar_gives_single_line():
    img = np.zeros((60, 9), bool); img[5:55, 3:6] = True
    S = core.zhang_suen(img)
    strokes = core.merge_strokes(core.skeleton_edges(S), 20.0)
    ln = max((core.pixels_to_line(s, 0, 0, 20.0) for s in strokes), key=lambda l: l.length)
    assert ln.length > 40 * 20

