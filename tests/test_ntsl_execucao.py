"""
Guarda ESTATICA dos .ntsl de EXECUCAO: vwapvp_continuacao, ignicao,
ea_123_vb (v4.33) e z_agf_win (v4.34).

NAO prova que compilam nem que operam -- nao existe interpretador NTSL fora
do Profit. Pega so' os defeitos que a skill de engenharia (3.1) ja' custou
caro: Abs(), acesso posicional dentro de condicao, Integer concatenado no
ConsoleLog, begin/end desbalanceado, e a trava mais importante deste porte:
nenhum arquivo manda ordem sem declarar que e' so' SIMULADOR.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

NTSL = Path(__file__).resolve().parents[1] / "ntsl"
ARQUIVOS = ["vwapvp_continuacao.ntsl", "ignicao.ntsl", "ea_123_vb.ntsl",
            "z_agf_win.ntsl"]


def _codigo(nome: str) -> list[str]:
    """Linhas sem comentario `//` (nao ha' `//` dentro de string nestes arquivos)."""
    linhas = (NTSL / nome).read_text(encoding="utf-8").splitlines()
    return [ln.split("//", 1)[0] for ln in linhas]


def _inteiros(nome: str) -> set[str]:
    achados: set[str] = set()
    for ln in _codigo(nome):
        m = re.match(r"\s*([\w,\s]+?)\s*:\s*Integer\s*;", ln, re.IGNORECASE)
        if m:
            achados.update(v.strip() for v in m.group(1).split(","))
    return achados


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_abs(nome: str) -> None:
    assert not any(re.search(r"\bAbs\s*\(", ln, re.IGNORECASE) for ln in _codigo(nome))


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_begin_end_balanceados(nome: str) -> None:
    texto = "\n".join(_codigo(nome))
    abre = len(re.findall(r"\bbegin\b", texto, re.IGNORECASE))
    fecha = len(re.findall(r"\bend\b", texto, re.IGNORECASE))
    assert abre == fecha, f"{nome}: {abre} begin x {fecha} end"


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_acesso_posicional_em_condicao(nome: str) -> None:
    """`if x[1] > 0 then` e' comportamento indefinido (skill 3.1). Vale para
    as linhas de condicao: if / else if / while / until."""
    ruins = [ln.strip() for ln in _codigo(nome)
             if re.match(r"\s*(else\s+)?(if|while|until)\b", ln, re.IGNORECASE)
             and re.search(r"\w\s*\[", ln)]
    assert not ruins, ruins


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_integer_nao_entra_no_consolelog(nome: str) -> None:
    inteiros = _inteiros(nome)
    # junta cada ConsoleLog (pode ocupar varias linhas ate' o `;`)
    texto = "\n".join(_codigo(nome))
    for chamada in re.findall(r"ConsoleLog\((.*?)\);", texto, re.DOTALL | re.IGNORECASE):
        sem_string = re.sub(r'"[^"]*"', "", chamada)
        usados = set(re.findall(r"[A-Za-z_]\w*", sem_string))
        assert not (usados & inteiros), f"{nome}: Integer no ConsoleLog: {usados & inteiros}"


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_declara_que_e_so_simulador_e_nao_compilado(nome: str) -> None:
    texto = (NTSL / nome).read_text(encoding="utf-8")
    assert "SIMULADOR" in "\n".join(texto.splitlines()[:60])
    assert "NAO COMPILEI" in texto


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_toda_variavel_do_consolelog_esta_declarada(nome: str) -> None:
    """O compilador do Profit recusa identificador nao declarado, e erro de
    compilacao so' aparece com o mercado aberto. Confere o que da' para
    conferir de fora: nomes `s*`/`b*`/`n*` usados no arquivo existem em
    `input` ou `var`."""
    texto = "\n".join(_codigo(nome))
    m_in = re.search(r"\binput\b(.*?)\bvar\b", texto, re.DOTALL | re.IGNORECASE)
    m_var = re.search(r"\bvar\b(.*?)\bbegin\b", texto, re.DOTALL | re.IGNORECASE)
    assert m_in and m_var
    declarados = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", m_in.group(1)))
    for bloco in m_var.group(1).split(";"):
        if ":" in bloco:
            declarados.update(v.strip() for v in bloco.split(":", 1)[0].split(","))
    corpo = texto[m_var.end():]
    corpo = re.sub(r'"[^"]*"', '""', corpo)
    usados = set(re.findall(r"\b([sbn][A-Z]\w*|vals)\b", corpo))
    faltam = sorted(usados - declarados)
    assert not faltam, f"{nome}: nao declaradas: {faltam}"


def test_ordens_so_com_quantidade_explicita() -> None:
    """Todo envio de ordem leva `Lote` (o valor que o operador configurou no
    input), nunca depende do default da automacao."""
    padrao = re.compile(
        r"\b(BuyAtMarket|SellShortAtMarket|BuyStop|SellShortStop|SellToCoverStop|"
        r"SellToCoverLimit|BuyToCoverStop|BuyToCoverLimit)\b\s*(\(([^;]*)\))?", re.IGNORECASE)
    for nome in ARQUIVOS:
        texto = "\n".join(_codigo(nome))
        for m in padrao.finditer(texto):
            assert m.group(3) and "Lote" in m.group(3), f"{nome}: {m.group(0)!r} sem Lote"


# ---------------------------------------------------------------- z_agf_win
ORDENS_DE_ENTRADA = re.compile(r"\b(BuyAtMarket|SellShortAtMarket)\b", re.IGNORECASE)


def _entradas_sem_guarda(linhas: list[str]) -> list[str]:
    """Linhas que enviam ordem de ENTRADA sem `ModoConferir = 0` nas 6 linhas
    anteriores. E' o que garante que o modo conferencia nunca opera."""
    ruins = []
    for i, ln in enumerate(linhas):
        if ORDENS_DE_ENTRADA.search(ln):
            janela = linhas[max(0, i - 6):i + 1]
            if not any(re.search(r"ModoConferir\s*=\s*0", w) for w in janela):
                ruins.append(ln.strip())
    return ruins


def test_z_agf_win_sai_em_modo_conferir() -> None:
    codigo = "\n".join(_codigo("z_agf_win.ntsl"))
    assert re.search(r"\bModoConferir\s*\(\s*1\s*\)", codigo), "default tem que ser 1"


def test_z_agf_win_toda_entrada_esta_guardada() -> None:
    assert _entradas_sem_guarda(_codigo("z_agf_win.ntsl")) == []


def test_verificador_de_guarda_reprova_o_caso_ruim() -> None:
    """Skill disciplina 7.3: verificador novo roda contra o que DEVE pegar."""
    ruim = ["begin", "  if sArma = 1 then", "    BuyAtMarket(Lote);", "end;"]
    bom = ["begin", "  if ModoConferir = 0 then", "  begin", "    BuyAtMarket(Lote);",
           "  end;", "end;"]
    assert _entradas_sem_guarda(ruim) == ["BuyAtMarket(Lote);"]
    assert _entradas_sem_guarda(bom) == []


def _z_recursivo(xs: list[float], n: int, min_p: int) -> list[float]:
    """Espelho EXATO da aritmetica de z_agf_win.ntsl: soma e soma de quadrados
    recursivas, estatistica ate' a barra anterior, NaN = barra invalida."""
    soma = quad = cnt = 0.0
    hist: list[tuple[float, float]] = []   # (agf, ok) por barra
    saida: list[float] = []
    for i, x in enumerate(xs):
        ok = 0.0 if x != x else 1.0
        agf = 0.0 if x != x else x
        velho_agf, velho_ok = hist[i - n] if i >= n else (0.0, 0.0)
        z = float("nan")
        if ok == 1.0 and cnt >= min_p:
            media = soma / cnt
            var = (quad - cnt * media * media) / (cnt - 1)
            if var > 1e-10:
                z = (agf - media) / var ** 0.5
        soma = soma + ok * agf - velho_ok * velho_agf
        quad = quad + ok * agf * agf - velho_ok * velho_agf * velho_agf
        cnt = cnt + ok - velho_ok
        hist.append((agf, ok))
        saida.append(z)
    return saida


def test_z_recursivo_na_mao() -> None:
    """Conta a mao: janela [1,2,3] (media 2, desvio n-1 = 1); x=4 -> z = 2."""
    z = _z_recursivo([1.0, 2.0, 3.0, 4.0], n=3, min_p=2)
    assert z[3] == pytest.approx(2.0)
    assert z[0] != z[0] and z[1] != z[1]   # aquecimento: NaN


def test_z_recursivo_igual_ao_zscore_rolante_do_research() -> None:
    import numpy as np
    import pandas as pd

    from profittape.features.normalize import zscore_rolante

    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 0.05, 400)
    x[rng.random(400) < 0.1] = np.nan          # barras invalidas
    esperado = zscore_rolante(pd.Series(x), 50).to_numpy()
    obtido = np.array(_z_recursivo(list(x), 50, 25))
    ambos = ~np.isnan(esperado) & ~np.isnan(obtido)
    assert ambos.sum() > 250
    assert np.array_equal(np.isnan(esperado), np.isnan(obtido))
    assert np.max(np.abs(esperado[ambos] - obtido[ambos])) < 1e-8


