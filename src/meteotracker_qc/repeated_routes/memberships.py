"""Unique scientific memberships and separate, lossless match support relations."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
from shapely.geometry import LineString, Point
from .matching import project_onto_line

MEMBERSHIP_COLUMNS = [
    'membership_id', 'repeated_segment_id', 'segment_passage_id', 'campaign_id', 'track_part_id',
    'source_file', 'source_row', 'timestamp', 'longitude', 'latitude',
    'track_position_m', 'segment_position_m', 'distance_to_passage_m',
    'passage_direction', 'membership_basis',
    'geographic_crs', 'metric_crs', 'geometry',
]
MEMBERSHIP_KEY = ['repeated_segment_id','segment_passage_id','source_file','source_row']
SUPPORT_COLUMNS = ['membership_id', 'supporting_match_id']


def build_point_segment_tables(parts, passages, matches, cfg):
    """Return (unique scientific memberships, membership-to-match support)."""
    rows=[]
    for segment_id, group in passages.groupby('repeated_segment_id', sort=True):
        ref=group[group.is_reference].iloc[0]
        r=parts[ref.track_id].resampled
        r=r[r.distance_along_track_m.between(ref.reference_start_m,ref.reference_end_m)]
        coords=list(zip(r.x_m,r.y_m))
        if coords[0]>coords[-1]: coords.reverse()
        reference=LineString(coords)
        evidence=matches[matches.repeated_segment_id==segment_id]
        for p in group.itertuples():
            part=parts[p.track_id]
            r=part.resampled
            r=r[r.distance_along_track_m.between(p.track_start_m,p.track_end_m)]
            passage=LineString(list(zip(r.x_m,r.y_m)))
            # Arc interval is evaluated before spatial proximity: returning near
            # a previous location cannot select a later observation accidentally.
            points=part.points[part.points.cum_distance_m.between(p.track_start_m,p.track_end_m)]
            if points.empty: continue
            if 'source_file' not in points or points.source_file.isna().any():
                raise ValueError(f'Missing original source_file for {p.track_id}')
            distances,_=project_onto_line(passage,points.x_m.to_numpy(),points.y_m.to_numpy())
            _,positions=project_onto_line(reference,points.x_m.to_numpy(),points.y_m.to_numpy())
            support=[]
            for m in evidence.itertuples():
                if m.track_id_a==p.track_id: support.append((m.supporting_match_id,m.a_start_m,m.a_end_m))
                if m.track_id_b==p.track_id: support.append((m.supporting_match_id,m.b_start_m,m.b_end_m))
            for point,distance,position in zip(points.to_dict('records'),distances,positions):
                if distance>cfg.matching_tolerance_m: continue
                for match_id,lo,hi in support:
                    if not lo<=point['cum_distance_m']<=hi: continue
                    rows.append({
                        'repeated_segment_id':segment_id,'segment_passage_id':p.segment_passage_id,
                        'campaign_id':part.campaign_id,'track_part_id':part.track_id,
                        'source_file':point['source_file'],'source_row':point['source_row'],
                        'timestamp':point['time_utc'].isoformat(),
                        'longitude':point['Lon'],'latitude':point['Lat'],
                        'track_position_m':point['cum_distance_m'],'segment_position_m':float(position),
                        'distance_to_passage_m':float(distance),'passage_direction':p.normalized_direction,
                        'membership_basis':'original_qc_point_track_interval_and_passage_distance',
                        'supporting_match_id':match_id,
                        'geographic_crs':f'EPSG:{cfg.crs_geographic_epsg}',
                        'metric_crs':f'EPSG:{cfg.crs_metric_epsg}',
                        'geometry':Point(point['Lon'],point['Lat']),
                    })
    evidence_columns = [c for c in MEMBERSHIP_COLUMNS if c != 'membership_id'] + ['supporting_match_id']
    result = pd.DataFrame(rows, columns=evidence_columns)
    # IDs describe semantic membership, never which/how many matches support it.
    result['membership_id'] = [
        'membership_' + hashlib.sha256(json.dumps(
            [segment, passage, source, int(row)], ensure_ascii=True,
            separators=(',', ':'),
        ).encode('utf-8')).hexdigest()
        for segment, passage, source, row in result[MEMBERSHIP_KEY].itertuples(index=False, name=None)
    ]
    support = result[SUPPORT_COLUMNS].drop_duplicates().sort_values(SUPPORT_COLUMNS).reset_index(drop=True)
    memberships = result[MEMBERSHIP_COLUMNS].drop_duplicates(MEMBERSHIP_KEY)
    memberships = memberships.sort_values(MEMBERSHIP_KEY, kind='stable').reset_index(drop=True)
    return memberships, support


def build_point_segment_memberships(parts, passages, matches, cfg):
    """Scientific table only. Use build_point_segment_tables for full provenance."""
    return build_point_segment_tables(parts, passages, matches, cfg)[0]


def membership_metrics(points, support):
    unique=points.drop_duplicates(MEMBERSHIP_KEY)
    counts=unique.groupby(['campaign_id','source_file','source_row']).repeated_segment_id.nunique()
    return {'n_membership_evidence_rows':len(support), 'n_point_segment_match_support':len(support),
            'n_point_segment_memberships':len(unique),
            'n_duplicate_semantic_memberships':int(points.duplicated(MEMBERSHIP_KEY).sum()),
            'n_memberships_without_support':int((~points.membership_id.isin(support.membership_id)).sum()),
            'n_original_points_with_memberships':len(counts),
            'n_original_points_in_multiple_segments':int((counts>1).sum())}
