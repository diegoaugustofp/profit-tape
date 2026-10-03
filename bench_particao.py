# bench_particao.py -- python bench_particao.py D:\backup_raw\data\raw\book_offer\dt=2026-08-27\sym=WDOFUT
import sys, time
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq, pyarrow.dataset as ds
arqs = sorted(Path(sys.argv[1]).glob("part-*.parquet"))
for n in (4, 8, 16, len(arqs)):
    sub = arqs[:n]; rg = sum(pq.read_metadata(a).num_row_groups for a in sub)
    t0 = time.perf_counter(); pa.concat_tables([pq.ParquetFile(a).read(use_threads=True) for a in sub]); d1 = time.perf_counter() - t0
    print(f"{n:3d} arquivos {rg:8d} rg  ParquetFile.read/arquivo: {d1:7.1f}s {d1/rg*1000:6.2f} ms/rg", flush=True)
    if n <= 16:   # o caminho atual so' ate 16 arquivos: se for superlinear, o total levaria horas
        t0 = time.perf_counter(); ds.dataset([str(a) for a in sub], format="parquet").to_table(); d2 = time.perf_counter() - t0
        print(f"{'':27s} dataset.to_table:         {d2:7.1f}s {d2/rg*1000:6.2f} ms/rg", flush=True)