def test_ignicao_detecta_antes_do_bloco_de_posicao() -> None:
    """v4.35: o reprocessamento da barra de entrada precisa reconhecer o
    proprio sinal, entao a deteccao (sLado) tem que estar calculada ANTES de
    `if HasPosition`, e o ramo de reconstrucao precisa existir antes do ORFA."""
    codigo = "\n".join(_codigo("ignicao.ntsl"))
    assert codigo.index("sLado := 1;") < codigo.index("if HasPosition then")
    recons = codigo.index("sEvento   := 11;")
    orfa = codigo.index('ConsoleLog("NTSI|ORFA|"')
    assert recons < orfa
    assert "NTSD|" in codigo


def test_vwapvp_reconhece_o_proprio_sinal_antes_do_bloco_de_posicao() -> None:
    """v4.36: mesmo reprocessamento da barra de entrada do ignicao. O sinal
    (sArma) tem que estar calculado ANTES de `if HasPosition`, e o ramo de
    reconstrucao (evento 11) tem que vir antes do ORFA."""
    codigo = "\n".join(_codigo("vwapvp_continuacao.ntsl"))
    assert codigo.index("sArma := 1;") < codigo.index("if HasPosition then")
    assert codigo.index("sEvento  := 11;") < codigo.index('ConsoleLog("NTSV|ORFA|"')


