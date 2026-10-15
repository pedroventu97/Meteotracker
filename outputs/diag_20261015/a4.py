import pandas as pd, numpy as np, geopandas as gpd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
pc=pd.read_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_parts.parquet"); sc=pd.read_parquet(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\cells_pas.parquet")
seg=pd.read_csv(r"D:\projects\Meteotracker\outputs\repeated_routes_20261015T0835\repeated_segments.csv")
# global merge: segments clustered if cell-overlap >= f of smaller footprint
cs=sc.groupby("seg").apply(lambda g:set(zip(g.i,g.j))).to_dict()
camps=sc.groupby("seg").cid.apply(set).to_dict()
ids=list(cs); idx={s:k for k,s in enumerate(ids)}
from collections import defaultdict
inv=defaultdict(set)
for s,c in cs.items():
    for x in c: inv[x].add(s)
def run(f):
    par=list(range(len(ids)))
    def fd(a):
        while par[a]!=a: par[a]=par[par[a]]; a=par[a]
        return a
    for s in ids:
        nb=defaultdict(int)
        for x in cs[s]:
            for t in inv[x]: nb[t]+=1
        for t,n in nb.items():
            if t!=s and n>=f*min(len(cs[s]),len(cs[t])): par[fd(idx[s])]=fd(idx[t])
    cl=defaultdict(set)
    for s in ids: cl[fd(idx[s])].add(s)
    nc=[len(set().union(*(camps[s] for s in g))) for g in cl.values()]
    return cl,np.array(nc)
for f in [0.8,0.5,0.3]:
    cl,nc=run(f); print(f"merge f={f}: clusters={len(cl)} campaigns/cluster: median={np.median(nc)} p90={np.percentile(nc,90)} max={nc.max()} share==2: {(nc==2).mean():.2f} >=4: {(nc>=4).sum()}")
# per-cell many-to-many count from product evidence (union campaigns in cell) vs true
true=pc.groupby(["i","j"]).cid.nunique(); prod=sc.groupby(["i","j"]).cid.nunique()
mx=sc.groupby(["i","j","seg"]).cid.nunique().groupby(level=[0,1]).max()
df=pd.DataFrame({"true":true,"union":prod,"maxseg":mx}).fillna(0)
sp=pd.read_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\spine.csv"); prof=pd.read_csv(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\spine_profile.csv")
f,ax=plt.subplots(1,3,figsize=(18,8),gridspec_kw={"width_ratios":[1,1,0.8]})
I=df.index.get_level_values(0)*50; J=df.index.get_level_values(1)*50
ext=[(sp.i.min()-40)*50,(sp.i.max()+40)*50,(sp.j.min()-10)*50,(sp.j.max()+10)*50]
for a,col,t in [(ax[0],"true","Campagne distinte reali per cella 50 m"),(ax[1],"maxseg","Prodotto: max passaggi in un singolo segmento")]:
    s=a.scatter(I,J,c=df[col],s=4,marker="s",cmap="turbo",vmin=0,vmax=12); plt.colorbar(s,ax=a,shrink=.6)
    a.plot(sp.i*50+25,sp.j*50+25,color="k",lw=0,marker=".",ms=2,alpha=.5,label="asse N-S (spine)")
    a.set_xlim(ext[0],ext[1]); a.set_ylim(ext[2],ext[3]); a.set_aspect("equal"); a.set_title(t); a.legend(loc="lower right")
y=prof.j*50/1000; y=y-y.min()
ax[2].plot(prof.true_campaigns,y,label="campagne reali",lw=2)
ax[2].plot(prof.product_union_campaigns,y,label="unione campagne nei segmenti",ls="--")
ax[2].plot(prof.product_max_passages_one_segment,y,label="max passaggi in 1 segmento",lw=2,color="r")
ax[2].plot(prof.n_segments_stacked/5,y,label="n segmenti sovrapposti /5",color="gray",alpha=.6)
ax[2].set_xlabel("conteggio"); ax[2].set_ylabel("km da sud (Sabbiuno -> Bologna)"); ax[2].legend(fontsize=8); ax[2].set_title("Profilo lungo l'asse")
f.suptitle("Asse N-S Bologna (Viali/Pepoli - Via dei Colli - Via di Sabbiuno -> Sasso Marconi): passaggi reali vs prodotto repeated_routes_20261015T0835"); f.tight_layout()
f.savefig(r"C:\Users\MARCO~1.VEN\AppData\Local\Temp\mt_diag\diag_ns_axis.png",dpi=130)
