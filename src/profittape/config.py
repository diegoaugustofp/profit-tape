"""
Configuracao: YAML para o que e' versionavel, .env para o que e' segredo.

Credencial NUNCA entra no YAML — o arquivo de config e' feito para ser lido,
comparado e discutido; a chave de ativacao nao.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Credenciais(BaseSettings):
    """Vem do ambiente ou de .env. Nunca do YAML."""

    model_config = SettingsConfigDict(
        env_prefix="PROFIT_", env_file=".env", extra="ignore"
    )

    activation_key: str = ""
    user: str = ""
    password: str = ""
    dll_path: str = r"C:\Profit\ProfitDLL64.dll"
    pg_dsn: str | None = None

    def validar(self) -> None:
        faltando = [c for c in ("activation_key", "user", "password") if not getattr(self, c)]
        if faltando:
            raise ValueError(
                f"Credencial ausente: {faltando}. Copie .env.example para .env "
                f"e preencha, ou exporte PROFIT_* no ambiente."
            )


class AtivoConfig(BaseModel):
    ticker: str
    bolsa: str = "B"
    trades: bool = True
    offer_book: bool = False
    price_book: bool = False


class StorageConfig(BaseModel):
    raiz: Path

    @field_validator("raiz")
    @classmethod
    def _exigir_absoluto(cls, v: Path) -> Path:
        # ARMADILHA REAL #1 (2026-08-22): 'raiz: \data\raw' (barra inicial SEM
        # letra de unidade) e' "relativo a unidade" no Windows — resolve para
        # a raiz do DRIVE CORRENTE do terminal. Uma recaptura de 20 dias foi
        # para G:\ (o disco que corrompe) e outra para C:\data\raw (fora do
        # projeto), ambas em silencio.
        #
        # ARMADILHA REAL #2 (2026-08-25): mesmo o caso "seguro" recomendado
        # pela 1a versao desta defesa — 'raiz: data\raw', relativo PURO, sem
        # barra nenhuma — se mostrou igualmente perigoso. Resolve relativo ao
        # CWD do PROCESSO no momento em que inicia, nao ao arquivo yaml nem
        # ao projeto. Rodando manualmente (sempre com `cd` pro projeto antes)
        # isso sempre acertou por acidente — mas o schtasks nao garante CWD
        # nenhum, e o mesmo yaml resolveu para C:\data\raw num teste de
        # reproducao (2026-08-25), fora do projeto inteiro. Nao houve como
        # confirmar se foi a causa do exit code 1 daquele dia, mas o bug em
        # si e' real e reproduzivel.
        #
        # CORRECAO: exigir absoluto SEMPRE. Nao existe "relativo seguro" pra
        # um processo cujo CWD de lancamento nao esta sob nosso controle —
        # so' absoluto elimina a ambiguidade por completo, incondicionalmente.
        if not v.is_absolute():
            raise ValueError(
                f"storage.raiz '{v}' nao e' absoluto. Caminho relativo "
                f"resolve contra o diretorio de trabalho do PROCESSO no "
                f"momento em que inicia — que o schtasks nao garante ser o "
                f"do projeto (confirmado: o mesmo yaml resolveu para "
                f"C:\\data\\raw rodando de C:\\, 2026-08-25). Use caminho "
                f"absoluto completo, ex.: C:\\projetos\\profit-tape\\data\\raw."
            )
        return v.resolve()
    compressao: Literal["zstd", "snappy", "gzip", "lz4"] = "zstd"
    nivel_compressao: int = 3
    max_rows_per_file: int = 5_000_000
    idle_close_s: float = 900.0


class PipelineConfig(BaseModel):
    fila_maxsize: int = 500_000
    batch_max: int = 50_000
    poll_timeout_s: float = 0.5
    # Acima disso, escrita de lote vira log. Em HDD USB com spin-down, 1-2 s
    # na CRIACAO de arquivo e' fisica do disco, nao gargalo — suba o limiar ou
    # ignore os eventos rotulados como criacao_de_arquivo.
    limiar_lote_lento_s: float = 1.0


class RuntimeConfig(BaseModel):
    tz_offset_horas: int = -3
    heartbeat_s: float = 30.0
    encerrar_em: str | None = Field(
        default=None,
        description="HH:MM local. Encerra sozinho — util em Agendador de Tarefas.",
    )
    alerta_taxa_descarte: float = 0.0001

    @field_validator("encerrar_em")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        h, _, m = v.partition(":")
        if not (h.isdigit() and m.isdigit() and 0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError(f"encerrar_em deve ser HH:MM, veio {v!r}")
        return v


class RecorderConfig(BaseModel):
    ativos: list[AtivoConfig]
    storage: StorageConfig
    pipeline: PipelineConfig = PipelineConfig()
    runtime: RuntimeConfig = RuntimeConfig()

    @classmethod
    def from_yaml(cls, caminho: str | Path) -> RecorderConfig:
        dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
        return cls.model_validate(dados)

    @property
    def tickers_book(self) -> list[AtivoConfig]:
        return [a for a in self.ativos if a.offer_book or a.price_book]