def test_123_nao_tem_o_defeito_do_reprocessamento_do_mesmo_candle() -> None:
    """HISTORICO: a premissa era "entrada STOP enche em t+1 com estado gravado
    em t". FALSA (v4.40: 10 ORFA no backtest). Fica so' o fato estrutural: a
    entrada continua sendo ordem STOP, nao a mercado. O conserto tem os testes
    `test_123_sinal_puro_...` abaixo."""
    codigo = "\n".join(_codigo("ea_123_vb.ntsl"))
    assert "BuyStop(" in codigo and "BuyAtMarket" not in codigo


# --------------------------------------------------------------------------
# v4.38: alarme ALVO_CRUZADO (so' diagnostico). Achado de 06/10: na 1a
# passada do backtest o ToCover existe (Pend=1), o preco cruza o alvo e nao
# ha' fill; nas passadas finais nunca. O alarme torna isso visivel ao vivo.
# --------------------------------------------------------------------------
ALARMADOS = ["ignicao.ntsl", "vwapvp_continuacao.ntsl"]


def _bloco_alarme(nome: str) -> list[str]:
    linhas = _codigo(nome)
    ini = next(i for i, ln in enumerate(linhas) if "AlarmeCruzado = 1" in ln)
    fim = next(i for i in range(ini, len(linhas)) if "ConsoleLog" in linhas[i])
    while ";" not in linhas[fim]:
        fim += 1
    return linhas[ini : fim + 1]


def _alarme_py(lado: float, alvo: float, stop: float, hi: float, lo: float,
               bars_pos: float, tem_pos: bool = True) -> bool:
    """Espelho da condicao do .ntsl."""
    if not (tem_pos and bars_pos >= 1 and alvo > 0):
        return False
    if lado > 0:
        return hi >= alvo or lo <= stop
    if lado < 0:
        return lo <= alvo or hi >= stop
    return False


