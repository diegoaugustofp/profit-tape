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

from .gate_fluxo import GateDeFluxo, SemFiltro
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
    limite: float | None = None    # stop-LIMITE: o preco limite enviado
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
    desfecho: str = ""             # nao_executou | alvo | stop | zeragem | erro | reconciliado
    pnl_pts: float | None = None
    # protecao do stop (EA_ARQUITETURA sec. 9, 2026-09-22): o stop-limite
    # disparou num salto e nao executou; o EA zerou a mercado. O desfecho
    # continua `stop`, que e' o resultado da ficha.
    stop_protegido: bool = False
    preco_disparou_protecao: float | None = None
    avisos: list[str] = field(default_factory=list)
    barra_gatilho: dict[str, Any] | None = None    # fluxo de t+1 (passo 6)
    infra: dict[str, Any] = field(default_factory=dict)   # estado da infra ao armar

    def resumo(self) -> dict[str, Any]:
        ordens = {k: v.resumo() for k, v in
                  (("entrada", self.entrada), ("stop", self.stop), ("alvo", self.alvo),
                   ("zeragem", self.zeragem)) if v is not None}
        r = {"candidato": self.candidato.resumo(), "desfecho": self.desfecho,
             "pnl_pts": self.pnl_pts, "avisos": self.avisos, "ordens": ordens,
             "barra_gatilho": self.barra_gatilho, "infra": self.infra}
        if self.stop_protegido:          # so' aparece quando houve protecao
            r["stop_protegido"] = True
            r["preco_disparou_protecao"] = self.preco_disparou_protecao
        return r


