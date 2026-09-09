import itertools
import numpy as np
import pandas as pd
import pytest
from test_repeated_routes import CFG, T0, X0, Y0, make_part, make_points_df
from meteotracker_qc.repeated_routes.matching import match_tracks
from meteotracker_qc.repeated_routes.segments import consolidate_segments


def fixture(contained=False, reverse=False):
    specs=[('a',0,1000,0),('b',0,1000 if contained else 700,2),('c',400,700 if contained else 1000,-2)]
    parts={}
    for name,start,end,offset in specs:
        backwards=reverse and name=='b'
        pts=make_points_df(X0+offset,Y0+(end if backwards else start),0,-5 if backwards else 5,int((end-start)/5)+1,T0)
        pts['source_file']=name+'.csv'
        pts['use_for_route_mapping']=True; pts['qc_coord_missing']=False
        p=make_part(name,1,pts); parts[p.track_id]=p
    matches=[]
    for a,b in itertools.combinations(parts.values(),2):
        matches.extend(match_tracks(a.track_id,a.resampled,b.track_id,b.resampled,CFG))
    return parts,matches,{p.campaign_id:p.points for p in parts.values()}

@pytest.mark.parametrize('contained',[False,True])
def test_distinct_extents_and_multiple_original_memberships(contained):
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_memberships
    parts,matches,std=fixture(contained)
    seg,passages,evidence=consolidate_segments(parts,matches,std,CFG)
    assert len(seg)>=2
    ab=set(evidence[(evidence.track_id_a=='a::part1') & (evidence.track_id_b=='b::part1')].repeated_segment_id)
    ac=set(evidence[(evidence.track_id_a=='a::part1') & (evidence.track_id_b=='c::part1')].repeated_segment_id)
    assert ab and ac and ab.isdisjoint(ac)
    if contained:
        assert seg[seg.repeated_segment_id.isin(ab)].segment_length_m.max()>=990
    points=build_point_segment_memberships(parts,passages,evidence,CFG)
    a=points[points.campaign_id=='a']
    assert a.groupby(['source_file','source_row']).repeated_segment_id.nunique().max()>=2
    assert not points.duplicated(['repeated_segment_id','segment_passage_id','source_file','source_row']).any()


def test_exact_duplicate_and_input_order():
    parts,matches,std=fixture(True)
    first=consolidate_segments(parts,matches,std,CFG)
    second=consolidate_segments(parts,list(reversed(matches))+[matches[0]],std,CFG)
    for a,b in zip(first,second):
        pd.testing.assert_frame_equal(a,b)