@pytest.mark.parametrize("nome", ALARMADOS)
def test_alarme_existe_default_ligado_e_so_na_barra_posterior_a_entrada(nome: str) -> None:
    texto = "\n".join(_codigo(nome))
    assert re.search(r"AlarmeCruzado\(1\)", texto)
    bloco = "\n".join(_bloco_alarme(nome))
    assert "sBarsPos >= 1" in bloco and "HasPosition" in bloco


@pytest.mark.parametrize("nome", ALARMADOS)
def test_alarme_nao_altera_estado_nem_envia_ordem(nome: str) -> None:
    bloco = "\n".join(_bloco_alarme(nome))
    atribuicoes = re.findall(r"(\w+)\s*:=", bloco)
    assert set(atribuicoes) <= {"sBar"}, atribuicoes
    for ordem in ("BuyAtMarket", "SellShortAtMarket", "ClosePosition", "ToCover"):
        assert ordem not in bloco


@pytest.mark.parametrize("nome", ALARMADOS)
def test_alarme_usa_float_no_consolelog_e_nao_depende_de_lastbaronchart(nome: str) -> None:
    bloco = "\n".join(_bloco_alarme(nome))
    log = bloco[bloco.index("ConsoleLog"):]
    assert "CurrentBar" not in log and "sBar" in log
    assert "LastBarOnChart" not in bloco


def test_alarme_comportamento_na_mao() -> None:
    # compra, alvo 100, stop 90: barra posterior com High 101 cruza o alvo
    assert _alarme_py(1, 100, 90, 101, 95, 1)
    # venda, alvo 100, stop 110: Low 99 cruza o alvo; High 111 cruza o stop
    assert _alarme_py(-1, 100, 110, 105, 99, 2)
    assert _alarme_py(-1, 100, 110, 111, 105, 2)
    # sem cruzar: nada
    assert not _alarme_py(1, 100, 90, 99, 91, 3)
    # barra de entrada (BarsPos 0): faixa inclui o pre-fill, nao alarma
    assert not _alarme_py(1, 100, 90, 101, 95, 0)
    # sem posicao: nada (fill normal do ToCover)
    assert not _alarme_py(1, 100, 90, 101, 95, 1, tem_pos=False)


# --------------------------------------------------------------------------
# v4.39: diagnostico do 123 (NT123D e NT123|DIA). Backtest 30/09-06/10 deu
# 0 operacoes e o unico log era o do ultimo candle (GateN = 0, Med = 0).
# --------------------------------------------------------------------------
def test_123_diagnostico_nao_depende_de_lastbaronchart_e_nao_altera_nada() -> None:
    linhas = _codigo("ea_123_vb.ntsl")
    texto = "\n".join(linhas)
    assert re.search(r"LogDiag\(1\)", texto)
    i = next(k for k, ln in enumerate(linhas) if "ConsoleLog(\"NT123D|\"" in ln)
    janela = "\n".join(linhas[max(0, i - 4) : i + 6])
    assert "LastBarOnChart" not in janela
    for ordem in ("BuyStop", "SellShortStop", "ClosePosition", "CancelPendingOrders"):
        assert ordem not in janela
    j = next(k for k, ln in enumerate(linhas) if "NT123|DIA|" in ln)
    assert "LastBarOnChart" not in "\n".join(linhas[max(0, j - 2) : j + 1])


def test_123_contador_de_barras_do_dia_e_recursivo_e_le_posicional_no_topo() -> None:
    texto = "\n".join(_codigo("ea_123_vb.ntsl"))
    assert "sBarDia   := sBarDia[1];" in texto
    assert "sBarDia := sBarDia + 1" in texto


# --------------------------------------------------------------------------
# v4.40: o 123 TEM o defeito do reprocessamento (backtest 30/09-06/10 com
# BarrasPorDia 38: 23 armadas, 10 eventos ORFA em 5 trades). Mesmo conserto do
# ignicao/vwapvp: sinal puro antes do bloco de posicao + reconstrucao sem ordem.
# --------------------------------------------------------------------------
def test_123_sinal_puro_antes_do_bloco_de_posicao_e_reconstrucao_antes_do_orfa() -> None:
    linhas = _codigo("ea_123_vb.ntsl")
    i_sinal = next(k for k, ln in enumerate(linhas) if "bSinal := False" in ln)
    i_pos = next(k for k, ln in enumerate(linhas) if re.match(r"\s*if HasPosition then", ln))
    assert i_sinal < i_pos
    i_recons = next(k for k, ln in enumerate(linhas) if "sEvento  := 11" in ln)
    i_orfa = next(k for k, ln in enumerate(linhas) if "NT123|ORFA|" in ln)
    assert i_pos < i_recons < i_orfa


