# diag_pipeline.py -- python diag_pipeline.py D:\backup_raw\data\raw\tiny_book\dt=2026-08-27\sym=WINFUT
import sys, time, tempfile, math
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq
from profittape.tools.compact import _gravar_arquivo   # o mesmo codigo da v3.85

RG, MAXF = 1_048_576, 5_000_000
arqs = sorted(Path(sys.argv[1]).glob("part-*.parquet"))
def fase(nome, fn):
    t0 = time.perf_counter(); r = fn(); print(f"  {nome:42s} {time.perf_counter()-t0:8.1f}s", flush=True); return r

partes = fase("leitura 37 arquivos (guardando)", lambda: [pq.ParquetFile(a).read(use_threads=False) for a in arqs])
tab = fase("concat_tables permissive", lambda: pa.concat_tables(partes, promote_options="permissive"))
print(f"  linhas={tab.num_rows} chunks/col={tab.column(0).num_chunks}", flush=True)
del partes
fatias = fase("Table.slice por max_rows_per_file", lambda: [tab.slice(i, MAXF) for i in range(0, tab.num_rows, MAXF)])
fase("slice+combine_chunks de 1 row group (so' 1)", lambda: tab.slice(0, RG).combine_chunks())
out = Path(tempfile.mkdtemp())
for k, f in enumerate(fatias):
    fase(f"_gravar_arquivo fatia {k} ({f.num_rows} linhas)", lambda f=f, k=k: _gravar_arquivo(f, out / f"p{k}.parquet", RG))
fase("verificacao (ParquetFile.metadata dos novos)", lambda: [pq.ParquetFile(p).metadata.num_row_groups for p in out.glob("*.parquet")])
print("saida em", out)