import pyarrow.dataset as ds
p = r"D:\backup_raw\data\raw\book_offer\dt=2026-09-17"
t = ds.dataset(p, format="parquet", partitioning="hive").to_table(
    filter=ds.field("sym") == "WINFUT", columns=["action", "position"]).to_pandas()
df = t[t.action == 3]
print("DELETE_FROM total (com o par):", len(df))
print("com position 0 (livro inteiro limpo):", int((df.position == 0).sum()))
print("distribuicao de position:", df.position.value_counts().head(8).to_dict())
