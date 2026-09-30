"""
PERFIL DE VOLUME POR PRECO (Volume Profile) + DELTA POR NIVEL -- F1 do
EA `vwap_vp` (docs/eas/vwap_vp.md, 2026-09-29).

NAO confundir com `ea/perfil_volume.py`, que e' o perfil POR HORARIO
(mediana de vol_total por hhmm, gate de volume da ficha 12). Aqui o eixo
e' o PRECO: em que niveis o volume se acumulou.

O que sai daqui
---------------
- histograma preco -> contratos, em bins de `bin_pts` (D4: 25 pts = 5
  ticks no WIN; a 5 pts o WIN da' 300-500 bins e todo bin vira LVN);
- POC = bin de maior volume (empate: o mais proximo do centro do range,
  regra classica de Market Profile);
- area de valor (VAL, VAH) = menor faixa contigua em torno do POC com
  >= `pct` do volume, expandindo sempre para o lado do bin vizinho
  maior (VAH/VAL sao as BORDAS EXTERNAS dos bins de ponta);
- HVN/LVN parametrizados: LVN = bin com volume < `lvn_frac` x media dos
  `vizinhos` bins de cada lado; HVN = maximo local com volume >=
  `hvn_frac` x volume do POC. Os numeros sao chute declarado (ficha D4)
  ate' serem olhados ao lado do perfil do Profit -- por isso sao
  parametros, nao constantes;
- DELTA POR NIVEL: por bin, agressao de compra e de venda (tipos 2/3),
  RLP (13) e leilao (4) separados, para gravar "com/sem RLP" de graca.

Quais negocios entram no TOTAL e' de quem chama (`incluir_tipos`); o
default e' todos (D3: bate com o que o Profit plota). A agressao por
lado SEMPRE conta so' tipos 2/3, independente do filtro do total.

Construtor do dia anterior: le o curated e guarda em cache JSON pela
mesma assinatura (arquivos, linhas) do `cache_barras` -- se o dia for
recurado, refaz.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import structlog

from ..domain.enums import TradeType
from .cache_barras import assinatura

log = structlog.get_logger(__name__)

_VERSAO_CACHE = 1
AGRESSAO = (int(TradeType.AGGRESSOR_BUYER), int(TradeType.AGGRESSOR_SELLER))


class PerfilDePreco:
    __slots__ = ("_agr_c", "_agr_v", "_leilao", "_rlp", "_total", "bin_pts",
                 "incluir_tipos", "n")

    def __init__(self, bin_pts: float = 25.0,
                 incluir_tipos: Iterable[int] | None = None) -> None:
        if bin_pts <= 0:
            raise ValueError("bin_pts deve ser > 0")
        self.bin_pts = float(bin_pts)
        self.incluir_tipos: frozenset[int] | None = (
            None if incluir_tipos is None else frozenset(int(t) for t in incluir_tipos))
        self._total: dict[float, float] = {}     # bin -> contratos (filtro incluir_tipos)
        self._agr_c: dict[float, float] = {}     # bin -> agressao compra (tipo 2)
        self._agr_v: dict[float, float] = {}     # bin -> agressao venda (tipo 3)
        self._rlp: dict[float, float] = {}       # bin -> RLP (tipo 13)
        self._leilao: dict[float, float] = {}    # bin -> leilao (tipo 4)
        self.n = 0

    # ------------------------------------------------------------ entrada
    def bin_de(self, price: float) -> float:
        """Borda INFERIOR do bin que contem `price` (floor)."""
        return math.floor(price / self.bin_pts) * self.bin_pts

    def registrar(self, price: float, quantidade: int | float, trade_type: int) -> None:
        if quantidade <= 0:
            return
        b = self.bin_de(float(price))
        v = float(quantidade)
        t = int(trade_type)
        if self.incluir_tipos is None or t in self.incluir_tipos:
            self._total[b] = self._total.get(b, 0.0) + v
        if t == AGRESSAO[0]:
            self._agr_c[b] = self._agr_c.get(b, 0.0) + v
        elif t == AGRESSAO[1]:
            self._agr_v[b] = self._agr_v.get(b, 0.0) + v
        elif t == int(TradeType.RLP):
            self._rlp[b] = self._rlp.get(b, 0.0) + v
        elif t == int(TradeType.AUCTION):
            self._leilao[b] = self._leilao.get(b, 0.0) + v
        self.n += 1

    # ---------------------------------------------------------- consultas
    @property
    def vazio(self) -> bool:
        return not self._total

    @property
    def volume(self) -> float:
        return sum(self._total.values())

    def bins(self) -> list[float]:
        return sorted(self._total)

    def volume_no_bin(self, b: float) -> float:
        return self._total.get(b, 0.0)

    def delta_no_bin(self, b: float) -> float:
        """agressao compra - agressao venda no bin (so' tipos 2/3)."""
        return self._agr_c.get(b, 0.0) - self._agr_v.get(b, 0.0)

    def delta_na_faixa(self, inferior: float, superior: float) -> float:
        """Delta somado nos bins cuja borda inferior cai em [inferior, superior]."""
        return sum(self.delta_no_bin(b) for b in self._total if inferior <= b <= superior)

    def poc(self) -> float | None:
        """Bin de maior volume. Empate: o mais proximo do centro do range."""
        if not self._total:
            return None
        bs = self.bins()
        centro = (bs[0] + bs[-1]) / 2.0
        maior = max(self._total.values())
        cands = [b for b in bs if self._total[b] == maior]
        return min(cands, key=lambda b: (abs(b - centro), b))

    def poc_faixa(self, frac: float = 0.90) -> tuple[float, float] | None:
        """(inferior, superior) dos bins com volume >= frac x maximo -- o
        PLATO do POC. Medido em 25/09 e 28/09 (F1): os 8 maiores bins
        ficam a 3% um do outro numa faixa de ~150 pts; o POC "vence" por
        pouco e um alvo ancorado nele tem +-100 pts de indeterminacao por
        construcao. Bordas externas, como VAL/VAH."""
        if not self._total:
            return None
        maior = max(self._total.values())
        bs = [b for b in self.bins() if self._total[b] >= frac * maior]
        return (bs[0], bs[-1] + self.bin_pts)

    def area_de_valor(self, pct: float = 0.70, modo: str = "bin") -> tuple[float, float] | None:
        """(VAL, VAH): bordas externas da menor faixa contigua em torno do
        POC com >= pct do volume.

        modo="bin"   expande UM bin por vez para o vizinho maior; empate
                     expande para cima (declarado na ficha, D4).
        modo="pares" expande DOIS bins por vez, comparando a soma dos dois
                     acima com a dos dois abaixo (TPO classico / Sierra).
        O Profit nao marca VAL/VAH (F1, 29/09), entao a escolha nao e'
        conferivel na tela: o replay calcula os dois e mede a diferenca."""
        if modo not in ("bin", "pares"):
            raise ValueError(f"modo={modo!r}: use 'bin' ou 'pares'")
        p = self.poc()
        if p is None:
            return None
        bs = self.bins()
        i_lo = i_hi = bs.index(p)
        alvo = pct * self.volume
        acum = self._total[p]
        passo = 1 if modo == "bin" else 2
        while acum < alvo and (i_lo > 0 or i_hi < len(bs) - 1):
            abaixo = sum(self._total[bs[i]] for i in range(max(0, i_lo - passo), i_lo))
            acima = sum(self._total[bs[i]]
                        for i in range(i_hi + 1, min(len(bs), i_hi + 1 + passo)))
            if i_hi >= len(bs) - 1:
                acima = -1.0
            if i_lo <= 0:
                abaixo = -1.0
            if acima >= abaixo:
                n = min(passo, len(bs) - 1 - i_hi)
                i_hi += n
                acum += acima
            else:
                n = min(passo, i_lo)
                i_lo -= n
                acum += abaixo
        return (bs[i_lo], bs[i_hi] + self.bin_pts)

    def nos(self, lvn_frac: float = 0.30, hvn_frac: float = 0.50,
            vizinhos: int = 2) -> dict[str, list[float]]:
        """{'lvn': [...], 'hvn': [...]} -- bordas inferiores dos bins.
        LVN: volume < lvn_frac x media dos ate' `vizinhos` bins de cada
        lado (bins ausentes no meio do range contam como zero, sao LVN por
        definicao). HVN: maximo local (>= vizinhos imediatos) com volume
        >= hvn_frac x POC. Range com < 3 bins nao tem no'."""
        bs = self.bins()
        if len(bs) < 3:
            return {"lvn": [], "hvn": []}
        lo, hi = bs[0], bs[-1]
        grade = [lo + k * self.bin_pts for k in range(round((hi - lo) / self.bin_pts) + 1)]
        vol = [self._total.get(b, 0.0) for b in grade]
        vpoc = max(vol)
        lvn: list[float] = []
        hvn: list[float] = []
        for i, b in enumerate(grade):
            viz = vol[max(0, i - vizinhos):i] + vol[i + 1:i + 1 + vizinhos]
            if not viz:
                continue
            media = sum(viz) / len(viz)
            if media > 0 and vol[i] < lvn_frac * media:
                lvn.append(b)
            e = vol[i - 1] if i > 0 else -1.0
            d = vol[i + 1] if i < len(grade) - 1 else -1.0
            if vol[i] >= hvn_frac * vpoc and vol[i] >= e and vol[i] >= d and vol[i] > 0:
                hvn.append(b)
        return {"lvn": lvn, "hvn": hvn}

    def resumo(self, pct: float = 0.70) -> dict[str, Any]:
        va = self.area_de_valor(pct)
        bs = self.bins()
        return {"n": self.n, "bins": len(bs), "bin_pts": self.bin_pts,
                "volume": self.volume,
                "volume_rlp": sum(self._rlp.values()),
                "volume_leilao": sum(self._leilao.values()),
                "agr_compra": sum(self._agr_c.values()),
                "agr_venda": sum(self._agr_v.values()),
                "min": bs[0] if bs else None,
                "max": (bs[-1] + self.bin_pts) if bs else None,
                "poc": self.poc(),
                "poc_faixa": self.poc_faixa(),
                "val": None if va is None else va[0],
                "vah": None if va is None else va[1],
                "va_pares": self.area_de_valor(pct, "pares")}

    # ------------------------------------------------------------- cache
    def _para_json(self) -> dict[str, Any]:
        return {"bin_pts": self.bin_pts, "n": self.n,
                "incluir_tipos": None if self.incluir_tipos is None
                else sorted(self.incluir_tipos),
                "total": self._total, "agr_c": self._agr_c, "agr_v": self._agr_v,
                "rlp": self._rlp, "leilao": self._leilao}

    @classmethod
    def _de_json(cls, d: dict[str, Any]) -> PerfilDePreco:
        p = cls(float(d["bin_pts"]), d.get("incluir_tipos"))
        p.n = int(d["n"])
        for nome in ("total", "agr_c", "agr_v", "rlp", "leilao"):
            setattr(p, f"_{nome}", {float(k): float(v) for k, v in d[nome].items()})
        return p


# --------------------------------------------------------------- do curated
def construir_do_dia(curated: Path, symbol: str, dia: dt.date, bin_pts: float = 25.0,
                     incluir_tipos: Iterable[int] | None = None) -> PerfilDePreco:
    """O caminho caro: le o dia do curated negocio a negocio."""
    from ..features.pipeline import _carregar_dia

    p = PerfilDePreco(bin_pts, incluir_tipos)
    pasta = curated / "trade" / f"dt={dia.isoformat()}"
    if not (pasta / f"sym={symbol}").exists():
        return p
    t = _carregar_dia(pasta, symbol)
    if t.empty:
        return p
    for price, qtd, tipo in t[["price", "quantidade", "trade_type"]].itertuples(index=False):
        p.registrar(float(price), int(qtd), int(tipo))
    return p


def perfil_do_dia(curated: Path, symbol: str, dia: dt.date, bin_pts: float = 25.0,
                  incluir_tipos: Iterable[int] | None = None,
                  cache_dir: Path | None = None) -> PerfilDePreco:
    """Perfil do dia, do cache quando a assinatura do curated bate; senao
    constroi e guarda. Dia sem tape devolve perfil vazio (nao cacheado)."""
    ass = assinatura(curated, symbol, dia)
    if ass is None:
        return PerfilDePreco(bin_pts, incluir_tipos)
    tipos = "todos" if incluir_tipos is None else "-".join(str(t) for t in sorted(incluir_tipos))
    destino = cache_dir or (curated.parent / "cache" / "perfil_preco")
    arq = destino / f"{symbol}_{dia.isoformat()}_{bin_pts:g}_{tipos}.json"
    if arq.exists():
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
            if tuple(d["assinatura"]) == ass and d.get("versao") == _VERSAO_CACHE:
                return PerfilDePreco._de_json(d["perfil"])
            log.info("ea.perfil_preco.invalidado", dia=dia.isoformat(), symbol=symbol,
                     assinatura_no_cache=d.get("assinatura"), assinatura_agora=list(ass),
                     nota="o dia mudou no curated (recura/backfill): refazendo")
        except Exception:
            pass
    p = construir_do_dia(curated, symbol, dia, bin_pts, incluir_tipos)
    if p.vazio:
        return p
    try:
        destino.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps({"versao": _VERSAO_CACHE, "assinatura": list(ass),
                                   "perfil": p._para_json()}), encoding="utf-8")
    except OSError as e:               # cache e' otimizacao: falhar nao quebra o EA
        log.warning("ea.perfil_preco.nao_gravou", erro=str(e), arquivo=str(arq))
    return p


# ------------------------------------------------------------ dias do curated
def dias_disponiveis(curated: Path, symbol: str) -> list[dt.date]:
    """Dias com pasta `trade/dt=.../sym=<symbol>` no curated, em ordem."""
    base = curated / "trade"
    if not base.exists():
        return []
    out: list[dt.date] = []
    for pasta in base.iterdir():
        if not pasta.name.startswith("dt=") or not (pasta / f"sym={symbol}").exists():
            continue
        try:
            out.append(dt.date.fromisoformat(pasta.name[3:]))
        except ValueError:
            continue
    return sorted(out)


def dia_de_referencia(curated: Path, symbol: str, dia: dt.date) -> dt.date | None:
    """O ultimo dia com tape ANTES de `dia` (D2: perfil de referencia = dia
    util anterior, fixo). None se nao ha' dia anterior no curated."""
    ant = [d for d in dias_disponiveis(curated, symbol) if d < dia]
    return ant[-1] if ant else None

