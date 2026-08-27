"""
Testes de tools/triagem_inprogress.py -- resposta ao incidente real
(2026-08-27): maquina travou, todos os writers abertos naquele instante
ficaram orfaos simultaneamente, um por stream/simbolo.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from profittape.tools.triagem_inprogress import gerar_resumo_para_integridade, triagem


def _criar_inprogress_com_footer(caminho: Path) -> None:
    """Simula o crash acontecer DEPOIS do footer, ANTES do rename --
    janela pequena mas real, dado intacto."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"x": [1, 2, 3]}), caminho)   # footer sempre valido


def _criar_inprogress_sem_footer(caminho: Path) -> None:
    """Simula o caso comum: crash NO MEIO da escrita, sem footer."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"PAR1" + b"\x00" * 100)   # magic no INICIO, nao no fim -- sem footer real


def _envelhecer(caminho: Path, minutos: float) -> None:
    """Move o mtime do arquivo para o passado, simulando um arquivo
    parado ha' muito tempo (sem escritor vivo)."""
    agora = time.time()
    os.utime(caminho, (agora - minutos * 60, agora - minutos * 60))


def test_arquivo_recente_e_pulado_nunca_tocado(tmp_path: Path) -> None:
    raiz = tmp_path / "raw"
    arq = raiz / "trade" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet.inprogress"
    _criar_inprogress_sem_footer(arq)
    # NAO envelhece -- mtime e' "agora", dentro do limiar

    r = triagem(raiz, tmp_path / "quarentena", idade_min_min=15.0, mover=True)
    assert len(r.pulados_recentes) == 1
    assert len(r.quarentenados) == 0
    assert arq.exists()   # intocado


def test_arquivo_antigo_sem_footer_vai_para_quarentena(tmp_path: Path) -> None:
    raiz = tmp_path / "raw"
    arq = raiz / "book_offer" / "dt=2026-08-27" / "sym=WDOFUT" / "part-0008.parquet.inprogress"
    _criar_inprogress_sem_footer(arq)
    _envelhecer(arq, minutos=30)

    destino_q = tmp_path / "quarentena"
    r = triagem(raiz, destino_q, idade_min_min=15.0, mover=True)

    assert len(r.quarentenados) == 1
    assert len(r.recuperados) == 0
    assert not arq.exists()   # saiu da arvore original
    assert r.quarentenados[0].exists()   # esta na quarentena
    assert "book_offer" in str(r.quarentenados[0])   # estrutura relativa preservada


def test_arquivo_antigo_com_footer_e_recuperado(tmp_path: Path) -> None:
    """Caso feliz: crash aconteceu APOS o footer, ANTES do rename --
    dado intacto, so' precisa da promocao (tirar o .inprogress)."""
    raiz = tmp_path / "raw"
    arq = raiz / "trade" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet.inprogress"
    _criar_inprogress_com_footer(arq)
    _envelhecer(arq, minutos=30)

    r = triagem(raiz, tmp_path / "quarentena", idade_min_min=15.0, mover=True)

    assert len(r.recuperados) == 1
    assert len(r.quarentenados) == 0
    assert not arq.exists()   # o .inprogress sumiu...
    esperado = raiz / "trade" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet"
    assert esperado.exists()   # ...porque virou isto
    pq.ParquetFile(esperado)   # le sem erro -- dado genuinamente recuperado


def test_dry_run_nao_move_nada(tmp_path: Path) -> None:
    raiz = tmp_path / "raw"
    arq = raiz / "trade" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet.inprogress"
    _criar_inprogress_sem_footer(arq)
    _envelhecer(arq, minutos=30)

    r = triagem(raiz, tmp_path / "quarentena", idade_min_min=15.0, mover=False)

    assert len(r.quarentenados) == 1   # identificado...
    assert arq.exists()                 # ...mas NADA foi movido de verdade
    assert not r.quarentenados[0].exists()


def test_varios_streams_e_simbolos_de_uma_vez(tmp_path: Path) -> None:
    """O cenario real: travamento afeta TODOS os streams/simbolos abertos
    no mesmo instante -- a ferramenta precisa achar todos numa passada."""
    raiz = tmp_path / "raw"
    arquivos = [
        raiz / "trade" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet.inprogress",
        raiz / "trade" / "dt=2026-08-27" / "sym=PETR4" / "part-0008.parquet.inprogress",
        raiz / "book_offer" / "dt=2026-08-27" / "sym=WINFUT" / "part-0008.parquet.inprogress",
        raiz / "tiny_book" / "dt=2026-08-27" / "sym=VALE3" / "part-0008.parquet.inprogress",
    ]
    for a in arquivos:
        _criar_inprogress_sem_footer(a)
        _envelhecer(a, minutos=30)

    r = triagem(raiz, tmp_path / "quarentena", idade_min_min=15.0, mover=True)
    assert len(r.quarentenados) == 4

    resumo = gerar_resumo_para_integridade(r, raiz)
    assert "trade" in resumo
    assert "book_offer" in resumo
    assert "tiny_book" in resumo
    assert "WINFUT" in resumo and "PETR4" in resumo and "VALE3" in resumo


def test_resumo_vazio_quando_nada_quarentenado(tmp_path: Path) -> None:
    from profittape.tools.triagem_inprogress import ResultadoTriagem
    resumo = gerar_resumo_para_integridade(ResultadoTriagem(), tmp_path)
    assert "Nenhum arquivo" in resumo
