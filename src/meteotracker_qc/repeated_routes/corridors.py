"""Non-transitive corridor identity and deterministic pairwise evidence."""
from __future__ import annotations

import hashlib
import json
import numpy as np
from scipy.stats import spearmanr
from shapely.geometry import LineString, Point
from .matching import project_onto_line


def evidence_key(match):
    sides = sorted((
        (match['track_id_a'], float(match['a_start_m']), float(match['a_end_m'])),
        (match['track_id_b'], float(match['b_start_m']), float(match['b_end_m'])),
    ))
    return tuple(sides)


def canonical_matches(matches):
    unique = {}
    for original in matches:
        m = dict(original)
        if m['track_id_a'] > m['track_id_b']:
            for a, b in [('track_id_a','track_id_b'),('a_start_m','b_start_m'),('a_end_m','b_end_m'),('n_matched_points_a','n_matched_points_b')]:
                m[a], m[b] = m[b], m[a]
        key = evidence_key(m)
        # Deterministic representative also when equivalent evidence has different diagnostics.
        rank = json.dumps(m, sort_keys=True, default=str)
        if key not in unique or rank < unique[key][0]:
            unique[key] = (rank,m)
    result=[]
    for key, (_,m) in sorted(unique.items()):
        m['supporting_match_id'] = 'match_' + hashlib.sha256(repr(key).encode()).hexdigest()[:20]
        result.append(m)
    return result


def corridor_groups(parts, matches, cfg):
    """Maximal complete compatibility sets, split by connected pairwise evidence.

    Complete sets prohibit A~B~C chaining when A and C differ. A match may
    support more than one maximal set. Disconnected campaign evidence remains
    separate until a shared passage connects it.
    """
    intervals=[]; lines=[]
    for m in matches:
        iv=dict((track,(lo,hi)) for track,lo,hi in evidence_key(m))
        intervals.append(iv)
        geometries=[]
        for track,(lo,hi) in iv.items():
            r=parts[track].resampled
            r=r[r.distance_along_track_m.between(lo,hi)]
            geometries.append(LineString(list(zip(r.x_m,r.y_m))))
        lines.append(geometries)

    def same_line(a,b):
        # Compare extent, endpoints in either direction, and entire corridor.
        tol=cfg.matching_tolerance_m
        if abs(a.length-b.length)>2*tol:
            return False
        aa,az=Point(a.coords[0]),Point(a.coords[-1])
        ba,bz=Point(b.coords[0]),Point(b.coords[-1])
        ends=min(max(aa.distance(ba),az.distance(bz)),max(aa.distance(bz),az.distance(ba)))
        if ends>tol or a.hausdorff_distance(b)>tol:
            return False
        # Same footprint is insufficient for loops/backtracking: normalized
        # traversal order must also agree, using the existing direction threshold.
        for source,target in ((a,b),(b,a)):
            xy=np.asarray(source.coords)
            _,arc=project_onto_line(target,xy[:,0],xy[:,1])
            if len(arc)>2:
                corr=float(spearmanr(np.arange(len(arc)),arc).statistic)
                if not np.isfinite(corr) or abs(corr)<cfg.direction_correlation_threshold:
                    return False
        return True

    adjacency={i:set() for i in range(len(matches))}
    for i in range(len(matches)):
        for j in range(i):
            common=intervals[i].keys() & intervals[j].keys()
            if any(max(abs(a-b) for a,b in zip(intervals[i][t],intervals[j][t]))>cfg.resampling_distance_m+1e-6 for t in common):
                continue
            if all(same_line(a,b) for a in lines[i] for b in lines[j]):
                adjacency[i].add(j); adjacency[j].add(i)

    cliques=[]
    def visit(r,p,x):
        if not p and not x:
            cliques.append(r); return
        pivot=max(sorted(p|x),key=lambda u:len(p & adjacency[u])) if p|x else None
        for v in sorted(p - (adjacency[pivot] if pivot is not None else set())):
            visit(r|{v},p & adjacency[v],x & adjacency[v])
            p.remove(v); x.add(v)
    visit(set(),set(adjacency),set())
    groups=set()
    for clique in cliques:
        remaining=set(clique)
        while remaining:
            connected={min(remaining)}; remaining-=connected
            while True:
                tracks=set().union(*(intervals[i].keys() for i in connected))
                added={j for j in remaining if tracks & intervals[j].keys()}
                if not added: break
                connected |= added; remaining -= added
            groups.add(tuple(sorted(connected)))
    # A split clique can yield a redundant subset of another connected clique.
    return [g for g in sorted(groups) if not any(set(g)<set(h) for h in groups)]