def test_123_o_sinal_puro_nao_envia_ordem_e_a_reconstrucao_nao_manda_nova_entrada() -> None:
    linhas = _codigo("ea_123_vb.ntsl")
    i_sinal = next(k for k, ln in enumerate(linhas) if "bSinal := False" in ln)
    i_pos = next(k for k, ln in enumerate(linhas) if re.match(r"\s*if HasPosition then", ln))
    bloco_sinal = "\n".join(linhas[i_sinal:i_pos])
    for ordem in ("BuyStop", "SellShortStop", "ClosePosition", "ToCover", "CancelPendingOrders"):
        assert ordem not in bloco_sinal
    i_recons = next(k for k, ln in enumerate(linhas) if "sEvento  := 11" in ln)
    janela = "\n".join(linhas[i_recons - 10 : i_recons + 2])
    assert "BuyStop" not in janela and "SellShortStop" not in janela


def test_123_barras_por_dia_default_e_o_medido_38() -> None:
    assert re.search(r"BarrasPorDia\(38\)", "\n".join(_codigo("ea_123_vb.ntsl")))


# --------------------------------------------------------------------------
# v4.41: alarme ALVO_CRUZADO no 123 (so' diagnostico). O fill da entrada e' em
# t+1 do arme; so' candles POSTERIORES ao do fill contam (a faixa do candle do
# fill inclui o pre-fill).
# --------------------------------------------------------------------------
def _alarme_123_py(lado: float, alvo: float, stop: float, hi: float, lo: float,
                   bar: int, arm_bar: int, evento: int = 0, tem_pos: bool = True) -> bool:
    """Espelho da condicao do .ntsl."""
    if not (tem_pos and evento != 11 and stop > 0 and alvo > 0 and bar >= arm_bar + 2):
        return False
    if lado > 0:
        return hi >= alvo or lo <= stop
    if lado < 0:
        return lo <= alvo or hi >= stop
    return False


def test_123_alarme_existe_default_ligado_e_so_apos_o_candle_do_fill() -> None:
    codigo = "\n".join(_codigo("ea_123_vb.ntsl"))
    assert re.search(r"AlarmeCruzado\(1\)", codigo)
    linhas = _codigo("ea_123_vb.ntsl")
    ini = next(k for k, ln in enumerate(linhas) if "AlarmeCruzado = 1" in ln)
    bloco = "\n".join(linhas[ini : ini + 16])
    assert "CurrentBar >= sArmBar + 2" in bloco and "HasPosition" in bloco
    atribs = set(re.findall(r"(\w+)\s*:=", bloco.split("ConsoleLog")[0]))
    assert atribs <= {"sBar", "sTmp"}, atribs
    for ordem in ("BuyStop", "SellShortStop", "ClosePosition", "ToCover", "CancelPendingOrders"):
        assert ordem not in bloco
    assert "LastBarOnChart" not in bloco


def test_123_alarme_comportamento_na_mao() -> None:
    # compra, alvo 100, stop 90, arme na barra 10 (fill na 11): so' >= 12 conta
    assert _alarme_123_py(1, 100, 90, 101, 95, 12, 10)
    assert not _alarme_123_py(1, 100, 90, 101, 95, 11, 10)  # candle do fill
    assert _alarme_123_py(1, 100, 90, 99, 89, 12, 10)       # stop cruzado
    assert not _alarme_123_py(1, 100, 90, 99, 91, 13, 10)   # sem cruzar
    assert _alarme_123_py(-1, 90, 100, 96, 89, 12, 10)      # venda, alvo (Low cruza)
    assert not _alarme_123_py(1, 100, 90, 101, 95, 12, 10, evento=11)
    assert not _alarme_123_py(1, 100, 90, 101, 95, 12, 10, tem_pos=False)


