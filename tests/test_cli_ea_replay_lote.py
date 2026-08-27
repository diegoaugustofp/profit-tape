"""
Teste do progresso do comando `ea-replay-lote` (2026-08-27, pedido real
do operador): sem contador [i/N] e marcador de inicio/fim por dia,
rodando dezenas de dias, nao da' pra saber se o processo travou ou so'
esta demorando. Ver docs/BOAS_PRATICAS_PROGRESSO.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from profittape.cli import app

runner = CliRunner()

# Nota: nao precisa de fixture de limpeza de log aqui -- ea-replay-lote
# chama configurar() internamente (via CliRunner), que muda estado GLOBAL
# do structlog; o reset e' feito pela fixture autouse em conftest.py
# (_isolar_estado_global_de_logging), que cobre TODOS os testes da suite.


def _preparar_dias(raiz: Path, dias: list[str]) -> None:
    for i, dia in enumerate(dias):
        rng = np.random.default_rng(i)
        n = 3000
        df = pd.DataFrame({
            "ts_ns": np.arange(n, dtype=np.int64) * 10**8,
            "ts_recv_ns": np.arange(n, dtype=np.int64) * 10**8,
            "symbol": "WINFUT", "exchange": "F", "trade_id": np.arange(n),
            "price": 140000.0 + np.cumsum(rng.choice([-5.0, 0.0, 5.0], n)),
            "volume_financeiro": 0.0,
            "quantidade": rng.integers(1, 8, n),
            "agente_comprador": rng.choice([3, 85], n),
            "agente_vendedor": rng.choice([3, 85], n),
            "trade_type": rng.choice([2, 3], n),
            "is_edit": False,
        })
        d = raiz / "trade" / f"dt={dia}" / "sym=WINFUT"
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "part-0000.parquet", index=False)


def _config(caminho: Path) -> None:
    caminho.write_text("""
symbol: WINFUT
volume_barra: 80
janela_z: 10
tamanho_posicao: 1
custo_pontos_estimado: 11.0
dry_run: true
usar_conta_real: false
sinais:
  - feature: z_agf_3
    horizonte: 3
    agent_id: 3
    threshold_entrada: 1.0
    direcao: contrarian
risco:
  capital: 5000.0
  risco_max_pct: 0.02
  valor_ponto_reais: 0.20
  max_perdas_consecutivas: 3
""")


def test_progresso_mostra_contador_e_marcador_inicio_fim_por_dia(tmp_path: Path) -> None:
    dias = ["2026-08-24", "2026-08-25", "2026-08-26"]
    _preparar_dias(tmp_path / "raw", dias)
    cfg = tmp_path / "ea.yaml"
    _config(cfg)

    resultado = runner.invoke(app, [
        "ea-replay-lote", "-c", str(cfg),
        "--raiz-raw", str(tmp_path / "raw"),
        "--saida", str(tmp_path / "out"),
    ])
    assert resultado.exit_code == 0, resultado.output

    for i, dia in enumerate(dias, 1):
        assert f"[{i}/3] {dia} — iniciando" in resultado.output
        assert f"[{i}/3] {dia} concluido" in resultado.output
    # A estimativa de tempo restante tem que aparecer, mesmo que pequena
    assert "restante~=" in resultado.output


def test_progresso_tambem_vai_para_o_log_file(tmp_path: Path) -> None:
    """Duplo canal: quem so' vai olhar --log-file depois precisa ver a
    MESMA informacao que apareceu na tela."""
    dias = ["2026-08-24", "2026-08-25"]
    _preparar_dias(tmp_path / "raw", dias)
    cfg = tmp_path / "ea.yaml"
    _config(cfg)
    log_file = tmp_path / "lote.jsonl"

    resultado = runner.invoke(app, [
        "ea-replay-lote", "-c", str(cfg),
        "--raiz-raw", str(tmp_path / "raw"),
        "--saida", str(tmp_path / "out"),
        "--log-file", str(log_file),
    ])
    assert resultado.exit_code == 0, resultado.output

    conteudo = log_file.read_text(encoding="utf-8")
    assert "ea.replay_lote_dia_iniciando" in conteudo
    assert "ea.replay_lote_dia_concluido" in conteudo
    for dia in dias:
        assert dia in conteudo


def test_relatorio_lote_quebra_por_lado(tmp_path: Path) -> None:
    """
    Mesma pergunta que mae.py ja respondia de forma independente: as
    perdas do EA simulado (dado REAL do proprio replay) estao
    concentradas no lado de compra, ou distribuidas nos dois?
    """
    dias = ["2026-08-24", "2026-08-25", "2026-08-26"]
    _preparar_dias(tmp_path / "raw", dias)
    cfg = tmp_path / "ea.yaml"
    _config(cfg)

    resultado = runner.invoke(app, [
        "ea-replay-lote", "-c", str(cfg),
        "--raiz-raw", str(tmp_path / "raw"),
        "--saida", str(tmp_path / "out"),
    ])
    assert resultado.exit_code == 0, resultado.output
    assert "por lado (pnl" in resultado.output
    assert "compra:" in resultado.output
    assert "venda " in resultado.output

    arquivos_md = list((tmp_path / "out").glob("*.md"))
    assert len(arquivos_md) == 1
    conteudo = arquivos_md[0].read_text(encoding="utf-8")
    assert "Por lado (pnl LIQUIDO" in conteudo


def test_comparar_circuit_breaker_nao_combina_com_ignorar(tmp_path: Path) -> None:
    dias = ["2026-08-24"]
    _preparar_dias(tmp_path / "raw", dias)
    cfg = tmp_path / "ea.yaml"
    _config(cfg)

    resultado = runner.invoke(app, [
        "ea-replay-lote", "-c", str(cfg),
        "--raiz-raw", str(tmp_path / "raw"),
        "--saida", str(tmp_path / "out"),
        "--ignorar-circuit-breaker", "--comparar-circuit-breaker",
    ])
    assert resultado.exit_code != 0
    assert "nao combina" in resultado.output or "nao combina" in str(resultado.exception)


def test_comparar_circuit_breaker_mostra_com_e_sem_freio(tmp_path: Path) -> None:
    """
    Pedido real do operador (2026-08-27): apos ver que o circuit breaker
    disparou num dia e o resto do dia teria recuperado (sem o freio),
    a comparacao precisa ser automatica -- carrega o dia UMA vez, roda
    DUAS simulacoes (com e sem freio) sobre o MESMO dado, sem reler o
    parquet duas vezes.
    """
    dias = ["2026-08-24"]
    # Volume alto o suficiente para provavelmente disparar o circuit
    # breaker em pelo menos um cenario -- usa o mesmo gerador de sempre.
    _preparar_dias(tmp_path / "raw", dias)
    cfg = tmp_path / "ea.yaml"
    _config(cfg)

    resultado = runner.invoke(app, [
        "ea-replay-lote", "-c", str(cfg),
        "--raiz-raw", str(tmp_path / "raw"),
        "--saida", str(tmp_path / "out"),
        "--comparar-circuit-breaker",
    ])
    assert resultado.exit_code == 0, resultado.output

    arquivos_md = list((tmp_path / "out").glob("*.md"))
    conteudo = arquivos_md[0].read_text(encoding="utf-8")
    assert "pnl (com freio)" in conteudo
    assert "pnl (sem freio)" in conteudo
    assert "ATENCAO NA LEITURA" in conteudo
