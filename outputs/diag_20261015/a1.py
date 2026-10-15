import geopandas as gpd, pandas as pd, numpy as np, json
from scipy import ndimage
G=r"D:\projects\Meteotracker\outputs\repeated_routes_20261015T0835\repeated_routes.gpkg"
C=50.0
def rd(l): return gpd.read_file(G,layer=l,engine="pyogrio").to_crs(32632)
parts=rd("campaign_parts"); seg=rd("repeated_segments"); pas=rd("segment_passages")
print(parts.columns.tolist()); print(len(parts), parts.campaign_id.nunique())
def cells(geom,step=5):
    out=set()
    gs=getattr(geom,'geoms',[geom])
    for g in gs:
        L=g.length
        if L==0: continue
        for s in np.arange(0,L+step,step):
            p=g.interpolate(min(s,L)); out.add((int(p.x//C),int(p.y//C)))
    return out
rows=[]
for _,r in parts.iterrows():
    for c in cells(r.geometry): rows.append((c[0],c[1],r.campaign_id))
pc=pd.DataFrame(rows,columns=["i","j","cid"]).drop_duplicates()
pc.to_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_parts.parquet")
rows=[]
for _,r in pas.iterrows():
    for c in cells(r.geometry): rows.append((c[0],c[1],r.repeated_segment_id,r.campaign_id))
sc=pd.DataFrame(rows,columns=["i","j","seg","cid"]).drop_duplicates()
sc.to_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_pas.parquet")
