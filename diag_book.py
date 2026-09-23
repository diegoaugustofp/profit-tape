import pyarrow.dataset as ds
p = r"D:\backup_raw\data\raw\book_offer\dt=2026-09-17"
d = ds.dataset(p, format="parquet", partitioning="hive")
print("colunas:", d.schema.names)
t = d.to_table(filter=ds.field("sym") == "WINFUT").to_pandas()
print("linhas:", len(t))
print("por action:", t["action"].value_counts().to_dict())
for a, g in t.groupby("action"):
    print(f"action={a}  offer_id==0: {(g.offer_id == 0).mean():.3f}  "
          f"price==0: {(g.price == 0).mean():.3f}  quantidade==0: {(g.quantidade == 0).mean():.3f}")
ids_add = set(t.loc[t.action == 0, "offer_id"].unique())
dels = t[t.action.isin([2, 3])]
print("DELETE com offer_id que apareceu em ADD:", round(dels.offer_id.isin(ids_add).mean(), 3))
print(t.head(15).to_string())
