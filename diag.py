import pandas as pd, glob
from profittape.ea.barra_tempo import ConstrutorDeBarraDeTempo
f = glob.glob("data/curated/trade/dt=2026-09-16/sym=WINFUT/*.parquet")[0]
df = pd.read_parquet(f, columns=["ts_ns","price","quantidade","trade_type"])
c = ConstrutorDeBarraDeTempo(900)
n = 0
for r in df.itertuples(index=False):
    if c.processar_trade(int(r.ts_ns), float(r.price), int(r.quantidade), int(r.trade_type)):
        n += 1
print("barras fechadas SO pelo fluxo de trades:", n)
