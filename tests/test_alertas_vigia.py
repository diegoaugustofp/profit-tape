"""
Testes de alertas.py e vigia.py — o watchdog externo que cobre o caso que o
record nao pode alertar sobre si mesmo (nunca ter iniciado, ou ter travado).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from profittape.alertas import ConfigAlertas, enviar
from profittape.logging_setup import configurar
from profittape.vigia import checar


def test_configuracao_ausente_e_no_op(tmp_path: Path) -> None:
    """Sem config/alertas.yaml, ConfigAlertas.carregar() = None, enviar()
    nao levanta e devolve False — record precisa rodar igual sem config."""
    cfg = ConfigAlertas.carregar(tmp_path / "nao_existe.yaml")
    assert cfg is None
    assert enviar("teste", cfg) is False


def test_configuracao_incompleta_e_no_op(tmp_path: Path) -> None:
    p = tmp_path / "alertas.yaml"
    p.write_text("telegram:\n  bot_token: \"\"\n", encoding="utf-8")
    assert ConfigAlertas.carregar(p) is None


def test_configuracao_completa_carrega(tmp_path: Path) -> None:
    p = tmp_path / "alertas.yaml"
    p.write_text('telegram:\n  bot_token: "123:ABC"\n  chat_id: "999"\n',
                encoding="utf-8")
    cfg = ConfigAlertas.carregar(p)
    assert cfg is not None
    assert cfg.bot_token == "123:ABC"
    assert cfg.chat_id == "999"


def _escrever_log_json(caminho: Path, eventos: list[dict]) -> None:
    """Grava linhas no MESMO formato real que logging_setup.configurar()
    produz — JSONRenderer, uma linha por evento, timestamp ISO UTC."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        for ev in eventos:
            f.write(json.dumps(ev) + "\n")


def test_vigia_detecta_nao_iniciou(tmp_path: Path) -> None:
    """Sem nenhum 'recorder.subscrito' de hoje, dentro do pregao -> alerta."""
    log_file = tmp_path / "log.jsonl"
    _escrever_log_json(log_file, [])  # log vazio: hoje ainda nao começou
    veredito = checar(
        log_file, tmp_path / "alertas.yaml", tmp_path / "estado.json",
        abertura_local="00:00", fechamento_local="23:59",
    )
    assert veredito == "nao_iniciou"


def test_vigia_ok_quando_tudo_normal(tmp_path: Path) -> None:
    log_file = tmp_path / "log.jsonl"
    hoje = datetime.now(UTC).strftime("%Y-%m-%dT")
    agora_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _escrever_log_json(log_file, [
        {"timestamp": hoje + "09:00:00.000000Z", "event": "recorder.subscrito",
         "ticker": "WINFUT"},
        {"timestamp": agora_iso, "event": "recorder.heartbeat", "linhas": 1000},
    ])
    veredito = checar(
        log_file, tmp_path / "alertas.yaml", tmp_path / "estado.json",
        abertura_local="00:00", fechamento_local="23:59", limite_parado_min=6.0,
    )
    assert veredito == "ok"


