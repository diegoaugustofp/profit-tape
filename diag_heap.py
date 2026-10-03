# diag_heap.py -- python diag_heap.py D:\backup_raw\data\raw\tiny_book\dt=2026-08-27\sym=WINFUT
# (use um dia AINDA NAO compactado; tiny_book e' o mais barato: ~2 min se plano, ~18 se degradar)
import sys, time
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq
print("pool:", pa.default_memory_pool().backend_name, "| disponiveis:", pa.supported_memory_backends(), flush=True)
arqs = sorted(Path(sys.argv[1]).glob("part-*.parquet"))
for modo in ("descartando", "guardando"):
    print(f"\n--- {modo}", flush=True)
    guardadas = []; t_ini = time.perf_counter()
    for i, a in enumerate(arqs):
        rg = pq.read_metadata(a).num_row_groups
        t0 = time.perf_counter(); t = pq.ParquetFile(a).read(use_threads=False); dt = time.perf_counter() - t0
        if modo == "guardando": guardadas.append(t)
        if i % 6 == 0 or i == len(arqs) - 1:
            print(f"  arq {i:2d} {dt/rg*1000:6.2f} ms/rg  bytes_vivos={pa.total_allocated_bytes()/1e9:5.2f} GB", flush=True)
    print(f"  total {time.perf_counter()-t_ini:.0f}s", flush=True)
    del guardadas