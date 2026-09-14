"""
E5.4b — incluir e remover EA COM O RECORD RODANDO, via `--ea-dir`.

O que estes testes protegem e' a decisao do operador (2026-09-11):

    "Se o record iniciou uma estrategia eu nao inicio uma nova sem
    reiniciar o record. Isso gera perda de dados."

Captura perdida nao se refaz. Entao: nenhum erro de EA -- yaml torto,
ticker repetido, config invalida -- pode derrubar o record em execucao.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from profittape.config import (
    AtivoConfig,
    Credenciais,
    PipelineConfig,
    RecorderConfig,
    RuntimeConfig,
    StorageConfig,
)
from profittape.recorder.service import RecorderService
from profittape.testing.fake_dll import FakeProfitDLL

_YAML = """symbol: {symbol}
volume_barra: 30
janela_z: 10
tamanho_posicao: 1
dry_run: true
sinais:
  - feature: z_agf_3
    horizonte: 3
    agent_id: 3
    threshold_entrada: 1.4
    direcao: contrarian
"""


def _escrever(pasta: Path, nome: str, symbol: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{nome}.yaml"
    caminho.write_text(_YAML.format(symbol=symbol), encoding="utf-8")
    return caminho


def _cfg(tmp: Path) -> RecorderConfig:
    return RecorderConfig(
        ativos=[AtivoConfig(ticker="PETR4", bolsa="B", trades=True),
                AtivoConfig(ticker="VALE3", bolsa="B", trades=True)],
        storage=StorageConfig(raiz=tmp / "raw", max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=200_000, batch_max=5_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(heartbeat_s=5.0, encerrar_em=None),
    )


def _cred() -> Credenciais:
    return Credenciais(activation_key="k", user="u", password="p", dll_path="fake")


def test_ea_dir_vazia_sobe_sem_nenhum_EA(tmp_path: Path) -> None:
    pasta = tmp_path / "eas"
    pasta.mkdir()
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    assert len(svc.despachante) == 0
    assert svc.registro.nomes == []


def test_incluir_EA_A_QUENTE_sem_parar_o_record(tmp_path: Path) -> None:
    """O teste central do E5.4b: o record ja' esta' capturando quando o
    yaml aparece, e o EA entra sem que nada pare."""
    pasta = tmp_path / "eas"
    pasta.mkdir()
    # intervalo_s>0: o fake precisa CONTINUAR emitindo depois que o EA
    # entrar, senao o teste passaria por acidente (EA incluido, mas sem
    # trade sobrando para provar que ele recebe).
    fake = FakeProfitDLL(eventos_por_ativo=3000, intervalo_s=0.001)
    svc = RecorderService(_cfg(tmp_path), _cred(), dll_injetada=fake, ea_dir=pasta)
    svc._EA_DIR_INTERVALO_S = 0.2          # acelera a varredura no teste
    assert len(svc.despachante) == 0

    t = threading.Thread(target=svc.run, daemon=True)
    t.start()
    time.sleep(0.8)
    recebidos_antes = svc.bus.stats().total_recebido
    assert recebidos_antes > 0, "a captura precisa ja' estar rodando"

    _escrever(pasta, "petr", "PETR4")      # <- EA aparece COM o record no ar
    fim = time.monotonic() + 5
    while time.monotonic() < fim and len(svc.despachante) == 0:
        time.sleep(0.1)
    assert len(svc.despachante) == 1, "EA nao foi incluido a quente"
    ea_svc = svc.despachante.bridges[0].ea_service

    time.sleep(0.8)
    svc._parar.set()
    t.join(timeout=60)

    assert ea_svc.stats.trades > 0, "o EA incluido a quente tem que receber trades"
    assert svc.bus.stats().total_descartado == 0, "a captura nao pode ter sofrido"


def test_remover_EA_tirando_o_yaml_da_pasta(tmp_path: Path) -> None:
    pasta = tmp_path / "eas"
    caminho = _escrever(pasta, "petr", "PETR4")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._EA_DIR_INTERVALO_S = 0.2
    svc._em_execucao = True
    svc._varrer_ea_dir()
    assert svc.registro.nomes == ["petr"]

    caminho.unlink()                        # <- yaml some
    svc._varrer_ea_dir()
    assert svc.registro.nomes == [], "EA tinha que sair quando o yaml sumiu"
    assert len(svc.despachante) == 0


def test_yaml_INVALIDO_nao_derruba_o_record(tmp_path: Path) -> None:
    """Um yaml torto na pasta e' erro do operador, nao motivo para perder
    captura. Loga e segue."""
    pasta = tmp_path / "eas"
    pasta.mkdir()
    (pasta / "torto.yaml").write_text("isto: nao e' uma EAConfig\n", encoding="utf-8")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()                    # NAO levanta
    assert svc.registro.nomes == []


def test_dois_EAs_no_MESMO_ticker_o_segundo_e_recusado(tmp_path: Path) -> None:
    """A trava do caminho B, agora ponta a ponta pela pasta: sem
    subconta, dois EAs no mesmo ativo netariam."""
    pasta = tmp_path / "eas"
    _escrever(pasta, "primeiro", "PETR4")
    _escrever(pasta, "segundo", "PETR4")    # mesmo ticker!
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()
    assert len(svc.registro.nomes) == 1, "so' um dos dois pode ter entrado"
    assert len(svc.despachante) == 1


def test_dois_EAs_em_tickers_diferentes_convivem(tmp_path: Path) -> None:
    pasta = tmp_path / "eas"
    _escrever(pasta, "petr", "PETR4")
    _escrever(pasta, "vale", "VALE3")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()
    assert sorted(svc.registro.nomes) == ["petr", "vale"]
    assert svc.registro.tickers_ocupados() == {"PETR4": "petr", "VALE3": "vale"}


def test_pasta_ilegivel_nao_derruba_a_captura(tmp_path: Path) -> None:
    """Pasta em rede fora do ar, permissao negada: loga e segue."""
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=tmp_path / "nao_existe")
    svc._em_execucao = True
    svc._varrer_ea_dir()                    # NAO levanta
    assert svc.registro.nomes == []


def test_EA_com_ordens_reais_a_quente_sem_pre_requisito_e_recusado(tmp_path: Path) -> None:
    """dry_run=False exige --ea-ticker-ordem e login completo. A QUENTE
    isso nao pode matar o processo -- so' recusa o EA."""
    pasta = tmp_path / "eas"
    pasta.mkdir()
    (pasta / "real.yaml").write_text(
        _YAML.format(symbol="PETR4").replace("dry_run: true", "dry_run: false"),
        encoding="utf-8")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()                    # NAO levanta
    assert svc.registro.nomes == []