def test_reciprocal_run_reused(monkeypatch):
    import meteotracker_qc.repeated_routes.matching as mod
    parts,_,_=fixture()
    a,b=list(parts.values())[:2]
    def run(lo,hi,to_lo,to_hi):
        s=np.arange(lo,hi+1,10,dtype=float)
        return mod.RunResult(lo//10,hi//10,to_lo,to_hi,s,np.linspace(to_lo,to_hi,len(s)),np.zeros(len(s)))
    calls=iter([[run(0,300,0,300),run(400,700,400,700)],[run(0,700,0,700)]])
    monkeypatch.setattr(mod,'find_runs',lambda *args:next(calls))
    found=mod.match_tracks(a.track_id,a.resampled,b.track_id,b.resampled,CFG)
    assert len(found)==2
    assert [m["n_matched_points_b"] for m in found]==[31,31]


def test_opposite_direction_memberships():
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_memberships
    parts,matches,std=fixture(True,True)
    seg,passages,evidence=consolidate_segments(parts,matches,std,CFG)
    points=build_point_segment_memberships(parts,passages,evidence,CFG)
    ab=evidence[(evidence.track_id_a=='a::part1') & (evidence.track_id_b=='b::part1')].repeated_segment_id.iloc[0]
    subset=points[points.repeated_segment_id==ab]
    assert set(subset.passage_direction)=={'same_direction','opposite_direction'}
    b=subset[subset.campaign_id=='b'].sort_values('track_position_m')
    assert b.segment_position_m.iloc[0]>b.segment_position_m.iloc[-1]


def test_return_near_itself_keeps_interval():
    from meteotracker_qc.repeated_routes.memberships import build_point_segment_memberships
    parts,matches,std=fixture(True)
    seg,passages,evidence=consolidate_segments(parts,matches,std,CFG)
    p=parts['a::part1']; extra=p.points.copy()
    extra['cum_distance_m']+=2000; extra['source_row']+=10000
    extra['time_utc']+=pd.Timedelta(hours=1)
    p.points=pd.concat([p.points,extra],ignore_index=True)
    points=build_point_segment_memberships(parts,passages,evidence,CFG)
    assert points[points.campaign_id=='a'].source_row.max()<10000


@pytest.mark.parametrize('empty',[False,True])
def test_output_compatibility_and_round_trip(tmp_path, empty):
    import geopandas as gpd
    import json
    from meteotracker_qc.repeated_routes.pipeline import run_pipeline, write_outputs
    from meteotracker_qc.pipeline import _campaign_output_dir
    parts,_,_=fixture(True)
    raw=tmp_path/'raw'; raw.mkdir()
    qc=tmp_path/'qc'
    records=[]
    for p in list(parts.values())[:1 if empty else 3]:
        name=p.campaign_id+'.csv'
        path=raw/name; path.write_text('synthetic input',encoding='utf-8')
        df=p.points.copy(); df['dt_s']=1.0
        for col in ['qc_stationary','qc_coord_repeated','qc_possible_gps_freeze','qc_gps_freeze']:
            df[col]=False
        out=_campaign_output_dir(path,raw,qc); out.mkdir(parents=True)
        df.to_parquet(out/(p.campaign_id+'_standardized.parquet'),index=False)
        records.append({'source_file':name,'exclude_from_analysis':False})
    manifest=tmp_path/'manifest.csv'; pd.DataFrame(records).to_csv(manifest,index=False)
    result=run_pipeline(raw_dir=raw,qc_output_dir=qc,qc_config_path=tmp_path/'unused.yaml',
                        qc_profile='recommended',manifest_path=manifest,rr_config=CFG,refresh_qc=False)
    out=tmp_path/'result'; write_outputs(result,out)
    layers=set(gpd.list_layers(out/'repeated_routes.gpkg').name)
    assert layers=={'campaign_tracks','campaign_parts','excluded_or_low_quality_tracks',
                    'repeated_segments','segment_passages','pairwise_matches','point_segment_memberships','point_segment_match_support'}
    for name in ['campaign_inventory.csv','candidate_pairs.csv','comparison_opportunities.csv','point_segment_memberships.csv','point_segment_match_support.csv']:
        assert (out/name).exists()
    table=pd.read_csv(out/'point_segment_memberships.csv')
    spatial=gpd.read_file(out/'repeated_routes.gpkg',layer='point_segment_memberships')
    pd.testing.assert_frame_equal(table, pd.DataFrame(spatial.drop(columns='geometry')),
                                  check_dtype=False, check_exact=False, atol=1e-10)
    support=pd.read_csv(out/'point_segment_match_support.csv')
    persisted_support=gpd.read_file(out/'repeated_routes.gpkg',layer='point_segment_match_support')
    pd.testing.assert_frame_equal(support, persisted_support, check_dtype=False)
    assert not table.duplicated(['repeated_segment_id','segment_passage_id','source_file','source_row']).any()
    assert set(table.membership_id)==set(support.membership_id)
    assert not support.duplicated().any()
    assert spatial.crs.to_epsg()==4326
    summary=json.loads((out/'membership_summary.json').read_text())
    if empty:
        assert table.empty
    else:
        assert summary['n_original_points_in_multiple_segments']>0
        assert support.supporting_match_id.isin(result.matches_df.supporting_match_id).all()
        assert set(table.source_file)=={'a.csv','b.csv','c.csv'}


def test_no_transitive_corridor_union_and_match_supports_two_segments():
    from test_repeated_routes_cache import _part
    from meteotracker_qc.repeated_routes.corridors import canonical_matches
    # Adjacent evidence compatible; the extreme corridors are 30 m apart.
    parts={p.track_id:p for p in [_part('a',-10),_part('b',0),_part('c',10),_part('d',20)]}
    base={'a_start_m':0.,'a_end_m':500.,'b_start_m':0.,'b_end_m':500.,
          'shared_length_m':500.,'overlap_fraction':1.,'direction_class':'same_direction',
          'mean_matching_distance_m':1.,'p90_matching_distance_m':1.,
          'n_matched_points_a':51,'n_matched_points_b':51}
    matches=[dict(base,track_id_a=a+'::part1',track_id_b=b+'::part1') for a,b in [('a','b'),('b','c'),('c','d')]]
    seg,passages,evidence=consolidate_segments(parts,matches,{p.campaign_id:p.points for p in parts.values()},CFG)
    assert len(seg)>=2
    assert not any(set(g.campaign_id)=={'a','b','c','d'} for _,g in passages.groupby('repeated_segment_id'))
    assert evidence.groupby('supporting_match_id').repeated_segment_id.nunique().max()==2
    assert set(evidence.supporting_match_id)=={m['supporting_match_id'] for m in canonical_matches(matches)}


def test_original_source_file_survives_track_preparation():
    from meteotracker_qc.repeated_routes.tracks import prepare_campaign_tracks
    _,_,std=fixture(True)
    tracks=prepare_campaign_tracks('a',std['a'],CFG)
    assert set(tracks.parts[0].points.source_file)=={'a.csv'}


def test_real_geometry_two_runs_share_one_reciprocal_run():
    from test_repeated_routes import _INV
    from meteotracker_qc.repeated_routes.matching import find_runs
    from shapely.geometry import LineString
    coords=[]
    for p,q in [((0,0),(0,500)),((0,500),(100,600)),((100,600),(10,500)),((10,500),(10,0))]:
        n=int(np.hypot(q[0]-p[0],q[1]-p[1])/5)+1
        coords.extend(np.linspace(p,q,n)[:-1])
    coords.append((10,0)); xy=np.array(coords)
    a=make_points_df(X0,Y0,0,5,len(xy),T0)
    a['x_m']=X0+xy[:,0]; a['y_m']=Y0+xy[:,1]
    a['cum_distance_m']=np.r_[0,np.cumsum(np.hypot(np.diff(xy[:,0]),np.diff(xy[:,1])))]
    b=make_points_df(X0+8,Y0,0,5,101,T0)
    b['x_m']=X0+np.where(np.arange(101)<50,8,2)
    b['cum_distance_m']=np.r_[0,np.cumsum(np.hypot(np.diff(b.x_m),np.diff(b.y_m)))]
    for df in (a,b):
        df['Lon'],df['Lat']=_INV.transform(df.x_m,df.y_m)
    pa,pb=make_part('a',1,a),make_part('b',1,b)
    line_a=LineString(zip(pa.resampled.x_m,pa.resampled.y_m))
    line_b=LineString(zip(pb.resampled.x_m,pb.resampled.y_m))
    assert len(find_runs(pa.resampled,line_b,CFG))==2
    assert len(find_runs(pb.resampled,line_a,CFG))==1
    matches=match_tracks(pa.track_id,pa.resampled,pb.track_id,pb.resampled,CFG)
    assert len(matches)==2
    assert matches[0]['a_end_m']<matches[1]['a_start_m']
    assert matches[0]['b_start_m']==matches[1]['b_start_m']
    assert matches[0]['b_end_m']==matches[1]['b_end_m']
