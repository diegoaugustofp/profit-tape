"""
Nucleo PURO do EA de microprice: topo do livro + relogio -> decisao.
Zero I/O, zero DLL, relogio injetado -- o mesmo codigo roda ao vivo
(`service_microprice.tick`) e no replay do tiny_book gravado.

GATILHO
-------
    I = (qtd_bid - qtd_ask) / (qtd_bid + qtd_ask)     (TopoDoLivro.desequilibrio)

I >= +limiar por `persistencia_ms` -> COMPRA (paga o ask).
I <= -limiar por `persistencia_ms` -> VENDE (paga o bid).
Posicionado, zera no PRIMEIRO de: alvo, stop, desbalanco inverteu,
tempo maximo, fim da janela.

MARCACAO HONESTA (taker)
------------------------
Entrada a mercado paga o lado oposto; saida a mercado tambem. Comprado,
a marcacao e' o BID (o que se receberia vendendo agora), nao o mid nem
o ultimo. Por isso a operacao nasce em -1 spread: com spread de 1 tick,
o mid precisa andar 1 tick a favor so' para empatar no bruto, e o
`custo_pontos_estimado` (11 pts) ainda sai depois.

SONDA
-----
Separa "o sinal preve?" de "da' para ganhar pagando spread?". A cada
gatilho (borda de subida da persistencia, posicionado ou nao) guarda o
mid; depois de cada horizonte mede quanto o mid andou A FAVOR, em
pontos. Se a sonda der +2 pts em 5 s e a operacao der -12, o problema e'
custo, nao previsao -- e o caminho seria entrada passiva, nao outro
limiar.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .config_microprice import EAMicropriceConfig
from .decisao import Acao
from .livro_ao_vivo import TopoDoLivro

_NS = 1_000_000_000
_OFFSET_BRT_S = -3 * 3600   # B3 sem horario de verao desde 2019 (runtime usa -3)


def hhmm_brt(ts_ns: int) -> int:
    """Hora local da B3 como HHMM inteiro. Aritmetica pura: roda a cada
    avaliacao, e datetime+ZoneInfo ali seria custo sem ganho."""
    seg_dia = (ts_ns // _NS + _OFFSET_BRT_S) % 86400
    return (seg_dia // 3600) * 100 + (seg_dia % 3600) // 60


def microprice(topo: TopoDoLivro) -> float | None:
    """(Pa*Vb + Pb*Va)/(Vb + Va). None se falta lado/preco ou soma zero."""
    if (topo.preco_bid is None or topo.preco_ask is None
            or topo.qtd_bid is None or topo.qtd_ask is None):
        return None
    soma = topo.qtd_bid + topo.qtd_ask
    if soma <= 0:
        return None
    return (topo.preco_ask * topo.qtd_bid + topo.preco_bid * topo.qtd_ask) / soma


@dataclass(frozen=True)
class Leitura:
    """O topo ja' validado. `motivo` preenchido = inutilizavel para ENTRAR
    (pode ainda servir para SAIR, ver `marcavel`)."""

    motivo: str | None
    marcavel: bool = False
    bid: float = 0.0
    ask: float = 0.0
    imbalance: float = 0.0
    micro: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


def ler_topo(topo: TopoDoLivro | None, cfg: EAMicropriceConfig, agora_ns: int) -> Leitura:
    if topo is None or not topo.completo or topo.preco_bid is None or topo.preco_ask is None:
        return Leitura("sem_livro")
    if topo.preco_ask <= topo.preco_bid:
        return Leitura("livro_cruzado")       # leilao / transiente: nao marca
    if agora_ns - topo.ts_recv_ns > cfg.livro_max_idade_ms * 1_000_000:
        return Leitura("livro_velho")
    imb, mic = topo.desequilibrio, microprice(topo)
    if imb is None or mic is None:
        return Leitura("sem_livro")
    motivo: str | None = None
    if topo.preco_ask - topo.preco_bid > cfg.spread_max_ticks * cfg.tick + 1e-9:
        motivo = "spread_largo"
    elif (topo.qtd_bid or 0) + (topo.qtd_ask or 0) < cfg.qtd_min_topo:
        motivo = "topo_raso"
    # marcavel: mesmo com spread largo ou topo raso da' para SAIR a mercado
    return Leitura(motivo, True, topo.preco_bid, topo.preco_ask, imb, mic)


@dataclass
class PosicaoMicro:
    lado: int                 # +1 comprado, -1 vendido
    preco_entrada: float
    ts_entrada_ns: int
    imbalance_entrada: float


@dataclass(frozen=True)
class Avaliacao:
    acao: Acao
    motivo: str
    lado: int = 0             # direcao da ENTRADA (+1/-1); 0 em ZERAR/NADA
    preco: float | None = None  # preco de execucao assumido (taker)
    imbalance: float | None = None
    micro: float | None = None
    spread: float | None = None


@dataclass
class _Acum:
    n: int = 0
    soma: float = 0.0
    a_favor: int = 0
    contra: int = 0

    def resumo(self) -> dict[str, float | int | None]:
        return {"n": self.n,
                "media_pts": round(self.soma / self.n, 2) if self.n else None,
                "pct_a_favor": round(100 * self.a_favor / self.n, 1) if self.n else None,
                "pct_contra": round(100 * self.contra / self.n, 1) if self.n else None}


@dataclass
class SondaDePrevisao:
    horizontes_s: list[float]
    _pendentes: dict[float, deque[tuple[int, int, float]]] = field(default_factory=dict)
    _acum: dict[float, _Acum] = field(default_factory=dict)
    spread_soma: float = 0.0
    gatilhos: int = 0

    def __post_init__(self) -> None:
        for h in self.horizontes_s:
            self._pendentes[h] = deque()
            self._acum[h] = _Acum()

    def registrar(self, ts_ns: int, lado: int, mid: float, spread: float) -> None:
        self.gatilhos += 1
        self.spread_soma += spread
        for h in self.horizontes_s:
            self._pendentes[h].append((ts_ns + int(h * _NS), lado, mid))

    def resolver(self, agora_ns: int, mid: float) -> None:
        for h, fila in self._pendentes.items():
            ac = self._acum[h]
            while fila and fila[0][0] <= agora_ns:
                _, lado, mid0 = fila.popleft()
                delta = (mid - mid0) * lado
                ac.n += 1
                ac.soma += delta
                ac.a_favor += delta > 0
                ac.contra += delta < 0

    def resumo(self) -> dict[str, object]:
        return {"gatilhos": self.gatilhos,
                "spread_medio_pts": (round(self.spread_soma / self.gatilhos, 2)
                                     if self.gatilhos else None),
                **{f"h{h:g}s": self._acum[h].resumo() for h in self.horizontes_s}}


@dataclass
class EstatisticasMicro:
    operacoes: int = 0
    ganhos: int = 0
    pnl_bruto: float = 0.0
    pnl_liquido: float = 0.0
    perdas_seguidas: int = 0
    bloqueado: str | None = None
    saidas: Counter[str] = field(default_factory=Counter)
    filtros: Counter[str] = field(default_factory=Counter)
    duracao_soma_s: float = 0.0


class DecisorMicroprice:
    """Estado do dia (posicao, persistencia, limites). `avaliar` so'
    DECIDE; `abrir`/`fechar` registram o que de fato aconteceu -- ao vivo
    o preco pode ser o do fill, e a vaga do modo exclusivo pode recusar a
    entrada, entao o decisor nunca assume que a propria decisao virou
    posicao."""

    def __init__(self, cfg: EAMicropriceConfig) -> None:
        self.cfg = cfg
        self.posicao: PosicaoMicro | None = None
        self.stats = EstatisticasMicro()
        self.sonda = SondaDePrevisao(list(cfg.sonda_horizontes_s))
        self._cand = 0
        self._desde_ns = 0
        self._disparou = False
        self._cooldown_ate_ns = 0

    # ------------------------------------------------------------------
    def _persistencia(self, leitura: Leitura, agora_ns: int) -> int:
        """Lado (+1/-1) cujo desbalanco persistiu o bastante, senao 0.
        Registra na sonda a BORDA de subida (uma vez por corrida)."""
        cfg = self.cfg
        if leitura.motivo is not None:
            lado = 0
        elif leitura.imbalance >= cfg.limiar_entrada:
            lado = 1
        elif leitura.imbalance <= -cfg.limiar_entrada:
            lado = -1
        else:
            lado = 0
        if lado == 0:
            self._cand, self._disparou = 0, False
            return 0
        if lado != self._cand:
            self._cand, self._desde_ns, self._disparou = lado, agora_ns, False
        if agora_ns - self._desde_ns < cfg.persistencia_ms * 1_000_000:
            return 0
        if not self._disparou:
            self._disparou = True
            self.sonda.registrar(agora_ns, lado, leitura.mid, leitura.spread)
        return lado

    def avaliar(self, topo: TopoDoLivro | None, agora_ns: int) -> Avaliacao:
        cfg = self.cfg
        leitura = ler_topo(topo, cfg, agora_ns)
        if leitura.marcavel:
            self.sonda.resolver(agora_ns, leitura.mid)
        lado = self._persistencia(leitura, agora_ns)
        hhmm = hhmm_brt(agora_ns)

        # ---------------- posicionado: so' saida ------------------------
        if self.posicao is not None:
            if not leitura.marcavel:
                return Avaliacao(Acao.NADA, f"posicionado, sem marcacao ({leitura.motivo})")
            p = self.posicao
            marca = leitura.bid if p.lado > 0 else leitura.ask
            pnl = (marca - p.preco_entrada) * p.lado
            motivo = None
            if pnl >= cfg.alvo_ticks * cfg.tick - 1e-9:
                motivo = "alvo"
            elif pnl <= -cfg.stop_ticks * cfg.tick + 1e-9:
                motivo = "stop"
            elif leitura.imbalance * p.lado <= -cfg.limiar_saida:
                motivo = "imbalance_inverteu"
            elif agora_ns - p.ts_entrada_ns >= cfg.tempo_max_s * _NS:
                motivo = "tempo"
            elif hhmm >= cfg.janela_fim_hhmm:
                motivo = "fim_janela"
            if motivo is None:
                return Avaliacao(Acao.NADA, "posicionado")
            return Avaliacao(Acao.ZERAR, motivo, preco=marca,
                             imbalance=leitura.imbalance, micro=leitura.micro,
                             spread=leitura.spread)

        # ---------------- zerado: entrada ------------------------------
        if leitura.motivo is not None:
            self.stats.filtros[leitura.motivo] += 1
            return Avaliacao(Acao.NADA, leitura.motivo)
        if lado == 0:
            return Avaliacao(Acao.NADA, "sem_gatilho")
        bloqueio = None
        if self.stats.bloqueado:
            bloqueio = "bloqueado"
        elif not (cfg.janela_inicio_hhmm <= hhmm < cfg.janela_fim_hhmm):
            bloqueio = "fora_da_janela"
        elif agora_ns < self._cooldown_ate_ns:
            bloqueio = "cooldown"
        elif self.stats.operacoes >= cfg.max_operacoes_dia:
            bloqueio = "max_operacoes"
        elif (cfg.lado_permitido == "compra" and lado < 0) or (
                cfg.lado_permitido == "venda" and lado > 0):
            bloqueio = "lado_nao_permitido"
        if bloqueio:
            self.stats.filtros[bloqueio] += 1
            return Avaliacao(Acao.NADA, bloqueio)
        acao = Acao.COMPRAR if lado > 0 else Acao.VENDER
        return Avaliacao(acao, f"imbalance={leitura.imbalance:+.2f} persistiu "
                               f"{cfg.persistencia_ms}ms", lado=lado,
                         preco=leitura.ask if lado > 0 else leitura.bid,
                         imbalance=leitura.imbalance, micro=leitura.micro,
                         spread=leitura.spread)

    # ------------------------------------------------------------------
    def abrir(self, lado: int, preco: float, agora_ns: int, imbalance: float) -> None:
        self.posicao = PosicaoMicro(lado, preco, agora_ns, imbalance)

    def fechar(self, preco: float, agora_ns: int, motivo: str) -> dict[str, float | int | str]:
        """Contabiliza e devolve os campos para o log de fechamento."""
        assert self.posicao is not None, "fechar sem posicao"
        cfg, p, s = self.cfg, self.posicao, self.stats
        bruto = (preco - p.preco_entrada) * p.lado
        liquido = bruto - cfg.custo_pontos_estimado
        dur_s = (agora_ns - p.ts_entrada_ns) / _NS
        s.operacoes += 1
        s.ganhos += liquido > 0
        s.pnl_bruto += bruto
        s.pnl_liquido += liquido
        s.duracao_soma_s += dur_s
        s.saidas[motivo] += 1
        s.perdas_seguidas = 0 if liquido > 0 else s.perdas_seguidas + 1
        if s.perdas_seguidas >= cfg.max_perdas_seguidas:
            s.bloqueado = f"{s.perdas_seguidas} perdas seguidas"
        elif s.pnl_liquido <= -cfg.perda_max_dia_pontos:
            s.bloqueado = f"perda do dia {s.pnl_liquido:.0f} pts"
        self._cooldown_ate_ns = agora_ns + int(cfg.cooldown_s * _NS)
        self.posicao = None
        return {"lado": p.lado, "entrada": p.preco_entrada, "saida": preco,
                "pnl_bruto": round(bruto, 1), "pnl_liquido": round(liquido, 1),
                "duracao_s": round(dur_s, 2), "motivo": motivo,
                "imbalance_entrada": round(p.imbalance_entrada, 3)}

    def resumo(self) -> dict[str, object]:
        s = self.stats
        return {"operacoes": s.operacoes,
                "pct_ganho": round(100 * s.ganhos / s.operacoes, 1) if s.operacoes else None,
                "pnl_bruto_pts": round(s.pnl_bruto, 1),
                "pnl_liquido_pts": round(s.pnl_liquido, 1),
                "duracao_media_s": (round(s.duracao_soma_s / s.operacoes, 2)
                                    if s.operacoes else None),
                "saidas": dict(s.saidas), "bloqueado": s.bloqueado,
                # conta AVALIACOES (cadencia de `avaliacao_ms`), nao eventos:
                # serve para ver o que mais barra a entrada, nao para taxa.
                "avaliacoes_filtradas": dict(s.filtros),
                "posicionado": self.posicao is not None,
                "sonda": self.sonda.resumo()}
