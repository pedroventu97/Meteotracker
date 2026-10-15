import pandas as pd, numpy as np
from scipy import ndimage
from pyproj import Transformer
T=Transformer.from_crs(32632,4326,always_xy=True)
pc=pd.read_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_parts.parquet")
pc=pc[~pc.cid.str.contains("mtdicambo_UNKNOWN_Bologna-Bentivoglio")|True]
cnt=pc.groupby(["i","j"]).cid.nunique()
print(cnt.describe()); print(cnt.value_counts().sort_index(ascending=False).head(15))
i0,j0=cnt.index.get_level_values(0).min(),cnt.index.get_level_values(1).min()
W=cnt.index.get_level_values(0).max()-i0+1;H=cnt.index.get_level_values(1).max()-j0+1
A=np.zeros((W,H),int)
for (i,j),v in cnt.items(): A[i-i0,j-j0]=v
for th in [4,5,6,8,10]:
    lab,n=ndimage.label(A>=th,structure=np.ones((3,3)))
    best=[]
    for k in range(1,n+1):
        ii,jj=np.where(lab==k)
        best.append(((jj.max()-jj.min())*50,(ii.max()-ii.min())*50,len(ii),k))
    best.sort(reverse=True)
    print("th",th,"top comps (NS ext m, EW ext m, ncells):",best[:4])
    for b in best[:2]:
        ii,jj=np.where(lab==b[3]); x=(ii+i0+.5)*50; y=(jj+j0+.5)*50
        lo,la=T.transform([x.mean(),x[jj.argmin()],x[jj.argmax()]],[y.mean(),y.min(),y.max()]); print("  center/S/N lonlat",np.round(lo,5),np.round(la,5))
