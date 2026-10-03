# diag_pool.py -- python diag_pool.py D:\backup_raw\data\raw 2026-08-26 WINFUT
import os, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pyarrow as pa, pyarrow.parquet as pq

raiz, dia, sym = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
print(f"pa.cpu_count={pa.cpu_count()} io_threads={pa.io_thread_count()} os.cpu_count={os.cpu_count()} "
      f"OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}", flush=True)
arqs = {s: sorted((raiz / s / f"dt={dia}" / f"sym={sym}").glob("part-*.parquet"))[3]
        for s in ("book_offer", "book_price", "tiny_book", "trade")}
for s, a in arqs.items():
    m = pq.read_metadata(a)
    print(f"  {s:11s} {a.name} rg={m.num_row_groups} linhas={m.num_rows} cols={m.num_columns}", flush=True)

def ler(a, threads):
    t0 = time.perf_counter(); t = pq.ParquetFile(a).read(use_threads=threads)
    return a.parent.parent.parent.name, pq.read_metadata(a).num_row_groups, time.perf_counter() - t0

for threads in (True, False):
    print(f"\n--- use_threads={threads}: 1 arquivo por vez", flush=True)
    for a in arqs.values():
        s, rg, dt = ler(a, threads); print(f"  {s:11s} {dt:6.1f}s {dt/rg*1000:6.2f} ms/rg", flush=True)
    print(f"--- use_threads={threads}: os 4 ao mesmo tempo (= compact --workers 4)", flush=True)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(4) as ex:
        for s, rg, dt in ex.map(lambda a: ler(a, threads), arqs.values()):
            print(f"  {s:11s} {dt:6.1f}s {dt/rg*1000:6.2f} ms/rg", flush=True)
    print(f"  parede: {time.perf_counter()-t0:.1f}s", flush=True)