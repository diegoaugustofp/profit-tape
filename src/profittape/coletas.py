"""Coletas de dado em curso para hipoteses sem ficha (v4.22).

Uma coleta tem prazo e nao tem operacao: o diario nao a ve (ele le EAs) e a ficha nao a cobre
(ela e' de estrategia). Sem registro, ela some dos resumos -- foi o que aconteceu com as duas
series do WDO e com as opcoes de outubro. Fonte unica: `docs/coletas.yaml`."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml


def carregar_coletas(caminho: Path) -> list[dict[str, Any]]:
    if not caminho.exists():
        return []
    return list((yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}).get("coletas") or [])


def _data(v: Any) -> dt.date | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def situacao(c: dict[str, Any], hoje: dt.date) -> dict[str, Any]:
    """Onde a coleta esta' no calendario. `fase`: antes (nao comecou), durante (ha' fim e ele nao
    chegou), marco_passou (virada/vencimento ja' ocorreu), sem_prazo."""
    desde, fim = _data(c.get("desde")), _data(c.get("fim"))
    marco = _data((c.get("marco") or {}).get("data"))
    out: dict[str, Any] = {"desde": desde, "fim": fim, "marco": marco,
                           "dias_desde_inicio": (hoje - desde).days if desde else None}
    if desde is None:
        out["fase"] = "nao_iniciada"
    elif fim and hoje < fim:
        out["fase"] = "durante"
        out["dias_ate_fim"] = (fim - hoje).days
    elif marco and hoje > marco:
        out["fase"] = "marco_passou"
        out["dias_desde_marco"] = (hoje - marco).days
    elif marco and hoje <= marco:
        out["fase"] = "durante"
        out["dias_ate_marco"] = (marco - hoje).days
    else:
        out["fase"] = "sem_prazo"
    return out


def frase_de_situacao(s: dict[str, Any]) -> str:
    f = s["fase"]
    if f == "nao_iniciada":
        return "ainda nao iniciada"
    if f == "durante" and "dias_ate_fim" in s:
        return (f"em curso desde {s['desde']:%d/%m}; faltam {s['dias_ate_fim']} dias corridos "
                "para o fim")
    if f == "durante" and "dias_ate_marco" in s:
        return f"em curso desde {s['desde']:%d/%m}; o marco e' em {s['dias_ate_marco']} dias"
    if f == "marco_passou":
        return f"o marco passou ha' {s['dias_desde_marco']} dias: ha' dado para rodar"
    return "em curso, sem prazo"
