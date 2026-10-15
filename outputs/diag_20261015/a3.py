import pandas as pd, numpy as np, json
from scipy import ndimage
from pyproj import Transformer
T=Transformer.from_crs(32632,4326,always_xy=True)
pc=pd.read_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_parts.parquet"); sc=pd.read_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_pas.parquet")
seg=pd.read_csv(r"D:\projects\Meteotracker\outputs\repeated_routes_20261015T0835\repeated_segments.csv")
inv=pd.read_csv(r"D:\projects\Meteotracker\outputs\repeated_routes_20261015T0835\campaign_inventory.csv")
cnt=pc.groupby(["i","j"]).cid.nunique()
i0,j0=cnt.index.get_level_values(0).min(),cnt.index.get_level_values(1).min()
W=cnt.index.get_level_values(0).max()-i0+1;H=cnt.index.get_level_values(1).max()-j0+1
A=np.zeros((W,H),int)
for (i,j),v in cnt.items(): A[i-i0,j-j0]=v
lab,n=ndimage.label(A>=6,structure=np.ones((3,3)))
sizes=ndimage.sum(np.ones_like(A),lab,range(1,n+1)); k=int(np.argmax(sizes))+1
M=lab==k
# spine: per row j, cell with max count, continuity-constrained
spine=[]; prev=None
for j in range(H):
    ii=np.where(M[:,j])[0]
    if len(ii)==0: continue
    if prev is not None: 
        near=ii[np.abs(ii-prev)<=3]
        if len(near)==0: continue
        ii=near
    best=ii[np.argmax(A[ii,j])]; spine.append((best+i0,j+j0)); prev=best
spine=pd.DataFrame(spine,columns=["i","j"]); spine["n_true"]=[A[i-i0,j-j0] for i,j in zip(spine.i,spine.j)]
x=(spine.i+.5)*50;y=(spine.j+.5)*50; spine["lon"],spine["lat"]=T.transform(x.values,y.values)
print("spine cells",len(spine),"NS km",(spine.j.max()-spine.j.min())*.05)
print(spine.iloc[::20][["lon","lat","n_true"]].round(5).to_string())
# corridor = spine cells +-1 neighbor (tolerate lateral offset)
cor=set()
for i,j in zip(spine.i,spine.j):
    for di in (-1,0,1): cor.add((i+di,j))
pc["key"]=list(zip(pc.i,pc.j)); sc["key"]=list(zip(sc.i,sc.j))
pcc=pc[pc.key.isin(cor)]
# coverage per campaign = fraction of spine rows touched
cov=pcc.groupby("cid").j.nunique()/len(spine)
cov=cov.sort_values(ascending=False)
inv=inv.set_index("campaign_id")
out=pd.DataFrame({"cov":cov,"date":inv.reindex(cov.index).date,"q":inv.reindex(cov.index).campaign_quality_flag})
out.to_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\campaign_coverage.csv")
print(out.round(2).to_string())
for t in [0.25,0.5,0.75]: print("campaigns covering >=",t,(cov>=t).sum(),"dates",out[out["cov"]>=t].date.nunique())
spine.to_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\spine.csv",index=False)
# product
scc=sc[sc.key.isin(cor)]
segs=scc.groupby("seg").agg(rows=("j","nunique"),camps=("cid","nunique")).join(seg.set_index("repeated_segment_id")[["segment_length_m","n_passages","n_campaigns","n_same_direction","n_opposite_direction","reference_track_id"]])
segs=segs[segs.rows>=5].sort_values("rows",ascending=False)
segs.to_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\segments_on_corridor.csv")
print("segments overlapping corridor (>=5 rows=250m):",len(segs)); print(segs.drop(columns="reference_track_id").head(40).to_string())
print("n_passages distribution",segs.n_passages.value_counts().sort_index().to_dict())
print("sum length",segs.segment_length_m.sum(),"spine length m",len(spine)*50)
u=scc[scc.seg.isin(segs.index)].cid.unique(); print("union campaigns in product on corridor",len(u))
print("true campaigns (any touch >=10% rows)",(cov>=0.10).sum())
# per spine row: true count vs product max passages and union
ps=[]
for i,j in zip(spine.i,spine.j):
    kk=[(i+d,j) for d in (-1,0,1)]
    t=pc[pc.key.isin(kk)].cid.nunique()
    s=scc[scc.key.isin(kk)]
    mx=s.groupby("seg").cid.nunique().max() if len(s) else 0
    ps.append((i,j,t,mx,s.cid.nunique(),s.seg.nunique()))
ps=pd.DataFrame(ps,columns=["i","j","true_campaigns","product_max_passages_one_segment","product_union_campaigns","n_segments_stacked"])
ps.to_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\spine_profile.csv",index=False)
print(ps.describe().round(1).to_string())