def test_EA_com_ordens_reais_NA_CONSTRUCAO_sem_pre_requisito_mata_o_processo(
    tmp_path: Path,
) -> None:
    """Na construcao e' o oposto: nao ha' captura a perder, e subir um
    record que o operador acha que vai operar (mas nao vai) e' pior que
    nao subir."""
    ea = tmp_path / "real.yaml"
    ea.write_text(_YAML.format(symbol="PETR4").replace("dry_run: true", "dry_run: false"),
                  encoding="utf-8")
    with pytest.raises(SystemExit, match="ea-ticker-ordem"):
        RecorderService(_cfg(tmp_path), _cred(),
                        dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                        ea_config_path=ea)


def test_yaml_recusado_NAO_repete_o_erro_a_cada_varredura(tmp_path: Path) -> None:
    """Producao 2026-09-14: um yaml com ticker ja' ocupado gerou ~25
    linhas de erro IDENTICAS em 2 minutos (uma a cada varredura), ate' o
    operador corrigir. Ruido nessa escala esconde o que importa ler."""
    import structlog

    pasta = tmp_path / "eas"
    _escrever(pasta, "primeiro", "PETR4")
    ruim = _escrever(pasta, "segundo", "PETR4")      # ticker ja' ocupado
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True

    with structlog.testing.capture_logs() as eventos:
        for _ in range(5):                            # 5 varreduras
            svc._varrer_ea_dir()
    recusas = [e for e in eventos if e.get("event") == "recorder.ea_inclusao_recusada"]
    assert len(recusas) == 1, f"a recusa tem que sair UMA vez, saiu {len(recusas)}"
    assert len(svc.registro.nomes) == 1

    # editar o arquivo (corrigir o ticker) faz tentar de novo, sem reiniciar
    ruim.write_text(_YAML.format(symbol="VALE3"), encoding="utf-8")
    svc._varrer_ea_dir()
    assert sorted(svc.registro.nomes) == ["primeiro", "segundo"], (
        "corrigir o arquivo tem que bastar -- sem reiniciar o record")


def test_yaml_invalido_tambem_para_de_repetir(tmp_path: Path) -> None:
    import structlog

    pasta = tmp_path / "eas"
    pasta.mkdir()
    (pasta / "torto.yaml").write_text("isto: nao e' EAConfig\n", encoding="utf-8")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    with structlog.testing.capture_logs() as eventos:
        for _ in range(5):
            svc._varrer_ea_dir()
    assert len([e for e in eventos if e.get("event") == "recorder.ea_yaml_invalido"]) == 1


def test_remover_e_recolocar_o_arquivo_tenta_de_novo(tmp_path: Path) -> None:
    """Tirar o yaml da pasta esquece a falha: se voltar, merece nova
    chance (o operador pode ter arrumado fora da pasta)."""
    pasta = tmp_path / "eas"
    _escrever(pasta, "primeiro", "PETR4")
    ruim = _escrever(pasta, "segundo", "PETR4")
    svc = RecorderService(_cfg(tmp_path), _cred(),
                          dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                          ea_dir=pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()
    assert len(svc._ea_falhas_conhecidas) == 1
    ruim.unlink()
    svc._varrer_ea_dir()
    assert svc._ea_falhas_conhecidas == set(), "arquivo fora da pasta: esquecer a falha"
