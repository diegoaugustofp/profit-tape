"""
CACHE das barras derivadas do TAPE (2026-09-28).

Semente e perfil precisam das barras de 15 min dos pregoes que vieram
DEPOIS do fim do parquet do grafico. Elas eram reconstruidas negocio a
negocio, em Python, A CADA ARRANQUE DE EA. Em 28/09 isso custou:

- parquet parado em 11/09 -> 10 pregoes de ponte, e cresce 1 por dia;
- o perfil lia cada dia DUAS vezes (uma para registrar, outra so' para
  saber se veio algo);
- cada EA refazia tudo sozinho -- eram TRES no ar;
- durante o pregao o disco disputa com o record.

Resultado: o EA real subiu 09:21, com o mercado aberto desde 09:00, e
armou o primeiro sinal 10 min atrasado -- a ordem stop saiu com o
mercado 455 pts ALEM do gatilho e virou ordem a mercado. Custou 455 pts
numa operacao que deu certo.

Aqui o dia e' reconstruido UMA vez e guardado. A conta e' identica: o
cache guarda exatamente o que a funcao devolveria.

INVALIDACAO: a assinatura e' (arquivos, linhas) do dia no curated, lida
dos METADADOS do parquet (sem carregar dado). Se o dia for recurado ou
receber backfill, a assinatura muda e o cache e' refeito -- e' o caso
real de 18/09, que ganhou 212 mil negocios depois.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pyarrow.parquet as pq
import structlog

from ..features.pipeline import _carregar_dia
from .barra_tempo import ConstrutorDeBarraDeTempo

log = structlog.get_logger(__name__)
_NS = 1_000_000_000

# (ts_open_ns, close, vol_total, volume_confiavel) -- UM payload que serve
# aos dois usos: a semente quer `close`, o perfil quer `vol_total`. Antes
# cada um reconstruia o dia por conta propria.
Barra = tuple[int, float, float, bool]
_MEMORIA: dict[tuple[str, str, str, int], list[Barra]] = {}


def assinatura(curated: Path, symbol: str, dia: dt.date) -> tuple[int, int] | None:
    """(arquivos, linhas) do dia, pelos METADADOS -- nao carrega dado."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}" / f"sym={symbol}"
    if not pasta.exists():
        return None
    arqs = sorted(pasta.glob("*.parquet"))
    if not arqs:
        return None
    try:
        linhas = sum(pq.ParquetFile(a).metadata.num_rows for a in arqs)
    except Exception:              # arquivo em escrita, corrompido: sem cache
        return None
    return (len(arqs), int(linhas))


def _construir(curated: Path, symbol: str, dia: dt.date, periodo_s: int) -> list[Barra]:
    """O caminho caro: reconstroi as barras do dia negocio a negocio."""
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return []
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return []
    c = ConstrutorDeBarraDeTempo(periodo_s)
    out: list[Barra] = []
    for ts_ns, price, qtd, tipo in t[["ts_ns", "price", "quantidade",
                                      "trade_type"]].itertuples(index=False):
        b = c.processar_trade(int(ts_ns), float(price), int(qtd), int(tipo))
        if b is not None:
            out.append((b.ts_open_ns, float(b.close), float(b.vol_total),
                        bool(b.volume_confiavel)))
    fim = c.avancar_relogio(int(t["ts_ns"].to_numpy()[-1]) + periodo_s * _NS)
    if fim is not None:
        out.append((fim.ts_open_ns, float(fim.close), float(fim.vol_total),
                    bool(fim.volume_confiavel)))
    return out


def barras_do_dia(curated: Path, symbol: str, dia: dt.date, periodo_s: int,
                  cache_dir: Path | None = None) -> list[Barra]:
    """As barras do dia, do cache quando a assinatura bate; senao constroi
    e guarda."""
    ass = assinatura(curated, symbol, dia)
    if ass is None:
        return []
    chave = (str(curated), symbol, dia.isoformat(), periodo_s)
    em_memoria = _MEMORIA.get(chave)
    if em_memoria is not None:
        return em_memoria
    destino = (cache_dir or (curated.parent / "cache" / "barras_tape"))
    arq = destino / f"{symbol}_{dia.isoformat()}_{periodo_s}.json"
    if arq.exists():
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
            if tuple(d["assinatura"]) == ass and d.get("versao") == 2:
                barras = [(int(a), float(b), float(c), bool(e)) for a, b, c, e in d["barras"]]
                _MEMORIA[chave] = barras
                return barras
            log.info("ea.cache_barras.invalidado", dia=dia.isoformat(), symbol=symbol,
                     assinatura_no_cache=d["assinatura"], assinatura_agora=list(ass),
                     nota="o dia mudou no curated (recura/backfill): refazendo")
        except Exception:
            pass
    barras = _construir(curated, symbol, dia, periodo_s)
    _MEMORIA[chave] = barras
    try:
        destino.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps({"versao": 2, "assinatura": list(ass),
                                   "barras": barras}), encoding="utf-8")
    except OSError as e:           # cache e' otimizacao: falhar nao pode quebrar o EA
        log.warning("ea.cache_barras.nao_gravou", erro=str(e), arquivo=str(arq))
    return barras


def limpar_memoria() -> None:
    _MEMORIA.clear()
