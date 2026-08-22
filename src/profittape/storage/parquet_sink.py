"""
Sink Parquet particionado.

LAYOUT
------
    data/raw/{stream}/dt=YYYY-MM-DD/sym=PETR4/part-0000.parquet

Hive-style, entao DuckDB, pandas e pyarrow.dataset leem com filtro por
particao sem abrir arquivo desnecessario. `dt` primeiro porque quase toda
consulta e' "um dia, varios ativos".

POR QUE `sym=` E NAO `symbol=`
------------------------------
A coluna `symbol` continua gravada DENTRO do arquivo, de proposito: um Parquet
solto, copiado para outra maquina, precisa se descrever sozinho. Mas se a chave
de particao tivesse o mesmo nome, o pyarrow tentaria unir a coluna do arquivo
(dictionary) com a inferida do caminho (string) e falharia ao abrir o dataset:

    ArrowTypeError: Unable to merge: Field symbol has incompatible types

Nome distinto resolve sem abrir mao nem do filtro por particao nem do arquivo
autossuficiente. O custo e' uma coluna redundante na leitura — barato.

ROTACAO
-------
Arquivo fecha quando: muda o dia, estoura `max_rows_per_file`, ou o processo
encerra. Arquivo Parquet so vira legivel quando o footer e' escrito no close —
por isso o writer tambem fecha por tempo ocioso, senao uma queda do processo
as 17h transforma o pregao inteiro em arquivo corrompido.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from ..domain.enums import Stream
from ..domain.schema import schema_for

log = structlog.get_logger(__name__)


def _sanitize(valor: str) -> str:
    """Nome de particao seguro. Ticker de opcao tem caractere estranho."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in valor) or "UNKNOWN"


class PartitionKey(tuple[Stream, str, str]):
    """(stream, data, symbol) — identidade de um arquivo aberto."""

    __slots__ = ()

    def __new__(cls, stream: Stream, dia: str, symbol: str) -> PartitionKey:
        return super().__new__(cls, (stream, dia, symbol))

    @property
    def stream(self) -> Stream:
        return self[0]

    @property
    def dia(self) -> str:
        return self[1]

    @property
    def symbol(self) -> str:
        return self[2]


class _OpenFile:
    __slots__ = ("opened_at", "path_final", "path_tmp", "rows", "writer")

    def __init__(self, writer: pq.ParquetWriter, path_tmp: Path, path_final: Path) -> None:
        self.writer = writer
        self.path_tmp = path_tmp
        self.path_final = path_final
        self.rows = 0
        self.opened_at = datetime.now(UTC)