class CicloDeOrdens123:
    def __init__(self, sinal: SinalPreco123, executor: Any | None = None,
                 quantidade: int = 1, zeragem_hhmm: int = 1730,
                 slack_limite_pts: float = 50.0, timeout_s: float = 10.0,
                 gate: GateDeFluxo | None = None,
                 vagas: Any | None = None, symbol: str = "", nome: str = "",
                 registro: Any | None = None, infra_extra: Any | None = None,
                 diario: Any | None = None) -> None:
        self.sinal = sinal
        self.executor = executor
        self.gate: GateDeFluxo = gate or SemFiltro()
        self.vagas, self.symbol, self.nome = vagas, symbol, nome
        self.registro = registro                 # passo 6: grava cada operacao
        self.diario = diario                     # uma linha por SINAL (16/09)
        self.infra_extra = infra_extra           # callable -> dict do estado da infra
        self.rejeitados_gate = 0
        self.sinais_sem_vaga = 0
        self.reconciliacoes = 0
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
        self._ts_alem_do_limite: int | None = None   # protecao do stop (sec. 9)
        self._desfecho_da_zeragem = "zeragem"
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
        # passo 6: a primeira barra fechada depois de armar e' a barra do
        # GATILHO (t+1) -- o fluxo dela e' a amostra da porta de volume.
        if (self.op is not None and self.op.barra_gatilho is None
                and b.bar_id > self.op.candidato.barra_sinal_id):
            self.op.barra_gatilho = {"bar_id": b.bar_id, "vol_agr_compra": b.vol_agr_compra,
                                     "vol_agr_venda": b.vol_agr_venda, "n_trades": b.n_trades,
                                     "vol_total": b.vol_total,
                                     "volume_confiavel": b.volume_confiavel,
                                     "maior_lacuna_s": b.maior_lacuna_s,
                                     "high": b.high, "low": b.low, "close": b.close}
        c = self.sinal.barra_fechada(b)
        registrar = getattr(self.gate, "registrar_barra", None)
        if c is None:
            if registrar is not None:
                registrar(b)
            return
        if self.estado == "livre":
            passou = self.gate.permite(c, b)
            visto = dict(getattr(self.gate, "ultimo", {}) or {})
            if registrar is not None:
                registrar(b)
            if not passou:
                self.rejeitados_gate += 1
                # gate INDEFINIDO (barra nao confiavel ou sem perfil) e' um
                # desfecho diferente de "reprovou pelo volume" -- o diario
                # separa, porque um e' mercado e o outro e' feed.
                indefinido = (not visto.get("confiavel", True)) or visto.get("mediana") is None
                desfecho = "gate_indefinido" if indefinido else "rejeitado_gate"
                log.info(f"ea.123.{desfecho}", gate=type(self.gate).__name__, **c.resumo())
                self._diario_descarte(c, desfecho, visto)
                return
            if self.vagas is not None and not self.vagas.tentar_ocupar(
                    self.symbol, self.nome, simulado=self.dry_run):
                self.sinais_sem_vaga += 1
                log.info("ea.123.sinal_sem_vaga", **c.resumo())
                self._diario_descarte(c, "sem_vaga",
                                      {"dono_da_vaga": self.vagas.dono(self.symbol)})
                return
            self._armar(c)
        else:
            # Sinal que chega com o EA ocupado. ANTES (ate' 2026-09-21): ia direto
            # para `posicao_aberta`/`pendente` sem passar pelo gate -- o diario
            # nao sabia se o gate o reprovaria, e o custo do gate saia
            # SUBESTIMADO (em 18/09, 5 de 7 sinais bloqueados, nenhum julgado).
            # E o `registrar_barra` nao era chamado aqui, contra a propria
            # docstring do gate. Agora: avaliacao SEM efeito colateral,
            # registrada no diario; contadores reais intocados.
            avaliar = getattr(self.gate, "avaliar", None)
            sombra: dict[str, Any] = {"estado": self.estado}
            if avaliar is not None:
                passaria, visto = avaliar(c, b)
                sombra.update({"gate_passaria": bool(passaria), "gate": visto})
            if registrar is not None:
                registrar(b)
            if self.estado in ("posicionado", "saindo"):
                self.ignorados_posicao += 1
                log.info("ea.123.ignorado_posicao", **c.resumo(),
                         gate_passaria=sombra.get("gate_passaria"))
                self._diario_descarte(c, "posicao_aberta", sombra)
            else:
                self.ignorados_pendente += 1
                log.info("ea.123.ignorado_pendente", **c.resumo(),
                         gate_passaria=sombra.get("gate_passaria"))
                self._diario_descarte(c, "pendente", sombra)

    def _diario_descarte(self, c: Candidato123, desfecho: str,
                         motivo: dict[str, Any]) -> None:
        if self.diario is None:
            return
        try:
            self.diario.descartado(c, desfecho, motivo,
                                   self.infra_extra() if self.infra_extra else {})
        except Exception:
            log.exception("ea.123.diario_falhou", desfecho=desfecho)

    def _armar(self, c: Candidato123) -> None:
        o = OrdemViva("entrada", c.lado, c.entrada)
        limite = c.entrada + self.slack if c.lado == "compra" else c.entrada - self.slack
        self.op = OperacaoRegistrada(candidato=c, entrada=o)
        self.op.infra = {"reconciliacoes_ate_aqui": self.reconciliacoes,
                         "gate": dict(getattr(self.gate, "ultimo", {}) or {}),
                         **(self.infra_extra() if self.infra_extra else {})}
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
        if self.estado == "posicionado" and not self.dry_run:
            self._proteger_stop(ts_ns, price)
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
                # BUG (corrigido 2026-09-22): dizia "(4b zera)", mas a 4b so'
                # roda quando a conexao cai e VOLTA. Com o EA no ar, a posicao
                # invertida ficava aberta e o EA seguia operando por cima.
                self._aviso(f"{outra.papel} executou depois da outra perna: POSICAO CONTRARIA "
                            "-- zerando a mercado, CONFIRA NO PROFIT")
                if not self.dry_run and self.executor is not None:
                    self.executor.zerar()
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
                self._fechar_op(self._desfecho_da_zeragem)

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
        s.limite = lim
        ok_s = self._enviar(s, "enviar_stop", lado=lado_saida, gatilho=c.stop, limite=lim)
        ok_a = self._enviar(a, "enviar_limitada", lado=lado_saida, preco=c.alvo)
        if not (ok_s and ok_a):
            self._aviso("perna de saida recusada -- zerando a mercado")
            self._zeragem_forcada(None)
            return
        self.estado = "posicionado"
        log.info("ea.123.posicionado", lado=c.lado, fill=self.op.entrada.fill,
                 slippage_entrada_pts=self.op.entrada.slippage_pts, stop=c.stop, alvo=c.alvo)

    CARENCIA_STOP_PROTEGIDO_NS = 2 * _NS

    def _proteger_stop(self, ts_ns: int, price: float) -> None:
        """
        PRE-REGISTRO 2026-09-22 (EA_ARQUITETURA secao 9). Stop-LIMITE que
        dispara num salto ALEM do limite vira uma limitada que nao executa:
        a posicao fica aberta e sem protecao ate' a zeragem das 17:30.
        Regra: negocio estritamente alem do LIMITE do stop + 2 s de tempo de
        MERCADO sem fill -> cancela as duas pernas, zera a mercado, avisa.
        Desfecho continua `stop` (e' o resultado da ficha), com
        `stop_protegido=True`.
        """
        assert self.op is not None
        o = self.op.stop
        if o is None or o.limite is None or o.fill is not None:
            return
        # o stop de saida COMPRA quando a posicao e' vendida
        alem = price > o.limite if o.lado == "compra" else price < o.limite
        if not alem:
            self._ts_alem_do_limite = None          # voltou: o limite ainda pode executar
            return
        if self._ts_alem_do_limite is None:
            self._ts_alem_do_limite = ts_ns
            return
        if ts_ns - self._ts_alem_do_limite < self.CARENCIA_STOP_PROTEGIDO_NS:
            return
        log.error("ea.123.stop_protegido", preco_gatilho=o.nivel, limite=o.limite,
                  preco_do_tape=price, segundos_alem=round(
                      (ts_ns - self._ts_alem_do_limite) / _NS, 2),
                  nota="stop-limite nao executou num salto: zerando a mercado")
        self.op.stop_protegido = True
        self.op.preco_disparou_protecao = price
        self._aviso(f"stop disparou e NAO executou (tape {price:.0f} alem do limite "
                    f"{o.limite:.0f}) -- zerando a mercado, CONFIRA NO PROFIT")
        self._zeragem_forcada(None, desfecho="stop")

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

    def _zeragem_forcada(self, preco_dry: float | None, desfecho: str = "zeragem") -> None:
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
                self._fechar_op(desfecho)
                return
            z.t_envio = time.monotonic()
            assert self.executor is not None
            z.profit_id = self.executor.zerar()
            self._t_limite = time.monotonic() + self.timeout
            self._desfecho_da_zeragem = desfecho
            self.estado = "zerando"
            return
        self._fechar_op("nao_executou", "zeragem 17:30 com entrada pendente")

    def _fechar_op(self, desfecho: str, nota: str = "") -> None:
        assert self.op is not None
        op = self.op
        op.desfecho = desfecho
        if self.vagas is not None:
            self.vagas.liberar(self.symbol, self.nome)
        e = op.entrada
        saida = {"alvo": op.alvo, "stop": op.stop, "zeragem": op.zeragem}.get(desfecho)
        if e.fill is not None and saida is not None and saida.fill is not None:
            op.pnl_pts = (saida.fill - e.fill) * e.sinal_lado
        if nota:
            op.avisos.append(nota)
        self.operacoes.append(op)
        log.info("ea.123.operacao_fechada", **op.resumo())
        if self.registro is not None:
            try:
                self.registro.gravar(op)
            except Exception:
                log.exception("ea.123.registro_falhou")
        if self.diario is not None:
            try:
                self.diario.operacao(op)
            except Exception:
                log.exception("ea.123.diario_falhou", desfecho=desfecho)
        self.op = None
        self.estado = "livre"

    # ------------------------------------------------- 4b: reconciliacao
    def limpeza_na_subida(self) -> dict[str, Any]:
        """
        Ao subir em modo REAL (2026-09-22). Cobre o caso que a reconciliacao
        nao cobre: o processo anterior MORREU com ordens vivas (queda de
        energia, travamento). O EA novo nao conhece os ClOrdIDs, entao nao
        consegue cancelar ordem a ordem -- e uma perna orfa de stop ou alvo
        pode abrir uma posicao nova mais tarde. Aqui: `SendCancelOrders`
        (TODAS as ordens do ativo na conta) e, se houver posicao, zera.

        CUSTO DECLARADO: cancela TODAS as ordens do ativo naquela conta,
        inclusive as manuais. Por isso so' roda se a vaga do ticker nao e' de
        OUTRO EA -- senao cancelaria as ordens de um EA real ja' operando.
        """
        rel: dict[str, Any] = {}
        if self.dry_run or self.executor is None:
            return rel
        dono = self.vagas.dono(self.symbol) if self.vagas is not None else None
        if dono not in (None, self.nome):
            rel["acao"] = "adiada_vaga_de_outro"
            log.warning("ea.123.limpeza_na_subida", dono_da_vaga=dono, **rel,
                        nota="outro EA real opera este ticker: nao cancela as ordens dele")
            return rel
        if self.estado != "livre":
            rel["acao"] = "ignorada_ciclo_ocupado"
            return rel
        rel["cancel_todas_retorno"] = self.executor.cancelar_todas()
        pos = self.executor.consultar_posicao()
        real = int(pos.quantidade_liquida) if pos.plausivel else None
        rel["posicao_real"] = real
        if real is None:
            self._aviso("posicao implausivel na subida -- CONFIRA NO PROFIT")
            rel["acao"] = "posicao_implausivel"
        elif real != 0:
            log.error("ea.123.posicao_orfa", real=real, momento="subida")
            self.executor.zerar()
            self._aviso(f"posicao orfa na SUBIDA (real={real}) zerada a mercado "
                        "-- CONFIRA NO PROFIT")
            rel["acao"] = "zerou_orfa"
        else:
            rel["acao"] = "limpo"
        log.warning("ea.123.limpeza_na_subida", **rel,
                    nota="confira no Profit: nenhuma ordem de " + self.symbol + " viva nesta conta")
        return rel

    def reconciliar_apos_reconexao(self) -> dict[str, Any]:
        """
        Chamado quando a corretora volta a ficar pronta (ou no arranque com
        posicao desconhecida). Politica, decidida em 2026-09-14 (5.4):

          1. cancela ORDEM A ORDEM as que este ciclo conhece (entrada,
             stop, alvo), com `SendCancelOrder` -- a funcao SINGULAR,
             provada no E2b. **Decisao do operador (17/09): seguir sem a
             plural (`SendCancelOrders`), que nunca foi testada ao vivo.**
             LIMITACAO DECLARADA: ordem ORFA de processo morto (queda de
             energia com ordem viva) nao tem ClOrdID na memoria do EA
             novo e NAO e' cancelada -- fica o aviso CONFIRA AS ORDENS NO
             PROFIT e a limpeza e' manual. Com stop e alvo REAIS na
             corretora a posicao segue protegida; o risco residual e' um
             par orfao executar depois;
          2. consulta a POSICAO real;
          3. compara com o que o ciclo acha que tem:
             - ciclo posicionado e posicao real igual  -> re-arma stop + alvo;
             - ciclo posicionado e posicao real zero   -> uma perna executou na
               queda: fecha a operacao como `reconciliado` (P&L desconhecido);
             - ciclo nao posicionado e posicao real != 0 -> orfa: ZERA a mercado;
             - ciclo com entrada pendente e posicao zero -> `nao_executou`.
        Em dry_run so' reseta o que estiver pendente.
        """
        self.reconciliacoes += 1
        rel: dict[str, Any] = {"estado_antes": self.estado}
        if self.dry_run:
            if self.op is not None and self.estado == "entrada_pendente":
                self._fechar_op("nao_executou", "reconexao (dry_run)")
            rel["estado_depois"] = self.estado
            return rel
        assert self.executor is not None
        # ordem a ordem, com a funcao singular (ver docstring)
        canceladas = []
        if self.op is not None:
            for o in (self.op.entrada, self.op.stop, self.op.alvo):
                if o is not None and o.viva and o.cl_ord_id:
                    self._cancelar(o)
                    canceladas.append(o.papel)
        rel["canceladas"] = canceladas
        pos = self.executor.consultar_posicao()
        real = int(pos.quantidade_liquida) if pos.plausivel else None
        rel["posicao_real"] = real
        esperado = 0
        if self.op is not None and self.estado in ("posicionado", "saindo"):
            esperado = self.quantidade if self.op.candidato.lado == "compra" else -self.quantidade
        rel["posicao_esperada"] = esperado
        if real is None:
            self._aviso("posicao implausivel na reconciliacao -- CONFIRA NO PROFIT")
        elif esperado != 0 and real == esperado:
            assert self.op is not None
            for o in (self.op.entrada, self.op.stop, self.op.alvo):
                if o is not None:
                    o.viva = False
            self._apos_fill_entrada()                     # re-arma stop + alvo
            rel["acao"] = "rearmou_saida"
        elif esperado != 0 and real == 0:
            self._fechar_op("reconciliado", "posicao zerada durante a queda: uma perna executou")
            rel["acao"] = "fechou_reconciliado"
        elif real != esperado:
            # Qualquer posicao REAL diferente da esperada e diferente de zero.
            # Inclui a orfa (esperado 0) E a INVERTIDA -- o caso levantado pelo
            # operador em 22/09: stop e alvo sao ordens INDEPENDENTES na
            # corretora (a DLL nao tem OCO nativo); com o EA parado, se as
            # DUAS pernas executarem, a posicao inverte. Antes, esse caso caia
            # no `else` abaixo: registrava `nao_executou`, deixava a posicao
            # invertida ABERTA e sem protecao, e liberava o EA para operar por
            # cima. Agora: cancela o que houver do ativo, zera a mercado
            # (SendZeroPositionAtMarket zera seja qual for o sentido) e avisa.
            log.error("ea.123.posicao_inesperada", real=real, esperado=esperado)
            self.executor.cancelar_todas()
            self.executor.zerar()
            if self.op is not None:
                self._fechar_op("erro", f"posicao inesperada na reconciliacao: "
                                        f"real={real} esperado={esperado}")
            self._aviso(f"posicao inesperada (real={real}, esperado={esperado}) zerada a "
                        "mercado -- CONFIRA NO PROFIT")
            rel["acao"] = "zerou_orfa" if esperado == 0 else "zerou_inesperada"
        else:
            if self.op is not None:
                self._fechar_op("nao_executou", "reconexao: ordens canceladas")
            rel["acao"] = "limpou_pendentes"
        rel["estado_depois"] = self.estado
        log.warning("ea.123.reconciliado", **rel)
        return rel

    def encerrar_dia(self) -> None:
        if self.estado != "livre":
            self._zeragem_forcada(None)

    def hb(self) -> dict[str, Any]:
        return {"estado": self.estado, "operacoes": len(self.operacoes),
                "ignorados_posicao": self.ignorados_posicao,
                "ignorados_pendente": self.ignorados_pendente,
                "rejeitados_gate": self.rejeitados_gate,
                "gate_indefinidos": getattr(self.gate, "indefinidos", 0),
                "sinais_sem_vaga": self.sinais_sem_vaga,
                "reconciliacoes": self.reconciliacoes,
                "candidatos": self.sinal.candidatos_armados,
                "diario": (self.diario.resumo() if self.diario is not None else None),
                "dry_run": self.dry_run}