def test_vigia_detecta_travado(tmp_path: Path) -> None:
    """Iniciou, mas o ultimo heartbeat e' de ha' muito tempo -> travado."""
    log_file = tmp_path / "log.jsonl"
    hoje = datetime.now(UTC).strftime("%Y-%m-%dT")
    antigo = (datetime.now(UTC) - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    _escrever_log_json(log_file, [
        {"timestamp": hoje + "09:00:00.000000Z", "event": "recorder.subscrito"},
        {"timestamp": antigo, "event": "recorder.heartbeat", "linhas": 500},
    ])
    veredito = checar(
        log_file, tmp_path / "alertas.yaml", tmp_path / "estado.json",
        abertura_local="00:00", fechamento_local="23:59", limite_parado_min=6.0,
    )
    assert veredito == "travado"


def test_vigia_fora_do_pregao_nao_verifica(tmp_path: Path) -> None:
    """Fora da janela abertura-fechamento, nunca alerta 'nao_iniciou' —
    senao dispararia alarme falso toda madrugada."""
    log_file = tmp_path / "log.jsonl"
    _escrever_log_json(log_file, [])
    veredito = checar(
        log_file, tmp_path / "alertas.yaml", tmp_path / "estado.json",
        abertura_local="23:58", fechamento_local="23:59",
    )
    assert veredito == "fora_do_pregao"


def test_vigia_respeita_cooldown_nao_alerta_toda_chamada(tmp_path: Path) -> None:
    """Chamado 2x seguidas com a mesma condicao -> so' o primeiro grava
    estado (o teste confirma via arquivo de estado, nao via envio real)."""
    log_file = tmp_path / "log.jsonl"
    _escrever_log_json(log_file, [])
    estado_arquivo = tmp_path / "estado.json"

    checar(log_file, tmp_path / "alertas.yaml", estado_arquivo,
          abertura_local="00:00", fechamento_local="23:59")
    estado1 = json.loads(estado_arquivo.read_text())
    primeiro_ts = estado1["nao_iniciou"]

    time.sleep(0.05)
    checar(log_file, tmp_path / "alertas.yaml", estado_arquivo,
          abertura_local="00:00", fechamento_local="23:59")
    estado2 = json.loads(estado_arquivo.read_text())
    # dentro do cooldown (30min): o timestamp NAO deve ter avancado
    assert estado2["nao_iniciou"] == primeiro_ts


def test_logging_setup_grava_json_valido_em_arquivo(tmp_path: Path) -> None:
    """
    Bug real corrigido: --log-file gravava o MESMO texto do console (nao
    JSON), apesar do nome .jsonl. vigia.py depende de JSON valido para
    funcionar — esta e' a garantia de que a premissa se sustenta.

    configurar() muda estado GLOBAL (structlog.configure + root logger) —
    sem desfazer, testes seguintes na mesma sessao do pytest herdam um
    StreamHandler preso a um sys.stdout ja fechado (o capsys de OUTRO
    teste), e o capsys deles fica vazio. Restaura no finally para nao
    vazar estado entre testes.
    """
    import logging as _logging

    import structlog

    handlers_antes = list(_logging.getLogger().handlers)
    nivel_antes = _logging.getLogger().level
    try:
        arq = tmp_path / "log.jsonl"
        configurar("INFO", arq)
        log = structlog.get_logger("teste")
        log.info("evento.teste", chave="valor", numero=42)

        linhas = arq.read_text(encoding="utf-8").strip().splitlines()
        # A 1a linha agora e' sempre 'log.destino' (anuncio do caminho
        # absoluto resolvido — ver logging_setup.py, 2026-08-25); o evento
        # real do teste e' a ULTIMA linha, nao a unica.
        assert len(linhas) == 2
        d_destino = json.loads(linhas[0])
        assert d_destino["event"] == "log.destino"
        assert d_destino["arquivo"] == str(arq.resolve())
        d = json.loads(linhas[-1])   # nao pode levantar
        assert d["event"] == "evento.teste"
        assert d["chave"] == "valor"
        assert d["numero"] == 42
        assert "timestamp" in d
    finally:
        structlog.reset_defaults()
        _logging.getLogger().handlers[:] = handlers_antes
        _logging.getLogger().setLevel(nivel_antes)


def test_log_destino_anuncia_caminho_absoluto_mesmo_se_passado_relativo(
    tmp_path: Path,
) -> None:
    """
    Pedido real do operador (2026-08-25): --log-file relativo, rodado de um
    diretorio de trabalho inesperado, escreveu o log num lugar que ninguem
    olhou depois. Agora QUALQUER --log-file (relativo ou nao) anuncia seu
    caminho ABSOLUTO resolvido na primeira linha — console e arquivo — antes
    de qualquer outro log do comando.
    """
    import logging as _logging
    import os

    import structlog

    from profittape.logging_setup import configurar

    handlers_antes = list(_logging.getLogger().handlers)
    nivel_antes = _logging.getLogger().level
    cwd_antes = os.getcwd()
    try:
        os.chdir(tmp_path)
        configurar("INFO", Path("subpasta/log.jsonl"))   # relativo de proposito
        linhas = (tmp_path / "subpasta" / "log.jsonl").read_text().strip().splitlines()
        assert len(linhas) == 1
        d = json.loads(linhas[0])
        assert d["event"] == "log.destino"
        # o caminho anunciado tem que ser ABSOLUTO, nao o relativo original
        assert Path(d["arquivo"]).is_absolute()
        assert d["arquivo"] == str((tmp_path / "subpasta" / "log.jsonl").resolve())
    finally:
        os.chdir(cwd_antes)
        structlog.reset_defaults()
        _logging.getLogger().handlers[:] = handlers_antes
        _logging.getLogger().setLevel(nivel_antes)


def test_nivel_arquivo_independente_do_console(tmp_path: Path) -> None:
    """
    Pedido real (2026-08-27, ea-replay-lote): console quieto (WARNING,
    rodando 23 dias de uma vez) mas arquivo com detalhe completo (INFO)
    para auditoria posterior. Sem isso, o filtro global descartaria o
    INFO antes de chegar em QUALQUER handler, inclusive o arquivo.
    """
    import logging as _logging

    import structlog

    from profittape.logging_setup import configurar

    handlers_antes = list(_logging.getLogger().handlers)
    nivel_antes = _logging.getLogger().level
    try:
        arq = tmp_path / "log.jsonl"
        configurar("WARNING", arq, nivel_arquivo="INFO")
        log = structlog.get_logger("teste")
        log.info("evento.info", chave="valor")   # NAO deveria ir pro console
        log.warning("evento.warning")             # deveria ir pros dois

        linhas = arq.read_text(encoding="utf-8").strip().splitlines()
        eventos = [json.loads(linha)["event"] for linha in linhas]
        # log.destino (sempre) + os dois eventos, INFO incluso no arquivo
        assert "evento.info" in eventos
        assert "evento.warning" in eventos
    finally:
        structlog.reset_defaults()
        _logging.getLogger().handlers[:] = handlers_antes
        _logging.getLogger().setLevel(nivel_antes)


def test_sem_nivel_arquivo_comportamento_identico_ao_de_sempre(tmp_path: Path) -> None:
    """Retrocompatibilidade: omitir nivel_arquivo tem que dar EXATAMENTE
    o mesmo resultado de antes -- nenhum chamador existente muda."""
    import logging as _logging

    import structlog

    from profittape.logging_setup import configurar

    handlers_antes = list(_logging.getLogger().handlers)
    nivel_antes = _logging.getLogger().level
    try:
        arq = tmp_path / "log.jsonl"
        configurar("WARNING", arq)   # sem nivel_arquivo
        log = structlog.get_logger("teste")
        log.info("evento.info")      # deve ser FILTRADO, igual sempre foi

        linhas = arq.read_text(encoding="utf-8").strip().splitlines()
        eventos = [json.loads(linha)["event"] for linha in linhas]
        assert "evento.info" not in eventos
    finally:
        structlog.reset_defaults()
        _logging.getLogger().handlers[:] = handlers_antes
        _logging.getLogger().setLevel(nivel_antes)
