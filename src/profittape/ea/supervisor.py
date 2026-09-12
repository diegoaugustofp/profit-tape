"""
E5.0 — SupervisorDeRisco: calcula e AVISA, nunca impede.

DECISAO DO OPERADOR (2026-09-11), que e' a razao de este modulo existir
separado do `GestorDeRisco`:

    "O valor de capital, risco maximo e outras metricas relacionadas nao
    podem ser limitantes do EA, elas devem ser calculadas e apresentadas.
    A decisao de segui-las e' sempre do operador. Se operar com saldo em
    conta de 2000 mas o recomendado for 5000 nao devemos controlar, o
    risco e' sempre do operador, sabendo q pode ser zerado por falta de
    margem."

Por isso: NENHUM metodo aqui devolve "nao pode". Tudo devolve NUMERO e
ALERTA. Quem decide e' o operador, olhando o log.

O QUE ISTO **NAO** SUBSTITUI
-----------------------------
O circuit breaker de perdas consecutivas (`GestorDeRisco.pode_abrir`)
continua sendo trava DE VERDADE, e deve continuar. Sao coisas
diferentes:

  - circuit breaker  -> protege contra DEFEITO (sequencia anomala de
                        perdas sugere que a estrategia quebrou hoje).
                        Trava mesmo. Nao e' escolha do operador.
  - supervisor       -> informa sobre ESCOLHA DE CAPITAL do operador
                        (quanto ele poe na conta vs. quanto N EAs
                        pediriam). Nunca trava.

FORA DO ESCOPO, POR DECISAO
----------------------------
Zeragem em cascata por falta de margem (o que a corretora faz quando o
capital acaba). Nao modelamos nem gerenciamos -- registrado em
docs/EA_ARQUITETURA.md 4.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ExigenciaDeEA:
    """O que UM EA pede, para o supervisor somar. `capital_recomendado`
    vem da mesma formula do `GestorDeRisco`: o stop catastrofico e'
    `capital * risco_max_pct / valor_ponto`, entao para um stop de X
    pontos com N contratos o capital recomendado e' o que torna esse
    stop igual ao risco maximo aceito."""

    nome: str
    capital_recomendado: float
    contratos: int
    ticker: str
    subconta: str | None = None


@dataclass
class Alerta:
    nivel: str      # "info" | "atencao" | "critico"
    codigo: str
    mensagem: str


@dataclass
class SupervisorDeRisco:
    """
    Um por processo (nao por EA). Conhece TODOS os EAs registrados e o
    capital que o operador de fato tem em conta.

    `capital_em_conta` e' o que o operador declara ter -- nao e'
    consultado da corretora (seria outra chamada de DLL e mais um ponto
    de falha; e o proprio operador disse que a decisao e' dele).
    """

    capital_em_conta: float
    exigencias: dict[str, ExigenciaDeEA] = field(default_factory=dict)

    def registrar(self, exigencia: ExigenciaDeEA) -> None:
        """Idempotente por nome -- registrar de novo SUBSTITUI, nao soma
        (evita contar duas vezes se a montagem rodar mais de uma vez)."""
        self.exigencias[exigencia.nome] = exigencia

    @property
    def capital_recomendado_total(self) -> float:
        return sum(e.capital_recomendado for e in self.exigencias.values())

    @property
    def contratos_totais(self) -> int:
        return sum(e.contratos for e in self.exigencias.values())

    @property
    def cobertura(self) -> float:
        """Fracao do recomendado que o operador de fato tem. 1.0 = exato,
        <1 = abaixo do recomendado (permitido, so' alerta), inf se o
        recomendado for zero (nenhum EA registrado)."""
        rec = self.capital_recomendado_total
        if rec <= 0:
            return float("inf")
        return self.capital_em_conta / rec

    def subcontas_duplicadas(self) -> dict[str, list[str]]:
        """EAs que compartilham a MESMA subconta -- volta o netting que as
        subcontas existem para evitar (E5, 4.2). Chave: subconta; valor:
        nomes dos EAs. So' conta subconta nao-nula com 2+ EAs."""
        por_sub: dict[str, list[str]] = {}
        for e in self.exigencias.values():
            if e.subconta:
                por_sub.setdefault(e.subconta, []).append(e.nome)
        return {sub: nomes for sub, nomes in por_sub.items() if len(nomes) > 1}

    def avaliar(self) -> list[Alerta]:
        """
        Devolve alertas. NUNCA levanta excecao, NUNCA devolve "bloqueado"
        -- o chamador loga e segue. E' o ponto central da decisao do
        operador: informar, nao impedir.
        """
        alertas: list[Alerta] = []
        if not self.exigencias:
            return alertas

        rec = self.capital_recomendado_total
        cob = self.cobertura
        if cob >= 1.0:
            alertas.append(Alerta(
                "info", "capital_suficiente",
                f"capital em conta R$ {self.capital_em_conta:.2f} cobre o "
                f"recomendado R$ {rec:.2f} para {len(self.exigencias)} EA(s)"))
        else:
            falta = rec - self.capital_em_conta
            nivel = "critico" if cob < 0.5 else "atencao"
            alertas.append(Alerta(
                nivel, "capital_abaixo_do_recomendado",
                f"capital em conta R$ {self.capital_em_conta:.2f} e' "
                f"{cob:.0%} do recomendado R$ {rec:.2f} para "
                f"{len(self.exigencias)} EA(s) -- faltam R$ {falta:.2f}. "
                "NAO estou impedindo nada (decisao e risco do operador, "
                "incluindo zeragem por falta de margem); so' avisando."))

        dup = self.subcontas_duplicadas()
        for sub, nomes in dup.items():
            alertas.append(Alerta(
                "atencao", "subconta_compartilhada",
                f"subconta {sub!r} usada por {len(nomes)} EAs ({', '.join(sorted(nomes))}) "
                "-- posicoes opostas se NETAM nessa subconta, que e' "
                "exatamente o que subcontas separadas evitam (ver "
                "EA_ARQUITETURA 4.2)"))

        sem_sub = sorted(e.nome for e in self.exigencias.values() if not e.subconta)
        if len(self.exigencias) > 1 and sem_sub:
            alertas.append(Alerta(
                "atencao", "ea_sem_subconta",
                f"{len(sem_sub)} EA(s) sem subconta declarada ({', '.join(sem_sub)}) "
                "com multi-EA ativo -- vao operar na conta principal e netar "
                "entre si"))
        return alertas

    def resumo(self) -> dict[str, object]:
        """Para logar de uma vez so'. Numeros, nao decisao."""
        return {
            "eas": len(self.exigencias),
            "capital_em_conta": round(self.capital_em_conta, 2),
            "capital_recomendado_total": round(self.capital_recomendado_total, 2),
            "cobertura_pct": (None if self.cobertura == float("inf")
                             else round(100 * self.cobertura, 1)),
            "contratos_totais": self.contratos_totais,
            "por_ea": {
                e.nome: {"capital_recomendado": round(e.capital_recomendado, 2),
                        "contratos": e.contratos, "ticker": e.ticker,
                        "subconta": e.subconta}
                for e in sorted(self.exigencias.values(), key=lambda x: x.nome)
            },
        }

    def logar(self) -> list[Alerta]:
        """Conveniencia: avalia, loga cada alerta no nivel certo, devolve
        os alertas para quem quiser inspecionar (testes, CLI)."""
        alertas = self.avaliar()
        log.info("ea.supervisor.resumo", **self.resumo())
        for a in alertas:
            fn = {"info": log.info, "atencao": log.warning}.get(a.nivel, log.error)
            fn(f"ea.supervisor.{a.codigo}", mensagem=a.mensagem, nivel=a.nivel)
        return alertas


def capital_recomendado_para(stop_catastrofico_pontos: float, contratos: int,
                            valor_ponto_reais: float, risco_max_pct: float) -> float:
    """
    Inverso da formula do `GestorDeRisco.stop_catastrofico_pontos`:
    la', stop = capital * risco_max_pct / valor_ponto. Aqui, dado o stop
    que a estrategia REALMENTE usa e quantos contratos, qual capital
    tornaria esse risco igual ao maximo aceito.

    Ex.: stop de 500 pts, 1 contrato de WIN (R$0,20/pt), risco max 2%
    -> 500 * 1 * 0,20 / 0,02 = R$ 5.000 (bate com o default do projeto).
    """
    if risco_max_pct <= 0:
        raise ValueError("risco_max_pct precisa ser positivo")
    if contratos <= 0:
        raise ValueError("contratos precisa ser positivo")
    risco_reais = stop_catastrofico_pontos * contratos * valor_ponto_reais
    return risco_reais / risco_max_pct
