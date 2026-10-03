# bench_leitura.py  --  python bench_leitura.py caminho\part-0003.parquet
import sys, time
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq, pyarrow.dataset as ds

arq = Path(sys.argv[1])
t0 = time.perf_counter(); meta = pq.read_metadata(arq); dt_footer = time.perf_counter() - t0
n = meta.num_row_groups
print(f"{arq.name}: {n} row groups, {meta.num_rows} linhas, {meta.num_columns} colunas, "
      f"footer parseado em {dt_footer:.1f}s")
pf = pq.ParquetFile(arq)

def t(nome, fn, rgs):
    t0 = time.perf_counter(); r = fn(); dt = time.perf_counter() - t0
    print(f"{nome:48s} {dt:8.1f}s  {dt/rgs*1000:7.2f} ms/rg  linhas={r.num_rows}", flush=True)

# 1. escala DENTRO do arquivo: se ms/rg subir com k, o superlinear esta' no reader
for k in (2_500, 5_000, 10_000, 20_000):
    if k > n: break
    t(f"read_row_groups(0..{k}) 1 thread", lambda k=k: pf.read_row_groups(list(range(k)), use_threads=False), k)

# 2. candidato a streaming: blocos fixos de 2000, footer parseado uma vez
def blocos():
    return pa.concat_tables([pf.read_row_groups(list(range(i, min(i + 2000, n))), use_threads=False)
                             for i in range(0, n, 2000)])
t("read_row_groups em blocos de 2000 (arquivo todo)", blocos, n)

# 3. caminhos inteiros
t("ParquetFile.read(use_threads=False)", lambda: pf.read(use_threads=False), n)
t("ParquetFile.read(use_threads=True)", lambda: pf.read(use_threads=True), n)
t("dataset.to_table(use_threads=False)", lambda: ds.dataset([str(arq)], format="parquet").to_table(use_threads=False), n)
t("dataset.to_table(use_threads=True)   [= compact hoje]", lambda: ds.dataset([str(arq)], format="parquet").to_table(use_threads=True), n)