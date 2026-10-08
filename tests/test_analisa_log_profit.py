"""`tools/analisa_log_profit.py` contra o caso real de 07/10 (verificador que
tem que PEGAR o defeito conhecido: queda de conexao e candles sem Fechou=1)."""

from __future__ import annotations

from tools.analisa_log_profit import analisar


def _con(rid: int, hora: str, msg: str) -> str:
    return (f"#31CC #AAAA 07/10 {hora} | {hora} : #Log#Language X: #Event: RobotID={rid} "
            f"Time=07/10/2026 {hora} Event=Evento Personalizado (ConsoleLog) "
            f"Message={msg} LogDev= (DEV)  ExpOrdBuy=0")


def _net(rid: int, hora: str, des: bool) -> str:
    est = "desconectado" if des else "conectado"
    return (f"#31CC #BBBB 07/10 {hora} | {hora} : #Log RobotID={rid} Time=07/10/2026 {hora} "
            f"Event=Aviso de Conexão Message=Servidor {est} LogDev=")


def test_pega_queda_lacuna_e_fechou() -> None:
    linhas = [
        _con(7, "12:12:25.000", "NT123|1.261.007,00|1.200,00|1212|0,00|1|2"),
        _con(7, "12:12:30.000", "NT123|1.261.007,00|1.200,00|1212|0,00|1|2"),
        _net(7, "12:12:46.390", True),
        _net(7, "19:45:57.000", False),
        _con(7, "19:46:15.806", "NT123|1.261.007,00|1.815,00|1946|1,00|1|2"),
        _con(7, "19:46:20.806", "NT123|1.261.007,00|1.815,00|1946|0,00|1|2"),
        _con(2, "12:12:30.000", "NTSV|1.261.007,00|1.200,00|1212|0,00|1"),
        _con(2, "12:12:31.000", "NTSV|HB|1.261.007,00|1.200,00|1212|1,00"),  # HB nao conta
    ]
    r = analisar(linhas)
    assert len(r["7"]["quedas"]) == 1                                  # type: ignore[arg-type]
    assert r["7"]["quedas"][0][0] == 12 * 3600 + 12 * 60 + 46.39      # type: ignore[index]
    assert len(r["7"]["lacunas"]) == 1                                 # type: ignore[arg-type]
    assert r["7"]["fechou"]["1"] == 1 and r["7"]["fechou"]["0"] == 3  # type: ignore[index]
    assert r["2"]["fechou"]["0"] == 1 and "1" not in r["2"]["fechou"]  # type: ignore[operator]


def test_sem_queda_sem_lacuna() -> None:
    msg = "NT123|1.261.007,00|1.000,00|1000|0,00"
    linhas = [_con(7, f"10:00:{s:02d}.000", msg) for s in (0, 5, 10)]
    r = analisar(linhas)
    assert r["7"]["quedas"] == [] and r["7"]["lacunas"] == []