# --------------------------------------------------------------------------
# v4.42: NIVEIS VELHOS (achado de 07/10, simulador). No ignicao, a entrada das
# 10:02:40 saiu com o alvo/stop da operacao anterior (fechada 4 s antes): o
# candle anterior foi avaliado com a posicao aberta e guardou os niveis dela;
# o reprocessamento do candle de entrada leu isso em [1]; a reconstrucao so'
# roda com niveis ZERADOS, entao nao rodou; alvo velho abaixo do preco = saida
# a mercado em 0,13 s (-5 pts). Conserto: com posicao e DailyResult diferente
# do registrado no candle anterior, descartar os niveis de [1].
# --------------------------------------------------------------------------
DESCARTAM = ["ignicao.ntsl", "vwapvp_continuacao.ntsl", "ea_123_vb.ntsl"]
_ESTADO = {"sDescarte", "sLadoPos", "sNivel", "sAlvoPx", "sStopPx", "sBarsPos",
           "sNivEnt", "sNivStop", "sNivAlvo"}
_ORDENS = ("BuyAtMarket", "SellShortAtMarket", "BuyStop", "SellShortStop",
           "ClosePosition", "ToCover", "CancelPendingOrders")


def _i_posicao(linhas: list[str]) -> int:
    return next(k for k, ln in enumerate(linhas) if re.match(r"\s*if HasPosition then", ln))


def _bloco_descarte(nome: str) -> tuple[int, list[str]]:
    linhas = _codigo(nome)
    i = next(k for k, ln in enumerate(linhas) if "sDescarte := 1" in ln)
    return i, linhas[i : i + 2]


@pytest.mark.parametrize("nome", DESCARTAM)
def test_descarte_de_niveis_velhos_vem_antes_do_bloco_de_posicao(nome: str) -> None:
    linhas = _codigo(nome)
    i, _ = _bloco_descarte(nome)
    assert i < _i_posicao(linhas)


@pytest.mark.parametrize("nome", DESCARTAM)
def test_descarte_so_vale_com_posicao_e_dailyresult_diferente(nome: str) -> None:
    linhas = _codigo(nome)
    i, _ = _bloco_descarte(nome)
    cond = "\n".join(linhas[max(0, i - 3) : i + 1])
    assert "HasPosition" in cond
    if nome == "vwapvp_continuacao.ntsl":
        # reaproveita o bFechouTrade (sDelta = DailyResult - registrado em [1])
        assert "bFechouTrade and HasPosition" in cond
        texto = "\n".join(linhas)
        assert "sDelta := sDailyRes - sDailyAnt" in texto
        assert "bFechouTrade := (sDelta > 0.001) or (sDelta < 0 - 0.001)" in texto
    else:
        assert "sDailyRes - sDailyAnt > 0.001" in cond
        assert "sDailyAnt - sDailyRes > 0.001" in cond   # perdedor tambem (sem Abs)
        assert "sDailyAnt := sDailyRes[1];" in "\n".join(linhas)


@pytest.mark.parametrize("nome", DESCARTAM)
def test_descarte_so_zera_estado_e_nao_manda_ordem(nome: str) -> None:
    _, bloco = _bloco_descarte(nome)
    texto = "\n".join(bloco)
    atribs = set(re.findall(r"(\w+)\s*:=", texto))
    assert atribs <= _ESTADO, atribs
    for ordem in _ORDENS:
        assert ordem not in texto
    # zera (nao rebaixa): todo nivel recebe 0
    for nivel in re.findall(r"(sAlvoPx|sStopPx|sNivAlvo|sNivStop)\s*:=\s*(\S+);", texto):
        assert nivel[1] == "0", nivel


@pytest.mark.parametrize("nome", DESCARTAM)
def test_descarte_aparece_na_ultima_coluna_do_diagnostico(nome: str) -> None:
    texto = "\n".join(_codigo(nome))
    marcador = {"ignicao.ntsl": "NTSD|", "vwapvp_continuacao.ntsl": "NTSVD|",
                "ea_123_vb.ntsl": "NT123D|"}[nome]
    chamada = re.search(r'ConsoleLog\("' + re.escape(marcador) + r'.*?\);', texto, re.DOTALL)
    assert chamada, marcador
    assert chamada.group(0).rstrip(");").endswith('"|" + sDescarte')


