"""
Ciclo de ordens do 123 (passo 4 do F5, EAS_DE_PRECO.md 5.4).

    livre --(candidato)--> entrada_pendente (STOP na corretora, vale ate' o
    fim de t+1) --(fill)--> posicionado (STOP de protecao + LIMITADA de
    alvo, juntas) --(uma executa)--> saindo (cancela a outra) --(cancel
    confirmado)--> livre
          \\--(fim de t+1 sem fill)--> cancelando_entrada --> livre

Regras da ficha que moram aqui: um candidato por vez ("posicao aberta
ignora sinal" -- e pendente tambem: `ignorado_posicao` /
`ignorado_pendente`, contados); zeragem 17:30 (cancela o que estiver
vivo, zera a mercado se posicionado); OCO e' do EA porque a DLL nao tem.

DOIS MODOS, UM CICLO
--------------------
- REAL (executor): ordens vao para a corretora; fills, aceites e
  cancelamentos vem dos callbacks (`executor.eventos_de(profit_id)`),
  lidos no `tick`. Status medidos no E2b: New / Filled / Canceled;
  ClientCreated nao significa nada.
- DRY_RUN (executor=None): os fills sao SIMULADOS pelo tape, no
  `on_trade`: stop de entrada executa no primeiro trade que cruza o
  nivel (fill = preco do trade); stop de protecao idem; limitada de
  alvo executa AO NIVEL no primeiro trade que o toca. E' o que roda no
  pregao em dry_run (passo 7) para olhar barras e ordens antes do E4.

O QUE O FORWARD MEDE SAI DAQUI: por ordem, `nivel`, `fill`,
`slippage_pts` (fill - nivel, sinal do lado: positivo = contra o EA),
`latencia_ms` (envio -> primeiro callback; envio -> fill). Por
operacao, `OperacaoRegistrada` com tudo (passo 6 grava em parquet).

TIMEOUTS (defeito de execucao, nao de estrategia -- logam CONFIRA):
aceite da stop de entrada 10 s; confirmacao de cancelamento 10 s. Um
cancelamento nao confirmado deixa o ciclo em `livre` COM AVISO -- a
reconciliacao de ordens (4b) e' quem limpa.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from .sinal import BarraFechada
from .sinal_123 import Candidato123, SinalPreco123

log = structlog.get_logger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")
_NS = 1_000_000_000


def _cancelada(status: str) -> bool:
    return "cancel" in status.lower()


def _toca(lado: str, price: float, nivel: float, a_favor: bool) -> bool:
    """Compra: 'a favor' e' para cima (entrada/alvo), 'contra' para baixo
    (stop). Venda espelha."""
    acima = price >= nivel
    abaixo = price <= nivel
    if lado == "compra":
        return acima if a_favor else abaixo
    return abaixo if a_favor else acima


def _rejeitada(status: str) -> bool:
    s = status.lower()
    return "notcreated" in s or "reject" in s or "rejeit" in s or "invalid" in s


@dataclass
class OrdemViva:
    papel: str                     # entrada | stop | alvo | zeragem
    lado: str                      # compra | venda (da ordem, nao do trade)
    nivel: float
    profit_id: int | None = None
    cl_ord_id: str = ""
    t_envio: float = 0.0
    t_primeiro_callback: float | None = None
    t_fill: float | None = None
    fill: float | None = None
    status: list[str] = field(default_factory=list)
    t_cancel_envio: float | None = None
    t_cancel_confirmado: float | None = None
    viva: bool = True

    @property
    def sinal_lado(self) -> int:
        return 1 if self.lado == "compra" else -1

    @property
    def slippage_pts(self) -> float | None:
        return (self.fill - self.nivel) * self.sinal_lado if self.fill is not None else None

    def resumo(self) -> dict[str, Any]:
        def ms(a: float | None, b: float | None) -> float | None:
            return round((b - a) * 1000, 1) if a is not None and b is not None else None
        return {"papel": self.papel, "lado": self.lado, "nivel": self.nivel,
                "profit_id": self.profit_id, "cl_ord_id": self.cl_ord_id, "fill": self.fill,
                "slippage_pts": self.slippage_pts, "status": self.status,
                "latencia_aceite_ms": ms(self.t_envio, self.t_primeiro_callback),
                "latencia_fill_ms": ms(self.t_envio, self.t_fill),
                "latencia_cancel_ms": ms(self.t_cancel_envio, self.t_cancel_confirmado)}


@dataclass
class OperacaoRegistrada:
    candidato: Candidato123
    entrada: OrdemViva
    stop: OrdemViva | None = None
    alvo: OrdemViva | None = None
    zeragem: OrdemViva | None = None
    desfecho: str = ""             # nao_executou | alvo | stop | zeragem | erro
    pnl_pts: float | None = None
    avisos: list[str] = field(default_factory=list)

    def resumo(self) -> dict[str, Any]:
        ordens = {k: v.resumo() for k, v in
                  (("entrada", self.entrada), ("stop", self.stop), ("alvo", self.alvo),
                   ("zeragem", self.zeragem)) if v is not None}
        return {"candidato": self.candidato.resumo(), "desfecho": self.desfecho,
                "pnl_pts": self.pnl_pts, "avisos": self.avisos, "ordens": ordens}


class CicloDeOrdens123:
    def __init__(self, sinal: SinalPreco123, executor: Any | None = None,
                 quantidade: int = 1, zeragem_hhmm: int = 1730,
                 slack_limite_pts: float = 50.0, timeout_s: float = 10.0) -> None:
        self.sinal = sinal
        self.executor = executor
        self.dry_run = executor is None
        self.quantidade = quantidade
        self.zeragem_hhmm = zeragem_hhmm
        self.slack = slack_limite_pts
        self.timeout = timeout_s
        self.estado = "livre"
        self.op: OperacaoRegistrada | None = None
        self.operacoes: list[OperacaoRegistrada] = []
        self.ignorados_posicao = 0
        self.ignorados_pendente = 0
        self._t_limite = 0.0
        self._zerado_hoje: dt.date | None = None

    # ------------------------------------------------------------------ util
    @staticmethod
    def _hhmm(ts_ns: int) -> int:
        t = dt.datetime.fromtimestamp(ts_ns / _NS, tz=_TZ)
        return t.hour * 100 + t.minute

    def _enviar(self, o: OrdemViva, funcao: str, **kw: Any) -> bool:
        o.t_envio = time.monotonic()
        if self.dry_run:
            o.profit_id, o.cl_ord_id = -1, "dry"
            o.status.append("DRY")
            log.info("ea.123.ordem_simulada", papel=o.papel, lado=o.lado, nivel=o.nivel)
            return True
        oid = getattr(self.executor, funcao)(**kw)
        o.profit_id = oid
        if oid <= 0:
            o.viva = False
            o.status.append("RECUSADA")
            return False
        return True

    def _cancelar(self, o: OrdemViva) -> None:
        o.t_cancel_envio = time.monotonic()
        if self.dry_run:
            o.viva = False
            o.t_cancel_confirmado = o.t_cancel_envio
            o.status.append("DRY_CANCEL")
            return
        if not o.cl_ord_id:
            self._aviso(f"{o.papel}: sem ClOrdID, nao da' para cancelar -- CONFIRA NO PROFIT")
            o.viva = False
            return
        assert self.executor is not None
        self.executor.cancelar(o.cl_ord_id)

    def _aviso(self, texto: str) -> None:
        log.error("ea.123.aviso", texto=texto)
        if self.op is not None:
            self.op.avisos.append(texto)

    def _absorver(self, o: OrdemViva) -> None:
        """Le callbacks novos da ordem (modo real)."""
        if self.dry_run or o.profit_id is None or o.profit_id <= 0:
            return
        assert self.executor is not None
        for e in self.executor.eventos_de(o.profit_id)[len(o.status):]:
            o.status.append(e.status)
            if o.t_primeiro_callback is None:
                o.t_primeiro_callback = e.t_mono
            if e.cl_ord_id and not o.cl_ord_id:
                o.cl_ord_id = e.cl_ord_id
            if e.executada >= e.qtd > 0 and o.t_fill is None:
                o.t_fill, o.fill, o.viva = e.t_mono, float(e.preco_medio), False
                log.info("ea.123.fill", papel=o.papel, fill=o.fill, nivel=o.nivel,
                         slippage_pts=o.slippage_pts,
                         latencia_ms=round((e.t_mono - o.t_envio) * 1000, 1))
            if o.t_cancel_envio is not None and _cancelada(e.status):
                o.t_cancel_confirmado, o.viva = e.t_mono, False
            if _rejeitada(e.status):
                o.viva = False
                self._aviso(f"{o.papel}: rejeitada ({e.status} {e.texto})")

    # ------------------------------------------------------------ eventos
    def on_barra(self, b: BarraFechada) -> None:
        c = self.sinal.barra_fechada(b)
        if c is None:
            return
        if self.estado == "livre":
            self._armar(c)
        elif self.estado == "posicionado" or self.estado == "saindo":
            self.ignorados_posicao += 1
            log.info("ea.123.ignorado_posicao", **c.resumo())
        else:
            self.ignorados_pendente += 1
            log.info("ea.123.ignorado_pendente", **c.resumo())

    def _armar(self, c: Candidato123) -> None:
        o = OrdemViva("entrada", c.lado, c.entrada)
        limite = c.entrada + self.slack if c.lado == "compra" else c.entrada - self.slack
        self.op = OperacaoRegistrada(candidato=c, entrada=o)
        if not self._enviar(o, "enviar_stop", lado=c.lado, gatilho=c.entrada, limite=limite):
            self._fechar_op("erro", "stop de entrada recusada pela DLL")
            return
        self._t_limite = time.monotonic() + self.timeout
        self.estado = "entrada_pendente"
        log.info("ea.123.armado", **c.resumo(), valido_ate_ns=c.valido_ate_ns)

    def on_trade(self, ts_ns: int, price: float) -> None:
        """Validade da entrada, zeragem e (dry_run) fills simulados."""
        hhmm = self._hhmm(ts_ns)
        dia = dt.datetime.fromtimestamp(ts_ns / _NS, tz=_TZ).date()
        if hhmm >= self.zeragem_hhmm and self._zerado_hoje != dia and self.estado != "livre":
            self._zerado_hoje = dia
            self._zeragem_forcada(price)
            return
        if self.op is None:
            return
        c = self.op.candidato
        if self.estado == "entrada_pendente":
            if ts_ns >= c.valido_ate_ns:
                self._cancelar_entrada()
            elif self.dry_run:
                o = self.op.entrada
                if _toca(c.lado, price, o.nivel, a_favor=True):
                    o.fill, o.t_fill, o.viva = price, time.monotonic(), False
                    o.status.append("DRY_FILL")
                    self._apos_fill_entrada()
        elif self.estado == "posicionado" and self.dry_run:
            assert self.op.stop is not None and self.op.alvo is not None
            s, a = self.op.stop, self.op.alvo
            if _toca(c.lado, price, s.nivel, a_favor=False):
                s.fill, s.t_fill, s.viva = price, time.monotonic(), False
                s.status.append("DRY_FILL")
                self._apos_saida("stop")
            elif _toca(c.lado, price, a.nivel, a_favor=True):
                a.fill, a.t_fill, a.viva = a.nivel, time.monotonic(), False
                a.status.append("DRY_FILL")
                self._apos_saida("alvo")

    def tick(self) -> None:
        """Modo real: absorve callbacks e cuida dos timeouts. Barato; chamar a
        cada 0,5 s. Em dry_run nao faz nada (tudo acontece no on_trade)."""
        if self.dry_run or self.op is None:
            return
        st = self.estado
        if st == "entrada_pendente":
            o = self.op.entrada
            self._absorver(o)
            if o.fill is not None:
                self._apos_fill_entrada()
            elif not o.viva:
                self._fechar_op("erro", "stop de entrada morreu sem fill")
            elif o.t_primeiro_callback is None and time.monotonic() > self._t_limite:
                self._aviso("stop de entrada sem callback em 10 s -- CONFIRA NO PROFIT")
                self._fechar_op("erro", "sem aceite")
        elif st == "cancelando_entrada":
            o = self.op.entrada
            self._absorver(o)
            if o.fill is not None:                      # executou no meio do cancel
                self._apos_fill_entrada()
            elif o.t_cancel_confirmado is not None:
                self._fechar_op("nao_executou")
            elif time.monotonic() > self._t_limite:
                self._aviso("cancelamento da entrada nao confirmado -- CONFIRA NO PROFIT")
                self._fechar_op("nao_executou")
        elif st == "posicionado":
            assert self.op.stop is not None and self.op.alvo is not None
            for papel, o in (("stop", self.op.stop), ("alvo", self.op.alvo)):
                self._absorver(o)
                if o.fill is not None:
                    self._apos_saida(papel)
                    return
        elif st == "saindo":
            outra = self._outra
            self._absorver(outra)
            if outra.t_cancel_confirmado is not None:
                self._fechar_op(self._desfecho_pendente)
            elif outra.fill is not None:
                self._aviso(f"{outra.papel} executou depois da outra perna: POSICAO CONTRARIA "
                            "-- CONFIRA NO PROFIT (4b zera)")
                self._fechar_op(self._desfecho_pendente)
            elif time.monotonic() > self._t_limite:
                self._aviso("cancelamento da perna restante nao confirmado -- CONFIRA NO PROFIT")
                self._fechar_op(self._desfecho_pendente)
        elif st == "zerando":
            assert self.op.zeragem is not None
            self._absorver(self.op.zeragem)
            if self.op.zeragem.fill is not None or time.monotonic() > self._t_limite:
                if self.op.zeragem.fill is None:
                    self._aviso("zeragem sem fill -- CONFIRA A POSICAO NO PROFIT")
                self._fechar_op("zeragem")

    # -------------------------------------------------------- transicoes
    def _cancelar_entrada(self) -> None:
        assert self.op is not None
        self._cancelar(self.op.entrada)
        self._t_limite = time.monotonic() + self.timeout
        if self.dry_run:
            self._fechar_op("nao_executou")
        else:
            self.estado = "cancelando_entrada"

    def _apos_fill_entrada(self) -> None:
        assert self.op is not None
        c = self.op.candidato
        lado_saida = "venda" if c.lado == "compra" else "compra"
        s = OrdemViva("stop", lado_saida, c.stop)
        a = OrdemViva("alvo", lado_saida, c.alvo)
        self.op.stop, self.op.alvo = s, a
        lim = c.stop - self.slack if lado_saida == "venda" else c.stop + self.slack
        ok_s = self._enviar(s, "enviar_stop", lado=lado_saida, gatilho=c.stop, limite=lim)
        ok_a = self._enviar(a, "enviar_limitada", lado=lado_saida, preco=c.alvo)
        if not (ok_s and ok_a):
            self._aviso("perna de saida recusada -- zerando a mercado")
            self._zeragem_forcada(None)
            return
        self.estado = "posicionado"
        log.info("ea.123.posicionado", lado=c.lado, fill=self.op.entrada.fill,
                 slippage_entrada_pts=self.op.entrada.slippage_pts, stop=c.stop, alvo=c.alvo)

    def _apos_saida(self, papel: str) -> None:
        assert self.op is not None and self.op.stop is not None and self.op.alvo is not None
        self._outra = self.op.alvo if papel == "stop" else self.op.stop
        self._desfecho_pendente = papel
        self._cancelar(self._outra)
        self._t_limite = time.monotonic() + self.timeout
        if self.dry_run:
            self._fechar_op(papel)
        else:
            self.estado = "saindo"

    def _zeragem_forcada(self, preco_dry: float | None) -> None:
        assert self.op is not None
        for o in (self.op.entrada, self.op.stop, self.op.alvo):
            if o is not None and o.viva:
                self._cancelar(o)
        if self.estado in ("posicionado", "saindo"):
            z = OrdemViva("zeragem", "venda" if self.op.candidato.lado == "compra" else "compra",
                          nivel=preco_dry or 0.0)
            self.op.zeragem = z
            if self.dry_run:
                z.fill, z.t_fill, z.viva = preco_dry, time.monotonic(), False
                z.status.append("DRY_FILL")
                self._fechar_op("zeragem")
                return
            z.t_envio = time.monotonic()
            assert self.executor is not None
            z.profit_id = self.executor.zerar()
            self._t_limite = time.monotonic() + self.timeout
            self.estado = "zerando"
            return
        self._fechar_op("nao_executou", "zeragem 17:30 com entrada pendente")

    def _fechar_op(self, desfecho: str, nota: str = "") -> None:
        assert self.op is not None
        op = self.op
        op.desfecho = desfecho
        e = op.entrada
        saida = {"alvo": op.alvo, "stop": op.stop, "zeragem": op.zeragem}.get(desfecho)
        if e.fill is not None and saida is not None and saida.fill is not None:
            op.pnl_pts = (saida.fill - e.fill) * e.sinal_lado
        if nota:
            op.avisos.append(nota)
        self.operacoes.append(op)
        log.info("ea.123.operacao_fechada", **op.resumo())
        self.op = None
        self.estado = "livre"

    def encerrar_dia(self) -> None:
        if self.estado != "livre":
            self._zeragem_forcada(None)

    def hb(self) -> dict[str, Any]:
        return {"estado": self.estado, "operacoes": len(self.operacoes),
                "ignorados_posicao": self.ignorados_posicao,
                "ignorados_pendente": self.ignorados_pendente,
                "candidatos": self.sinal.candidatos_armados,
                "dry_run": self.dry_run}