class ParquetSink:
    """
    Mantem um ParquetWriter aberto por particao ativa.

    Nao e' thread-safe por escolha: so o writer thread toca nisto. Adicionar
    lock aqui seria pagar por seguranca que a arquitetura ja garante.
    """

    def __init__(
        self,
        raiz: Path,
        max_rows_per_file: int = 5_000_000,
        compressao: str = "zstd",
        nivel_compressao: int = 3,
    ) -> None:
        self.raiz = Path(raiz)
        self.max_rows_per_file = max_rows_per_file
        self.compressao = compressao
        self.nivel_compressao = nivel_compressao
        self._abertos: dict[PartitionKey, _OpenFile] = {}
        self._seq: dict[PartitionKey, int] = {}
        # Total de arquivos abertos na vida do sink. O writer compara antes e
        # depois de cada lote para distinguir lote lento por CRIACAO de
        # arquivo (spin-up de HDD USB: esperado) de lote lento por vazao.
        self.aberturas = 0

    # ------------------------------------------------------------------
    def write(self, stream: Stream, dia: str, symbol: str, colunas: dict[str, list[Any]]) -> int:
        """Grava um lote homogeneo. Devolve o numero de linhas escritas."""
        schema = schema_for(stream)
        batch = pa.record_batch(
            [pa.array(colunas[f.name], type=f.type) for f in schema],
            schema=schema,
        )
        key = PartitionKey(stream, dia, symbol)
        aberto = self._abertos.get(key)
        if aberto is None:
            aberto = self._open(key, schema)
        elif aberto.rows >= self.max_rows_per_file:
            self._close_one(key)
            aberto = self._open(key, schema)

        aberto.writer.write_batch(batch)
        aberto.rows += batch.num_rows
        return batch.num_rows

    # ------------------------------------------------------------------
    def _open(self, key: PartitionKey, schema: pa.Schema) -> _OpenFile:
        pasta = (
            self.raiz
            / key.stream.value
            / f"dt={key.dia}"
            / f"sym={_sanitize(key.symbol)}"
        )
        pasta.mkdir(parents=True, exist_ok=True)
        seq = self._seq.get(key)
        if seq is None:
            # Descobre o proximo indice livre OLHANDO O DISCO, nao a memoria.
            # Bug latente real: dois processos (ou dois runs) na mesma particao
            # comecavam ambos em part-0000; o segundo colidia no rename — ou,
            # antes do rename-on-close, SOBRESCREVIA o dado do primeiro em
            # silencio. Numeracao pertence ao diretorio, nao ao processo.
            usados = []
            for arq in pasta.glob("part-*.parquet*"):
                try:
                    usados.append(int(arq.name.split("-")[1].split(".")[0]))
                except (IndexError, ValueError):
                    continue
            seq = max(usados) + 1 if usados else 0
        self._seq[key] = seq + 1
        # Escreve com sufixo .inprogress e renomeia no close. Incidente real:
        # um processo morto a forca deixou um part-0000.parquet sem footer, e
        # o arquivo truncado era INDISTINGUIVEL de um pronto ate o pyarrow
        # explodir na leitura. Com o sufixo, incompleto se declara incompleto:
        # leitores globam *.parquet e nunca o veem, e sobra de crash aparece
        # no disco como *.inprogress — evidencia, nao armadilha.
        final = pasta / f"part-{seq:04d}.parquet"
        caminho = pasta / f"part-{seq:04d}.parquet.inprogress"
        self.aberturas += 1
        writer = pq.ParquetWriter(
            caminho,
            schema,
            compression=self.compressao,
            compression_level=self.nivel_compressao,
            # Estatistica por coluna permite pular row group na leitura por
            # janela de tempo, que e' o filtro mais comum em dado de tape.
            write_statistics=True,
        )
        aberto = _OpenFile(writer, caminho, final)
        self._abertos[key] = aberto
        return aberto

    def _close_one(self, key: PartitionKey) -> None:
        aberto = self._abertos.pop(key, None)
        if aberto is not None:
            aberto.writer.close()
            # INCIDENTE CRITICO (2026-08-21): 96 arquivos ficaram sem footer no
            # G: USB. Causa: writer.close() escreve o footer, mas em disco
            # externo/USB com spin-down o footer fica no cache de escrita do SO
            # e o rename seguinte "tem sucesso" renomeando um arquivo cujo
            # footer ainda esta em RAM. Quando o disco dorme/desconecta, o
            # footer se perde e o parquet fica ilegivel — os dados (row groups)
            # sobrevivem, mas sem o indice final nenhuma ferramenta le.
            #
            # Defesa: fsync do arquivo ANTES do rename, forcando o footer ao
            # disco fisico. rename-on-close so' e' atomico se o conteudo ja'
            # estiver duravel — senao a atomicidade e' do nome, nao do dado.
            try:
                fd = os.open(aberto.path_tmp, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError as exc:
                # fsync pode falhar em alguns sistemas de arquivo; nao mascara
                # o dado, mas registra para o operador saber que a durabilidade
                # nao foi confirmada neste arquivo.
                log.warning("sink.fsync_falhou", arquivo=str(aberto.path_tmp),
                            erro=str(exc),
                            aviso="footer pode nao estar duravel; risco em USB")
            aberto.path_tmp.rename(aberto.path_final)

    def close_idle(self, idade_maxima_s: float) -> list[Path]:
        """
        Fecha arquivos abertos ha muito tempo, tornando-os legiveis.

        Sem isso, um arquivo permanece sem footer o pregao inteiro e uma queda
        do processo o perde por completo.
        """
        agora = datetime.now(UTC)
        fechados: list[Path] = []
        for key in list(self._abertos):
            aberto = self._abertos[key]
            if (agora - aberto.opened_at).total_seconds() >= idade_maxima_s:
                fechados.append(aberto.path_final)
                self._close_one(key)
        return fechados

    def close(self) -> list[Path]:
        caminhos = [a.path_final for a in self._abertos.values()]
        for key in list(self._abertos):
            self._close_one(key)
        return caminhos

    @property
    def arquivos_abertos(self) -> int:
        return len(self._abertos)

    @property
    def linhas_por_stream(self) -> dict[str, int]:
        acc: dict[str, int] = {}
        for key, aberto in self._abertos.items():
            acc[key.stream.value] = acc.get(key.stream.value, 0) + aberto.rows
        return acc