@pytest.mark.parametrize("nome", DESCARTAM)
def test_params_uma_vez_no_primeiro_candle_sem_lastbaronchart(nome: str) -> None:
    linhas = _codigo(nome)
    i = next(k for k, ln in enumerate(linhas) if "|PARAMS|" in ln)
    janela = "\n".join(linhas[max(0, i - 4) : i + 6])
    assert "CurrentBar = 1" in janela and "LogDiag = 1" in janela
    assert "LastBarOnChart" not in janela
    esperado = {"ignicao.ntsl": ("BarrasJanela", "RefratBarras"),
                "vwapvp_continuacao.ntsl": ("MinutosBarra", "GuardaRelogio"),
                "ea_123_vb.ntsl": ("BarrasPorDia", "GuardaRelogio")}[nome]
    for campo in esperado:
        assert campo in janela


def _precisa_reconstruir(lado: float, alvo: float, stop: float) -> bool:
    """Espelho da condicao do ramo ORFA/reconstrucao (niveis ausentes)."""
    return lado == 0 or alvo == 0 or stop == 0


def _niveis_lidos(velhos: tuple[float, float, float], daily_ant: float,
                  daily_agora: float, tem_pos: bool) -> tuple[tuple[float, float, float], int]:
    """Espelho do descarte da v4.42: (niveis que o bloco de posicao enxerga, descarte)."""
    if tem_pos and (daily_agora - daily_ant > 0.001 or daily_ant - daily_agora > 0.001):
        return (0.0, 0.0, 0.0), 1
    return velhos, 0


def test_a_reconstrucao_so_roda_com_nivel_zerado_premissa_do_defeito() -> None:
    for nome, esperado in (("ignicao.ntsl", "(sLadoPos = 0) or (sAlvoPx = 0) or (sStopPx = 0)"),
                           ("vwapvp_continuacao.ntsl",
                            "(sLadoPos = 0) or (sAlvoPx = 0) or (sStopPx = 0)"),
                           ("ea_123_vb.ntsl",
                            "(sLadoPos = 0) or (sNivStop = 0) or (sNivAlvo = 0)")):
        assert esperado in "\n".join(_codigo(nome))


def test_cenario_de_07_10_niveis_do_trade_1_nao_chegam_ao_trade_2() -> None:
    # trade 1 (long): alvo 206715, stop 205655; fechou com +124 R$ depois da
    # avaliacao do candle anterior (registrou 0). Trade 2 enche no candle seguinte.
    velhos = (1.0, 206715.0, 205655.0)
    # sem o descarte (v4.41): niveis nao zerados -> nao reconstroi -> ToCover errado
    assert not _precisa_reconstruir(*velhos)
    lidos, descarte = _niveis_lidos(velhos, daily_ant=0.0, daily_agora=124.0, tem_pos=True)
    assert descarte == 1 and _precisa_reconstruir(*lidos)


def test_descarte_nao_mexe_no_fluxo_normal() -> None:
    velhos = (1.0, 206715.0, 205655.0)
    # posicao aberta, nenhum trade fechou desde o candle anterior: niveis ficam
    assert _niveis_lidos(velhos, 124.0, 124.0, True) == (velhos, 0)
    # variacao abaixo da tolerancia (ruido de ponto flutuante): ficam
    assert _niveis_lidos(velhos, 124.0, 124.0004, True) == (velhos, 0)
    # sem posicao: o fluxo sem posicao ja' zera e cancela; o descarte nao entra
    assert _niveis_lidos(velhos, 0.0, 124.0, False) == (velhos, 0)
    # trade perdedor tambem fecha: descarta
    assert _niveis_lidos(velhos, 0.0, -102.0, True)[1] == 1


# --------------------------------------------------------------------------
# v4.43: batimento de fechamento (HB) e AVISO_MODO. SO' log.
# Ver docs/NTSL_PORTE_EAS.md "07/10: o buraco das 12:12 e a caixa desmarcada".
# --------------------------------------------------------------------------
HB_ARQUIVOS = {"ea_123_vb.ntsl": "NT123", "vwapvp_continuacao.ntsl": "NTSV"}


