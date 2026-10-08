"""Resumo do `LogDesktop_AAAA_MM_DD.log` do Profit por automacao (RobotID).

Uso:  python tools/analisa_log_profit.py LogDesktop_2026_10_07.log

Mostra, por RobotID: linhas de console por hora, fracao de `Fechou = 1` nas linhas
NT123/NTSV (a coluna 4 depois do prefixo), quedas de conexao (Servidor
desconectado -> conectado) e lacunas sem console. Feito sobre o caso de 07/10:
queda 12:12:46-19:45:53 e so' 2 de 13 fechamentos vistos (caixa desmarcada).
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_CONSOLE = re.compile(
    r"RobotID=(?P<rid>\d+) Time=(?P<dia>\S+) (?P<hora>[\d:.]+) "
    r"Event=Evento Personalizado \(ConsoleLog\) Message=(?P<msg>.*?) LogDev="
)
_CONEXAO = re.compile(
    r"RobotID=(?P<rid>\d+) Time=(?P<dia>\S+) (?P<hora>[\d:.]+) "
    r"Event=Aviso de Conex.o Message=Servidor (?P<est>des)?conectado"
)
GAP_SEG = 120.0


def _seg(hora: str) -> float:
    h, m, s = hora.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _fechou(msg: str) -> str | None:
    """`NT123|data|hora|CurrentTime|Fechou|...` e `NTSV|...` (mesma posicao)."""
    p = msg.split("|")
    if len(p) > 4 and p[0] in ("NT123", "NTSV") and p[1][:1].isdigit():
        return p[4].split(",")[0]
    return None


def analisar(linhas: list[str]) -> dict[str, dict[str, object]]:
    por: dict[str, dict[str, object]] = defaultdict(
        lambda: {"horas": Counter(), "fechou": Counter(), "quedas": [],
                 "lacunas": [], "_ult": None, "_desc": None}
    )
    for ln in linhas:
        m = _CONSOLE.search(ln)
        if m:
            r = por[m["rid"]]
            seg = _seg(m["hora"])
            r["horas"][m["hora"][:2]] += 1  # type: ignore[index]
            f = _fechou(m["msg"])
            if f is not None:
                r["fechou"][f] += 1  # type: ignore[index]
            ult = r["_ult"]
            if isinstance(ult, float) and seg - ult > GAP_SEG:
                r["lacunas"].append((ult, seg))  # type: ignore[attr-defined]
            r["_ult"] = seg
            continue
        c = _CONEXAO.search(ln)
        if c:
            r = por[c["rid"]]
            seg = _seg(c["hora"])
            if c["est"]:
                r["_desc"] = seg
            elif isinstance(r["_desc"], float):
                r["quedas"].append((r["_desc"], seg))  # type: ignore[attr-defined]
                r["_desc"] = None
    return por


def _hms(seg: float) -> str:
    return f"{int(seg // 3600):02d}:{int(seg % 3600 // 60):02d}:{int(seg % 60):02d}"


def main(caminho: str) -> None:
    linhas = Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines()
    for rid, r in sorted(analisar(linhas).items()):
        print(f"RobotID {rid}")
        print("  console por hora:", dict(sorted(r["horas"].items())))  # type: ignore[attr-defined]
        fe = r["fechou"]
        tot = sum(fe.values())  # type: ignore[attr-defined]
        if tot:
            print(f"  Fechou=1: {fe.get('1', 0)} de {tot} linhas")  # type: ignore[attr-defined]
        for a, b in r["quedas"]:  # type: ignore[attr-defined]
            print(f"  QUEDA de conexao {_hms(a)} -> {_hms(b)}")
        for a, b in r["lacunas"]:  # type: ignore[attr-defined]
            print(f"  LACUNA sem console {_hms(a)} -> {_hms(b)}")


if __name__ == "__main__":
    main(sys.argv[1])
