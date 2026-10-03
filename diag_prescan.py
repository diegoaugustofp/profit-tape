# diag_prescan.py -- python diag_prescan.py D:\backup_raw\data\raw tiny_book\dt=2026-08-28\sym=WINFUT   (dia AINDA nao compactado)
import sys, time
from pathlib import Path
import pyarrow.parquet as pq
from profittape.storage.validacao import relatorio
raiz, part = Path(sys.argv[1]), Path(sys.argv[1]) / sys.argv[2]
arqs = sorted(part.glob("part-*.parquet")); rg = sum(pq.read_metadata(a).num_row_groups for a in arqs)
def leitura(rotulo):
    t0 = time.perf_counter(); [pq.ParquetFile(a).read(use_threads=False) for a in arqs]
    dt = time.perf_counter() - t0; print(f"  leitura {rotulo:22s} {dt:7.1f}s {dt/rg*1000:6.2f} ms/rg", flush=True)
leitura("ANTES da varredura")
t0 = time.perf_counter()
for s in ("book_offer", "book_price", "tiny_book", "trade"):
    relatorio(raiz / s)                       # exatamente o que compactar_raw faz no arranque
print(f"  varredura: {time.perf_counter()-t0:.0f}s", flush=True)
leitura("DEPOIS da varredura")