def _bloco_log(nome: str, marca: str) -> tuple[str, str]:
    """(condicao do `if`, corpo ate' o `end;`) do bloco que imprime `marca`."""
    linhas = _codigo(nome)
    j = next(k for k, ln in enumerate(linhas) if marca in ln)
    i = j
    while not re.match(r"\s*if ", linhas[i]):
        i -= 1
    k = j
    while not re.match(r"\s*end;", linhas[k]):
        k += 1
    cond = " ".join(linhas[i : next(m for m in range(i, j) if "begin" in linhas[m]) + 1])
    return cond, " ".join(linhas[i : k + 1])


@pytest.mark.parametrize("nome", HB_ARQUIVOS)
def test_hb_nao_depende_de_lastbaronchart_e_so_com_relogio(nome: str) -> None:
    cond, _ = _bloco_log(nome, f'"{HB_ARQUIVOS[nome]}|HB|"')
    assert "LastBarOnChart" not in cond
    assert "GuardaRelogio = 1" in cond and "bCompleta" in cond and "LogDiag = 1" in cond
    assert "CalcTime(sFimBarra, 3)" in cond          # janela de 3 min
    assert "sKey <> sHbKey" in cond                  # 1 linha por candle


@pytest.mark.parametrize("nome", HB_ARQUIVOS)
def test_aviso_modo_so_candle_incompleto_ao_vivo(nome: str) -> None:
    cond, _ = _bloco_log(nome, f'"{HB_ARQUIVOS[nome]}|AVISO_MODO|"')
    assert "LastBarOnChart" in cond and "not bCompleta" in cond
    assert "GuardaRelogio = 1" in cond and "sKey <> sAvKey" in cond


@pytest.mark.parametrize("nome", HB_ARQUIVOS)
def test_hb_e_aviso_so_logam_sem_ordem_e_sem_estado_de_decisao(nome: str) -> None:
    for marca in ("|HB|", "|AVISO_MODO|"):
        _, corpo = _bloco_log(nome, f'"{HB_ARQUIVOS[nome]}{marca}"')
        assert not any(o in corpo for o in _ORDENS)
        # unico estado escrito: a chave de deduplicacao
        escritos = set(re.findall(r"\b(s\w+)\s*:=", corpo))
        assert escritos <= {"sHbKey", "sAvKey"}


@pytest.mark.parametrize("nome", HB_ARQUIVOS)
def test_hb_leitura_posicional_no_topo_e_chave_declarada(nome: str) -> None:
    cod = "\n".join(_codigo(nome))
    assert re.search(r"sHbKey\s*:=\s*sHbKey\[1\];", cod)
    assert re.search(r"sAvKey\s*:=\s*sAvKey\[1\];", cod)
    assert re.search(r"sHbKey, sAvKey, sKey, sLast\s*:\s*Float;", cod)
    # nenhuma leitura posicional dentro dos blocos novos
    for marca in ("|HB|", "|AVISO_MODO|"):
        _, corpo = _bloco_log(nome, f'"{HB_ARQUIVOS[nome]}{marca}"')
        assert "[1]" not in corpo


def _hb_deve_imprimir(guarda: int, completa: bool, seg_apos_fim: float,
                      chave: float, chave_hb: float) -> bool:
    """Espelho Python da condicao do HB (janela de 3 min)."""
    return (guarda == 1 and completa and seg_apos_fim < 180 and chave != chave_hb)


def test_espelho_hb_um_por_candle_e_nada_no_backtest() -> None:
    assert _hb_deve_imprimir(1, True, 0.4, 1261007_0930, 0)           # fechamento
    assert not _hb_deve_imprimir(1, True, 0.4, 1261007_0930, 1261007_0930)  # reprocesso
    assert not _hb_deve_imprimir(0, True, 0.4, 1261007_0930, 0)       # backtest
    assert not _hb_deve_imprimir(1, False, 0.0, 1261007_0930, 0)      # incompleto
    assert not _hb_deve_imprimir(1, True, 600, 1261007_0930, 0)       # > 3 min depois
