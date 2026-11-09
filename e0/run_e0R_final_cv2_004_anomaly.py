import pandas as pd, glob, numpy as np, json, sys
from pathlib import Path
"""cv2_004 thermal anomaly per campaign (route mean T - campaign mean T), v0.2 recommended standardized + split. Read-only."""
root=Path("outputs/e0R_qc_split_20261109T1240"); sa=pd.read_parquet(root/"split_assignments_E0R.parquet",columns=["canonical_campaign_id","source_row","route"])
rows=[]
for cid,g in sa.groupby("canonical_campaign_id"):
    if not (g.route.astype(str)=="cv2_004").any(): continue
    s=pd.read_parquet(next((root/"recommended"/"campaigns"/cid).glob("*_standardized.parquet")),columns=["source_row","Temp[°C]","Alt[m]","qc_sensor_stabilization","keep_recommended"])
    m=s.merge(g,on="source_row"); on=m.route.astype(str)=="cv2_004"
    rows.append(dict(campaign=cid,n_cv2_004=int(on.sum()),dT_route_minus_campaign=float(m.loc[on,"Temp[°C]"].mean()-m["Temp[°C]"].mean()),
                     dAlt=float(m.loc[on,"Alt[m]"].mean()-m["Alt[m]"].mean()),share_stab=float(m.loc[on,"qc_sensor_stabilization"].mean()),share_keep_rec=float(m.loc[on,"keep_recommended"].mean())))
d=pd.DataFrame(rows).sort_values("dT_route_minus_campaign"); out=Path(sys.argv[1]); d.to_csv(out/"cv2_004_thermal_anomaly_by_campaign.csv",index=False)
print(d.round(2).to_string()); print("median dT others:", d[~d.campaign.str.contains("13_08_42")].dT_route_minus_campaign.median())
