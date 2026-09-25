"""Porta do livro ao vivo (v3.69). Incidente de 25/09: o record subiu sem
--ea-livro-ao-vivo, o EA de ignicao entrou a quente pela --ea-dir e ficou
sem livro o pregao inteiro (fill=tape, deslizamento nao medido). O gancho
era decidido na subida e capturado no callback da DLL; nada depois o
ligava. Agora o gancho vai sempre, atras de uma porta, e o registro abre
a porta quando entra o 1o EA que usa livro."""

from __future__ import annotations

from pathlib import Path

from profittape.config import (
    AtivoConfig,
    Credenciais,
    PipelineConfig,
    RecorderConfig,
    RuntimeConfig,
    StorageConfig,
)
from profittape.domain.events import TinyBook
from profittape.ea.config import EAConfig
from profittape.ea.config_ignicao import EAIgnicaoConfig
from profittape.ea.config_microprice import EAMicropriceConfig
from profittape.ea.registro import usa_livro
from profittape.recorder.service import RecorderService
from profittape.testing.fake_dll import FakeProfitDLL

RAIZ = Path(__file__).resolve().parents[1]

# Copiado de test_ea_dir_a_quente.py (EA de fluxo real), + filtro_book.
_YAML_FLUXO = """symbol: PETR4
volume_barra: 30
janela_z: 10
tamanho_posicao: 1
dry_run: true
filtro_book: false
sinais:
  - feature: z_agf_3
    horizonte: 3
    agent_id: 3
    threshold_entrada: 1.4
    direcao: contrarian
"""


def _cfg(tmp: Path) -> RecorderConfig:
    return RecorderConfig(
        ativos=[AtivoConfig(ticker="WINFUT", bolsa="F", trades=True),
                AtivoConfig(ticker="PETR4", bolsa="B", trades=True)],
        storage=StorageConfig(raiz=tmp / "raw", max_rows_per_file=1_000_000),
        pipeline=PipelineConfig(fila_maxsize=200_000, batch_max=5_000, poll_timeout_s=0.1),
        runtime=RuntimeConfig(heartbeat_s=5.0, encerrar_em=None),
    )


def _svc(tmp: Path, pasta: Path | None = None, forcar: bool = False) -> RecorderService:
    return RecorderService(_cfg(tmp), Credenciais(activation_key="k", user="u",
                                                  password="p", dll_path="fake"),
                           dll_injetada=FakeProfitDLL(eventos_por_ativo=0),
                           ea_dir=pasta, ea_livro_ao_vivo=forcar)


def _alimentar(svc: RecorderService) -> None:
    """Simula o callback da DLL entregando os dois lados do topo do WIN."""
    svc._alimentar_livro(TinyBook(1, "WINFUT", "F", 0, 188000.0, 10))
    svc._alimentar_livro(TinyBook(2, "WINFUT", "F", 1, 188005.0, 12))


def test_gancho_vai_sempre_para_a_dll_mas_fechado(tmp_path: Path) -> None:
    svc = _svc(tmp_path)
    assert svc.client._on_tiny_extra == svc._alimentar_livro
    assert svc._livro_aberto is False
    _alimentar(svc)
    assert svc.livro_ao_vivo.ler("WINFUT") is None        # porta fechada: nada


def test_EA_de_ignicao_A_QUENTE_abre_o_livro_sem_a_flag(tmp_path: Path) -> None:
    """O caso de 25/09: record sem a flag, yaml aparece com o record no ar."""
    pasta = tmp_path / "eas"
    pasta.mkdir()
    svc = _svc(tmp_path, pasta)
    svc._em_execucao = True
    _alimentar(svc)
    assert svc.livro_ao_vivo.ler("WINFUT") is None

    (pasta / "ea_ignicao.yaml").write_text(
        (RAIZ / "config" / "ea_ignicao.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    svc._varrer_ea_dir()
    assert svc.registro.nomes == ["ea_ignicao"]
    assert svc._livro_aberto is True
    ea = svc.despachante.bridges[0].ea_service
    assert ea.livro is svc.livro_ao_vivo

    _alimentar(svc)
    topo = svc.livro_ao_vivo.ler("WINFUT")
    assert topo is not None and (topo.preco_bid, topo.preco_ask) == (188000.0, 188005.0)


def test_EA_que_nao_usa_livro_nao_abre_a_porta(tmp_path: Path) -> None:
    pasta = tmp_path / "eas"
    pasta.mkdir()
    (pasta / "petr.yaml").write_text(_YAML_FLUXO, encoding="utf-8")
    svc = _svc(tmp_path, pasta)
    svc._em_execucao = True
    svc._varrer_ea_dir()
    assert svc.registro.nomes == ["petr"]
    assert svc._livro_aberto is False


def test_flag_forca_desde_a_subida_e_abrir_e_idempotente(tmp_path: Path) -> None:
    svc = _svc(tmp_path, forcar=True)
    assert svc._livro_aberto is True
    svc.ativar_livro_ao_vivo("de novo")                   # nao quebra, nao repete
    _alimentar(svc)
    assert svc.livro_ao_vivo.ler("WINFUT") is not None


def test_quais_EAs_usam_livro() -> None:
    assert usa_livro(EAIgnicaoConfig())
    assert usa_livro(EAMicropriceConfig(tipo="microprice"))
    import yaml
    dados = yaml.safe_load(_YAML_FLUXO)
    assert not usa_livro(EAConfig(**dados))
    assert usa_livro(EAConfig(**{**dados, "filtro_book": True}))
