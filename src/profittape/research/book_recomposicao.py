"""
RECOMPOSICAO NO LIVRO — passo 1, v2 (2026-09-19).

A hipotese do iceberg na FONTE CERTA (no tape de negocios ela era DADO
INSUFICIENTE: so' ha' o que executou).

CONTRAPARTE: quem negocia contra profundidade que nao ve. Uma oferta que
SAI do livro (consumida ou cancelada) e cujo lugar e' reposto pelo MESMO
agente, no MESMO preco e com o MESMO tamanho, em segundos, e' alguem
defendendo aquele nivel com capital.

POR QUE A v1 FOI REFEITA (sem nunca ter sido interpretada)
----------------------------------------------------------
A v1 contava "insercoes de mesmo tamanho no mesmo preco". Tres defeitos,
todos de VALIDEZ:

1. **O manual da DLL diz que fora de `atAdd` os campos escalares --
   inclusive `dPrice` -- NAO sao garantidos** (o mesmo motivo pelo qual
   `atFullBook` ja' era descartado na origem). A v1 usava `action in
   (ADD, EDIT)` como se EDIT trouxesse preco valido.
2. Nao exigia que fosse a MESMA ordem nem o mesmo agente: qualquer
   oferta de mesmo tamanho entrava na mesma "corrida". Resultado:
   `tamanho_max` de 63.508 num unico (preco, lado, quantidade) -- isso
   e' o preco mais negociado do dia acumulando lote 1, nao ordem
   defendendo nivel. Mesmo erro que o Times & Trades expos no iceberg
   do tape.
3. Lia o RAW sem deduplicar -- e duplicata e' literalmente "a oferta
   apareceu duas vezes", que infla recarga por construcao.

v3: LIVRO RECONSTRUIDO POR POSICAO (2026-09-21) -- substitui a v2
------------------------------------------------------------------
A v2 deu ZERO recargas em 8 dias. Diagnostico no dado real (17/09):
`DELETE` e `DELETE_FROM` chegam com `offer_id`, preco e quantidade
ZERADOS em 100% dos casos -- so' vem `side` e `position`. A remocao na DLL
e' POSICIONAL. A v2 casava saida com entrada pelo `offer_id` (sempre 0 no
DELETE), e a juncao dava vazio. Eu tinha aplicado a ressalva do manual ao
PRECO e nao ao `offer_id`, que e' campo escalar do mesmo jeito.

Agora o livro e' reconstruido evento a evento, por lado, como lista
posicional: `ADD` insere na posicao, `DELETE` remove na posicao (e ai' se
SABE qual oferta saiu), `EDIT` troca a quantidade na posicao,
`DELETE_FROM` trunca da posicao em diante (reset, nao consumo: NAO conta
como saida).

DOIS PROBLEMAS DO HISTORICO, TRATADOS E REPORTADOS:

1. **Eventos em PAR.** Ate' a v3.23, o V1 e o V2 do offer book disparavam
   os dois e o raw tem cada evento DUAS vezes (0,2-0,3 ms entre eles).
   Aplicar os dois corromperia as posicoes. Por dia, mede-se a fracao de
   linhas em sequencias de tamanho PAR de linhas identicas (tudo menos
   `ts_recv_ns`): se passar de 90%, o dia e' "dobrado" e cada sequencia e'
   reduzida a` metade. Dias ja' capturados com a correcao nao sao tocados.
2. **Livro inicial desconhecido.** O `atFullBook` e' descartado na origem,
   entao as primeiras remocoes apontam para ofertas que nunca vimos. O
   livro e' preenchido com DESCONHECIDOS nessas posicoes; remover um
   desconhecido conta como `saida_desconhecida`. A fracao sai no
   relatorio -- se for alta, a reconstrucao do dia nao serve.

(historico da v2, mantido abaixo)
v2: ESTADO POR `offer_id`
-------------------------
`ADD` registra (offer_id -> preco, quantidade, agente, lado). `DELETE` /
`DELETE_FROM` resolvem o nivel pelo `offer_id` (sem depender dos campos
do proprio evento). RECARGA = uma SAIDA seguida, em ate' `janela_s`, de
uma ENTRADA com mesmo preco, lado, quantidade e AGENTE. A cadeia de
recargas consecutivas no mesmo nivel e' o que se conta.

LIMITES DECLARADOS
------------------
- `offer_id` pode ser reaproveitado no dia; o estado guarda o ultimo ADD.
- `agente` e' CORRETORA, nao cliente final (confirmado no iceberg do
  tape). Reduz o poder, nao invalida: exigir o mesmo agente ja' e' muito
  mais apertado que nao exigir nada.
- O relogio e' `ts_recv_ns` (recepcao): serve para INTERVALO entre
  eventos proximos, nao para datar contra o trade.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import structlog

from ..domain.enums import BookAction

log = structlog.get_logger(__name__)
_NS = 1_000_000_000
JANELA_S = 5.0
N_MINIMO = 3
_ADD = int(BookAction.ADD)
_SAIDAS = (int(BookAction.DELETE), int(BookAction.DELETE_FROM))
_COLS = ["ts_recv_ns", "action", "side", "price", "quantidade", "agente", "offer_id"]


_COLS_V3 = ["ts_recv_ns", "action", "side", "position", "offer_id", "price",
            "quantidade", "agente"]
_EDIT = int(BookAction.EDIT)
_DELETE = int(BookAction.DELETE)
_DELETE_FROM = int(BookAction.DELETE_FROM)
LIMIAR_DIA_DOBRADO = 0.9


def carregar_book(raiz: Path, symbol: str, dia: dt.date) -> tuple[pd.DataFrame, int]:
    """Le o book do dia NA ORDEM DE CHEGADA (e' a ordem em que a DLL aplicou
    os eventos -- o livro posicional so' faz sentido nela). O segundo valor
    fica 0: a deduplicacao agora e' `desdobrar`, que sabe distinguir par
    duplicado de evento legitimo."""
    pasta = raiz / "book_offer" / f"dt={dia.isoformat()}"
    if not pasta.exists():
        return pd.DataFrame(), 0
    dataset = ds.dataset(pasta, format="parquet", partitioning="hive",
                         exclude_invalid_files=True)
    cols = [c for c in _COLS_V3 if c in dataset.schema.names]
    t: pd.DataFrame = dataset.to_table(filter=ds.field("sym") == symbol,
                                       columns=cols).to_pandas()
    return t.sort_values("ts_recv_ns", kind="stable").reset_index(drop=True), 0


def desdobrar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Desfaz o PAR V1+V2 do historico. Sequencia = linhas consecutivas
    identicas em tudo menos `ts_recv_ns`. Se >= 90% das linhas estao em
    sequencias PARES, o dia e' dobrado e cada sequencia vira a metade."""
    if df.empty:
        return df, {"dia_dobrado": False, "fracao_em_sequencia_par": None,
                    "linhas_removidas": 0}
    chave = [c for c in _COLS_V3 if c != "ts_recv_ns" and c in df]
    igual = np.ones(len(df), dtype=bool)
    igual[0] = False
    for c in chave:
        v = df[c].to_numpy()
        igual[1:] &= v[1:] == v[:-1]
    seq = np.cumsum(~igual) - 1
    tam = np.bincount(seq)
    tam_linha = tam[seq]
    fracao_par = float((tam_linha % 2 == 0).mean())
    dobrado = fracao_par >= LIMIAR_DIA_DOBRADO
    if not dobrado:
        return df, {"dia_dobrado": False, "fracao_em_sequencia_par": round(fracao_par, 4),
                    "linhas_removidas": 0}
    # posicao dentro da sequencia; fica a primeira metade (ceil)
    inicio = np.zeros(len(tam), dtype=np.int64)
    inicio[1:] = np.cumsum(tam)[:-1]
    pos = np.arange(len(df)) - inicio[seq]
    manter = pos < (tam_linha + 1) // 2
    out = df[manter].reset_index(drop=True)
    return out, {"dia_dobrado": True, "fracao_em_sequencia_par": round(fracao_par, 4),
                 "linhas_removidas": int(len(df) - len(out))}


def reconstruir(df: pd.DataFrame, log_a_cada: int = 5_000_000) -> tuple[pd.DataFrame,
                                                                         dict[str, Any]]:
    """
    Livro POSICIONAL, evento a evento, por lado, na semantica do MANUAL DA
    DLL (TPriceBookCallbackV2, que o offer book segue): "todos os ajustes que
    dependem de nPosition se referem a' posicao A PARTIR DO FINAL DA LISTA
    (em listas com inicio em 0, size - nPosition - 1)".

    Consequencia: o FIM da lista e' o TOPO do livro (posicao 0 = melhor
    oferta). ATENCAO -- correcao de registro: indexar do inicio ou do fim
    e' ESPELHO (as contagens saem identicas, conferido); a v3.24 so' mudou a
    orientacao da checagem de ordem. O que produzia 3,7 BILHOES de
    "removidas" era ler o `DELETE_FROM` como corte do FUNDO -- ele corta o
    TOPO (ver o corpo).

      ADD p        -> insere no indice size - p (a nova oferta fica na posicao p)
      DELETE p     -> remove o indice size - p - 1
      EDIT p       -> troca a quantidade no indice size - p - 1
      DELETE_FROM p-> remove as p+1 MELHORES (o TOPO: indice size-p-1 ate' o
                      fim). E' VARREDURA por agressao -- CONSUMO -- e as
                      ofertas removidas contam como SAIDAS (ver o corpo).

    AUTOVERIFICACAO: cada ADD e' conferido contra os vizinhos conhecidos. O
    lado de compra tem que crescer em preco rumo ao fim (melhor compra =
    maior preco, no topo); o de venda, decrescer. `insercoes_fora_de_ordem`
    sai no relatorio: com a semantica certa fica perto de zero; com a
    errada, dispara.
    """
    livro: dict[int, list[Any]] = {0: [], 1: []}
    n = len(df)
    s_ts = np.empty(n, dtype=np.int64)
    s_pr = np.empty(n, dtype=np.float64)
    s_sd = np.empty(n, dtype=np.int64)
    s_q = np.empty(n, dtype=np.int64)
    s_ag = np.empty(n, dtype=np.int64)
    k = 0
    desconhecidas = edit_desconhecido = truncadas = 0
    adds_conferidos = fora_de_ordem = 0
    por_varredura = 0
    cols = [df[c].tolist() for c in ("ts_recv_ns", "action", "side", "position",
                                     "price", "quantidade", "agente")]
    for i, (ts, acao, lado, pos, preco, qtd, ag) in enumerate(zip(*cols, strict=True)):
        lista = livro.get(lado)
        if lista is None:
            continue
        tam = len(lista)
        if acao == _ADD:
            if pos > tam:                       # mais fundo que o conhecido
                lista[:0] = [None] * (pos - tam)
                tam = pos
            idx = tam - pos
            lista.insert(idx, (preco, qtd, ag))
            # vizinhos: idx-1 e' mais FUNDO, idx+1 e' mais perto do TOPO
            fundo = lista[idx - 1] if idx - 1 >= 0 else None
            topo = lista[idx + 1] if idx + 1 < len(lista) else None
            if fundo is not None or topo is not None:
                adds_conferidos += 1
                if lado == 0:   # compra: preco sobe rumo ao topo
                    ruim = ((fundo is not None and fundo[0] > preco)
                            or (topo is not None and topo[0] < preco))
                else:           # venda: preco desce rumo ao topo
                    ruim = ((fundo is not None and fundo[0] < preco)
                            or (topo is not None and topo[0] > preco))
                fora_de_ordem += int(ruim)
        elif acao == _DELETE:
            if pos < tam:
                saiu = lista.pop(tam - pos - 1)
                if saiu is None:
                    desconhecidas += 1
                else:
                    s_ts[k], s_pr[k], s_sd[k], s_q[k], s_ag[k] = ts, saiu[0], lado, saiu[1], saiu[2]
                    k += 1
            else:
                desconhecidas += 1              # oferta mais funda que o conhecido
        elif acao == _EDIT:
            if pos < tam and lista[tam - pos - 1] is not None:
                p_, _, a_ = lista[tam - pos - 1]
                lista[tam - pos - 1] = (p_, qtd, a_)
            else:
                edit_desconhecido += 1
        elif acao == _DELETE_FROM:
            # REMOVE AS p+1 MELHORES OFERTAS (o TOPO): do indice size-p-1 ATE' O
            # FIM da lista. Leitura corrigida em 21/09: a 1a versao removia o
            # FUNDO (posicoes >= p). No dado real (17/09, 920.904 eventos) NAO
            # existe nenhum DELETE_FROM com p = 0 -- remover so' a melhor e' um
            # DELETE 0 -- e a distribuicao decai a partir de 1 (270 k, 163 k,
            # 106 k...): assinatura de VARREDURA do topo por ordem agressora.
            # Logo e' CONSUMO, e as ofertas removidas SAO saidas.
            corte = tam - pos - 1
            if corte < 0:                        # topo p+1 maior que o conhecido
                desconhecidas += -corte
                corte = 0
            removidas = lista[corte:]
            del lista[corte:]
            truncadas += len(removidas)
            for saiu in removidas:
                if saiu is None:
                    desconhecidas += 1
                else:
                    s_ts[k], s_pr[k], s_sd[k], s_q[k], s_ag[k] = ts, saiu[0], lado, saiu[1], saiu[2]
                    k += 1
                    por_varredura += 1
        if log_a_cada and i and i % log_a_cada == 0:
            log.info("book_recomposicao.reconstruindo", eventos=i, de=n, saidas=k,
                     desconhecidas=desconhecidas, fora_de_ordem=fora_de_ordem)
    add = df[df["action"] == _ADD]
    entradas = pd.DataFrame({"ts_recv_ns": add["ts_recv_ns"].to_numpy(),
                             "price": add["price"].to_numpy(dtype=np.float64),
                             "side": add["side"].to_numpy(dtype=np.int64),
                             "quantidade": add["quantidade"].to_numpy(dtype=np.int64),
                             "agente": add["agente"].to_numpy(dtype=np.int64),
                             "entrada": True})
    saidas = pd.DataFrame({"ts_recv_ns": s_ts[:k], "price": s_pr[:k], "side": s_sd[:k],
                           "quantidade": s_q[:k], "agente": s_ag[:k], "entrada": False})
    total_saidas = k + desconhecidas
    cont = {"saidas_atribuidas": k, "saidas_desconhecidas": desconhecidas,
            "fracao_saidas_desconhecidas": (round(desconhecidas / total_saidas, 4)
                                            if total_saidas else None),
            "edit_desconhecido": edit_desconhecido,
            "removidas_por_delete_from": truncadas,
            "saidas_por_varredura": por_varredura,
            "insercoes_conferidas": adds_conferidos,
            "insercoes_fora_de_ordem": fora_de_ordem,
            "fracao_insercoes_fora_de_ordem": (round(fora_de_ordem / adds_conferidos, 4)
                                               if adds_conferidos else None)}
    return pd.concat([entradas, saidas], ignore_index=True), cont


def eventos_de_nivel(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibilidade: desdobra e reconstroi, devolve so' os eventos."""
    ev, _ = reconstruir(desdobrar(df)[0], log_a_cada=0)
    return ev


def _cadeias(ev: pd.DataFrame, janela_ns: int) -> np.ndarray:
    """Tamanho de cada cadeia de RECARGAS: saida seguida de entrada no
    mesmo (preco, lado, quantidade, agente) dentro da janela."""
    if ev.empty:
        return np.array([], dtype=np.int64)
    chave = (ev["price"].to_numpy(dtype=np.float64), ev["side"].to_numpy(dtype=np.int64),
             ev["quantidade"].to_numpy(dtype=np.int64), ev["agente"].to_numpy(dtype=np.int64))
    ts = ev["ts_recv_ns"].to_numpy(dtype=np.int64)
    entrada = ev["entrada"].to_numpy(dtype=bool)
    ordem = np.lexsort((ts, *chave[::-1]))
    p, s_, q, a = (c[ordem] for c in chave)
    t, e = ts[ordem], entrada[ordem]
    mesma = np.empty(len(t), dtype=bool)
    mesma[0] = False
    mesma[1:] = ((p[1:] == p[:-1]) & (s_[1:] == s_[:-1]) & (q[1:] == q[:-1])
                 & (a[1:] == a[:-1]))
    # recarga: entrada logo apos uma SAIDA da mesma chave, dentro da janela
    recarga = np.zeros(len(t), dtype=bool)
    recarga[1:] = mesma[1:] & e[1:] & (~e[:-1]) & ((t[1:] - t[:-1]) <= janela_ns)
    if not recarga.any():
        return np.array([], dtype=np.int64)
    # CADEIA = recargas seguidas no MESMO nivel. Elas nao sao adjacentes no
    # vetor de eventos (entre duas ha' sempre a saida), entao a cadeia se
    # monta sobre as recargas isoladas: quebra quando a chave muda ou
    # quando o intervalo entre duas recargas passa da janela.
    idx = np.flatnonzero(recarga)
    pr, sr, qr, ar, tr = p[idx], s_[idx], q[idx], a[idx], t[idx]
    quebra = np.empty(len(idx), dtype=bool)
    quebra[0] = True
    quebra[1:] = ((pr[1:] != pr[:-1]) | (sr[1:] != sr[:-1]) | (qr[1:] != qr[:-1])
                  | (ar[1:] != ar[:-1]) | ((tr[1:] - tr[:-1]) > janela_ns))
    return np.bincount(np.cumsum(quebra) - 1).astype(np.int64)


def medir_dia(raiz: Path, symbol: str, dia: dt.date, janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, semente: int = 1) -> dict[str, Any]:
    t0 = time.monotonic()
    df, _ = carregar_book(raiz, symbol, dia)
    if df.empty:
        return {}
    seg_leitura = round(time.monotonic() - t0, 1)
    deltas_brutos = len(df)
    df, desdob = desdobrar(df)
    ev, cont = reconstruir(df)
    if ev.empty:
        return {}
    janela_ns = int(janela_s * _NS)
    tam = _cadeias(ev, janela_ns)
    # BASELINE: permuta o par (quantidade, agente) entre os eventos, mantendo
    # preco, lado e instante. Formador repondo rotina gera recarga; isto e'
    # o que separa reposicao automatica de nivel defendido.
    rng = np.random.default_rng(semente)
    perm = rng.permutation(len(ev))
    ev_b = ev.copy()
    ev_b["quantidade"] = ev["quantidade"].to_numpy()[perm]
    ev_b["agente"] = ev["agente"].to_numpy()[perm]
    tam_b = _cadeias(ev_b, janela_ns)

    def curva(v: np.ndarray) -> dict[str, int]:
        return {str(n): int((v >= n).sum()) for n in (3, 5, 10, 20, 50)}

    obs, base = curva(tam), curva(tam_b)
    r = {
        "dia": dia.isoformat(), "deltas": int(deltas_brutos),
        "duplicatas_removidas": int(desdob["linhas_removidas"]),
        "dia_dobrado": desdob["dia_dobrado"],
        "fracao_em_sequencia_par": desdob["fracao_em_sequencia_par"],
        **cont,
        "entradas": int(ev["entrada"].sum()), "saidas": int((~ev["entrada"]).sum()),
        "recargas": int(tam.sum()),
        "niveis_defendidos": int((tam >= n_minimo).sum()),
        "cadeia_p50": float(np.median(tam)) if len(tam) else None,
        "cadeia_max": int(tam.max()) if len(tam) else 0,
        "por_limiar": obs, "baseline": base,
        "razao_por_limiar": {n: round((obs[n] + 1) / (base[n] + 1), 3) for n in obs},
        "segundos_leitura": seg_leitura,
        "segundos_total": round(time.monotonic() - t0, 1),
    }
    log.info("book_recomposicao.dia", **{k: v for k, v in r.items()
                                         if k not in ("por_limiar", "baseline",
                                                      "razao_por_limiar")})
    return r


def descrever(raiz: Path, symbol: str, dias: list[dt.date], janela_s: float = JANELA_S,
              n_minimo: int = N_MINIMO, saida: Path | None = None) -> dict[str, Any]:
    linhas = [r for d in dias if (r := medir_dia(raiz, symbol, d, janela_s, n_minimo))]
    if not linhas:
        raise SystemExit(f"nenhum dia com book_offer de {symbol} em {raiz}")
    agregado = {
        "dias": len(linhas),
        "deltas_p50": float(np.median([x["deltas"] for x in linhas])),
        "duplicatas_p50": float(np.median([x["duplicatas_removidas"] for x in linhas])),
        "recargas_p50": float(np.median([x["recargas"] for x in linhas])),
        "niveis_defendidos_p50": float(np.median([x["niveis_defendidos"] for x in linhas])),
        "cadeia_max": int(max(x["cadeia_max"] for x in linhas)),
        "dias_dobrados": int(sum(1 for x in linhas if x["dia_dobrado"])),
        "fracao_insercoes_fora_de_ordem_p50": float(np.median(
            [x["fracao_insercoes_fora_de_ordem"] or 0.0 for x in linhas])),
        "fracao_saidas_desconhecidas_p50": float(np.median(
            [x["fracao_saidas_desconhecidas"] or 0.0 for x in linhas])),
        "por_limiar": {
            n: {"observado_p50": float(np.median([x["por_limiar"][n] for x in linhas])),
                "baseline_p50": float(np.median([x["baseline"][n] for x in linhas])),
                "razao_p50": float(np.median([x["razao_por_limiar"][n] for x in linhas]))}
            for n in linhas[0]["por_limiar"]},
        "segundos_por_dia_p50": float(np.median([x["segundos_total"] for x in linhas])),
    }
    r = {"symbol": symbol, "janela_s": janela_s, "n_minimo": n_minimo,
         "versao": "v3_posicional",
         "agregado": agregado, "por_dia": linhas}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "book_recomposicao.json").write_text(json.dumps(r, indent=2, default=str),
                                                      encoding="utf-8")
    return r
