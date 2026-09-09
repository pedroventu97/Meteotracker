"""Senior review: scientific row uniqueness and stable reciprocal evidence."""
import dataclasses
import numpy as np
import pandas as pd
import pytest
from test_repeated_routes_memberships import fixture
from test_repeated_routes import CFG
from meteotracker_qc.repeated_routes.segments import consolidate_segments
from meteotracker_qc.repeated_routes.memberships import build_point_segment_memberships

SEMANTIC_KEY=['repeated_segment_id','segment_passage_id','source_file','source_row']


def test_one_scientific_membership_two_supports_unweighted_temperature():
    parts,matches,std=fixture(True)
    from test_repeated_routes import make_part
    from meteotracker_qc.repeated_routes.matching import match_tracks
    a=parts['a::part1']
    c=make_part('c',1,a.points.assign(source_file='c.csv'))
    parts[c.track_id]=c; std['c']=c.points
    ab=[m for m in matches if m['track_id_a']=='a::part1' and m['track_id_b']=='b::part1']
    ac=match_tracks(a.track_id,a.resampled,c.track_id,c.resampled,CFG)[0]
    ac.update(a_start_m=10.,b_start_m=10.)
    _,passages,evidence=consolidate_segments(parts,ab+[ac],std,CFG)
    points=build_point_segment_memberships(parts,passages,evidence,CFG)
    assert not points.duplicated(SEMANTIC_KEY).any()
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_tables
    points,support=build_point_segment_tables(parts,passages,evidence,CFG)
    counts=support.groupby('membership_id').size()
    two=points[(points.campaign_id=='a') & points.membership_id.isin(counts[counts==2].index)].iloc[0]
    assert len(points[points.membership_id==two.membership_id])==1
    assert len(support[support.membership_id==two.membership_id])==2
    # Edge points have one support, interior points two: averaging evidence
    # would bias an actual temperature statistic for this very passage.
    same=points[points.segment_passage_id==two.segment_passage_id].copy()
    same['temperature_c']=np.where(same.membership_id.map(counts)==2,30.,10.)
    assert set(same.temperature_c)=={10.,30.}
    observations=same[['source_file','source_row','temperature_c']].copy()
    joined=same.drop(columns='temperature_c').merge(observations,on=['source_file','source_row'],validate='one_to_one')
    assert joined.temperature_c.mean()==pytest.approx(observations.temperature_c.mean())
    expanded=joined.merge(support,on='membership_id',validate='one_to_many')
    assert expanded.temperature_c.mean()!=pytest.approx(joined.temperature_c.mean())
    assert set(points.membership_id)==set(support.membership_id)


def test_duplicate_run_diagnostics_do_not_depend_on_run_order(monkeypatch):
    import meteotracker_qc.repeated_routes.matching as mod
    parts,_,_=fixture(True);a,b=list(parts.values())[:2]
    s=np.arange(0,1001,10,dtype=float)
    run=mod.RunResult(0,100,0.,1000.,s,s,np.zeros(len(s)))
    duplicate=dataclasses.replace(run,dist_matched=np.full(len(s),5.))
    def match(order):
        calls=iter([[run],order])
        monkeypatch.setattr(mod,'find_runs',lambda *args:next(calls))
        return mod.match_tracks(a.track_id,a.resampled,b.track_id,b.resampled,CFG)
    first=match([run,duplicate]); second=match([duplicate,run])
    assert len(first)==len(second)==1
    assert first==second


def test_overlap_threshold_applies_to_emitted_reciprocal_interval(monkeypatch):
    import meteotracker_qc.repeated_routes.matching as mod
    parts,_,_=fixture(True);a,b=list(parts.values())[:2]
    s=np.arange(0,1001,10,dtype=float)
    ra=mod.RunResult(0,100,0.,1000.,s,s,np.zeros(len(s)))
    rb=mod.RunResult(0,30,0.,600.,s[:31],np.linspace(0,600,31),np.zeros(31))
    calls=iter([[ra],[rb]])
    monkeypatch.setattr(mod,'find_runs',lambda *args:next(calls))
    # Actual emitted lengths would be A=1000 and B=300 (0.30, below 0.70).
    assert mod.match_tracks(a.track_id,a.resampled,b.track_id,b.resampled,CFG)==[]

def test_qc_exclusion_source_identity_boundaries_and_table_determinism():
    from meteotracker_qc.repeated_routes.tracks import prepare_campaign_tracks
    from meteotracker_qc.repeated_routes.matching import match_tracks
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_tables
    _,_,std=fixture(True)
    original=std['a'].copy()
    original.loc[original.source_row==50,'use_for_route_mapping']=False
    duplicate=original.iloc[[0]].assign(source_row=999)
    # Reverse input order; preserve tie order of the real point before duplicate.
    shuffled=pd.concat([original.iloc[::-1],duplicate],ignore_index=True)
    a=prepare_campaign_tracks('a',shuffled,CFG).parts[0]
    b=prepare_campaign_tracks('b',std['b'],CFG).parts[0]
    assert 999 not in set(a.points.source_row)
    assert 50 not in set(a.points.source_row)
    assert set(a.points.source_row)==set(original.source_row)-{50}
    assert set(a.resampled.source_point_before)<=set(a.points.source_row)
    parts={a.track_id:a,b.track_id:b}
    matches=match_tracks(a.track_id,a.resampled,b.track_id,b.resampled,CFG)
    _,passages,evidence=consolidate_segments(parts,matches,{'a':shuffled,'b':std['b']},CFG)
    points,support=build_point_segment_tables(parts,passages,evidence,CFG)
    selected=points[points.campaign_id=='a']
    assert {0,200}<=set(selected.source_row)
    assert not set(selected.source_row)&{50,999}
    truth=original.set_index('source_row')
    for p in selected.itertuples():
        assert p.source_file==truth.loc[p.source_row,'source_file']
        assert p.timestamp==truth.loc[p.source_row,'time_utc'].isoformat()
        assert p.longitude==truth.loc[p.source_row,'Lon']
        assert p.latitude==truth.loc[p.source_row,'Lat']
    reversed_tables=build_point_segment_tables(parts,passages.iloc[::-1],evidence.iloc[::-1],CFG)
    for first,second in zip((points,support),reversed_tables):
        pd.testing.assert_frame_equal(first,second)


def test_point_within_interval_but_far_from_geometry_is_not_assigned():
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_tables
    parts,matches,std=fixture(True)
    _,passages,evidence=consolidate_segments(parts,matches,std,CFG)
    a=parts['a::part1']
    # An observation has the correct arc position, but fails the independent
    # distance check against the passage geometry already produced.
    a.points.loc[a.points.source_row==100,'x_m']+=1000
    points,_=build_point_segment_tables(parts,passages,evidence,CFG)
    assert points[(points.campaign_id=='a') & (points.source_row==100)].empty


def test_previous_pair_algorithm_cache_is_not_reused(tmp_path):
    from test_repeated_routes_cache import _part
    from meteotracker_qc.repeated_routes.cache import RepeatedRoutesCache,pair_metadata,stable_hash
    a,b=_part('a'),_part('b',2)
    current=pair_metadata(a,'ka',b,'kb',CFG)
    previous={**current,'pair_algorithm_version':'pair-v2-reusable-runs'}
    cache=RepeatedRoutesCache(tmp_path)
    try:
        cache.save_pair(stable_hash(previous),previous,(a.track_id,b.track_id),[])
        key,payload=cache.load_pair(current,(a.track_id,b.track_id))
        assert key!=stable_hash(previous)
        assert payload is None
    finally:
        cache.close()
