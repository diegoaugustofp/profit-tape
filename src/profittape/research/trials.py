"""
Contador de trials PERSISTIDO + limiar deflacionado.

Cada (feature x horizonte) avaliado e' um trial, somado ao historico em disco
entre rodadas. O limiar de significancia e' deflacionado pelo numero TOTAL de
trials ja gastos (teorema da falsa estrategia, Bailey & Lopez de Prado):

    E[max Z de N trials de ruido] ~= (1-g)*Phi^-1(1-1/N) + g*Phi^-1(1-1/(N*e))
    g = 0.5772 (Euler-Mascheroni)

Um t-stat que nao supera o maximo ESPERADO de N ruidos nao e' evidencia — e'
o que ruido produz quando se tenta N vezes. Sem persistencia, o contador
zeraria a cada rodada e o pesquisador se enganaria honestamente.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

_GAMMA = 0.5772156649


def _phi_inv(p: float) -> float:
    """Inversa da normal padrao (Acklam) — evita dependencia de scipy."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def limiar_deflacionado(n_trials: int) -> float:
    """
    Barra que um t-stat deve superar: max(1.96, E[max Z de n_trials ruidos]).

    O piso de 1.96 e' essencial: para N pequeno, E[max Z] fica ABAIXO da
    significancia convencional (N=2 -> ~0.56) e usar a formula pura DILUIRIA
    o criterio em vez de deflaciona-lo. Bug real pego pelo teste de
    honestidade (ruido puro saiu 'segue' na primeira implementacao):
    deflacao so' pode SUBIR a barra, nunca baixa-la.
    """
    if n_trials <= 1:
        return 1.96
    esperado_max = (1 - _GAMMA) * _phi_inv(1 - 1 / n_trials) + \
        _GAMMA * _phi_inv(1 - 1 / (n_trials * math.e))
    return max(1.96, esperado_max)


def t_critico(z: float, graus_liberdade: int) -> float:
    """
    Converte um limiar Z para o t-critico equivalente com poucos graus de
    liberdade (expansao de Cornish-Fisher, 2a ordem). Segundo furo pego pelo
    teste de honestidade: um t-stat de 5 folds tem cauda de Student (4 g.l.,
    t_95 = 2.78), e compara-lo contra limiar de Z (1.96) deixa ruido passar
    com ~12% de chance em vez de 5%. A barra deve viver na distribuicao do
    estatistico que ela julga.
    """
    df = max(1, graus_liberdade)
    z3, z5 = z ** 3, z ** 5
    return z + (z3 + z) / (4 * df) + (5 * z5 + 16 * z3 + 3 * z) / (96 * df * df)


class RegistroTrials:
    """Historico de trials em JSON. Soma entre rodadas; nunca esquece."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        if caminho.exists():
            self._dados = json.loads(caminho.read_text(encoding="utf-8"))
        else:
            self._dados = {"total_trials": 0, "rodadas": []}

    @property
    def total(self) -> int:
        return int(self._dados["total_trials"])

    def registrar_rodada(self, n_trials: int, detalhe: dict[str, Any]) -> int:
        """Soma os trials desta rodada e persiste. Devolve o total acumulado."""
        self._dados["total_trials"] += n_trials
        self._dados["rodadas"].append(
            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "n_trials": n_trials, **detalhe}
        )
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps(self._dados, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.total
