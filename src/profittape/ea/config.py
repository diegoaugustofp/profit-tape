"""
Config do EA.

CORRECAO DE DESENHO (2026-08-24, operador identificou): a versao anterior
tinha CredenciaisEA com activation_key/user/password SEPARADOS do record,
como se existisse uma "segunda credencial de DLL". ERRADO -- e' o mesmo
login do Diego (DLLInitializeLogin usa as MESMAS 3 credenciais que
DLLInitializeMarketLogin, so' habilita mais servicos, roteamento incluso).
Nao ha duas contas de DLL: ha' UM login, e dentro dele, MULTIPLAS CONTAS
DE ROTEAMENTO (real e simulacao), reveladas via GetAccount()/AccountCallback
e identificadas por (pwcIDAccount, pwcIDCorretora) — confirmado no manual,
secao GetAccount / TAccountCallback.

A seguranca real (nao operar com dinheiro de verdade sem querer) NAO vem de
credencial de DLL separada -- vem de qual CONTA (IDAccount) e' passada para
SendBuyOrder/SendSellOrder/SendZeroPosition. E' esse o parametro que precisa
de default seguro e confirmacao explicita para trocar.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoteamentoConfig(BaseSettings):
    """
    pwcSenha e' a "senha de roteamento" -- distinta da senha de login da
    DLL, exigida especificamente para enviar ordem (medida de seguranca do
    lado da corretora/B3, nao do protocolo Nelogade em si).

    id_account_demo / id_account_real: os DOIS pwcIDAccount que o
    GetAccount() do Diego retorna. pwcIDCorretora normalmente e' o mesmo
    para as duas (mesma corretora, XP), mas o campo existe por conta caso
    real e demo estejam em corretoras diferentes.
    """
    model_config = SettingsConfigDict(env_prefix="ROTEAMENTO_", env_file=".env",
                                      extra="ignore")

    senha_roteamento: str = ""
    id_corretora: str = ""
    id_account_demo: str = ""
    id_account_real: str = ""

    def conta_para(self, usar_conta_real: bool) -> str:
        """
        Ponto UNICO de decisao real-vs-demo no codigo inteiro. Qualquer
        chamada de envio de ordem passa por aqui -- nunca hardcode
        id_account_real direto numa chamada de SendOrder.
        """
        if usar_conta_real:
            if not self.id_account_real:
                raise SystemExit(
                    "usar_conta_real=True mas ROTEAMENTO_ID_ACCOUNT_REAL "
                    "nao esta configurado -- nao ha' como confirmar que "
                    "e' a conta certa. Configure explicitamente antes."
                )
            return self.id_account_real
        if not self.id_account_demo:
            raise SystemExit(
                "ROTEAMENTO_ID_ACCOUNT_DEMO nao configurado -- rode "
                "GetAccount() uma vez (ver docs/EA_ARQUITETURA.md) e "
                "preencha o .env antes de rodar o EA, mesmo em dry_run."
            )
        return self.id_account_demo


class SinalConfig(BaseModel):
    """
    Um sinal operavel = uma linha do relatorio de quintis que passou no
    funil completo (research + quintis + teste de significancia). NUNCA
    adicione um sinal aqui so' porque o IC deu 'segue' -- precisa ter
    passado pela tabela de quintis com o custo REAL da conta.
    """
    feature: str                    # ex.: "z_agf_3"
    horizonte: int                  # barras (ex.: 3)
    agent_id: int                   # ex.: 3 (XP) -- o agente cujo fluxo gera o sinal
    threshold_entrada: float        # o EXTREMO validado, nao um meio-termo
                                    # "mais sensivel" -- ver decisao.py
    direcao: str                    # "contrarian" ou "momentum"
    # Restricao de lado (2026-08-27, decisao PRE-REGISTRADA -- ver
    # docs/RESEARCH_PLANO.md, secao "Restricao de direcao: venda apenas"):
    # z_agf_3 h=3 mostrou assimetria real e convergente (MAE n=300 OOS +
    # EA replay n=163/295) -- lado de venda com edge (+16 a +20 pts/op),
    # lado de compra SEM edge (-25 a -29 pts/op). "ambos" preserva o
    # comportamento historico (default, nunca muda sozinho); "venda" ou
    # "compra" restringe -- NUNCA mudar sem essa mesma disciplina de
    # pre-registro para outro sinal/decisao.
    lado_permitido: str = "ambos"   # "ambos" | "compra" | "venda"
    # Rota B (2026-08-27, PRE-REGISTRADA -- ver docs/RESEARCH_PLANO.md
    # "Rota B: par CONGELADO"). None (default) = Rota A pura, comportamento
    # historico intacto. Se AMBOS setados, adiciona saida por alvo/stop
    # mais apertado PARALELA a saida por tempo (nao substitui) -- qualquer
    # um dos tres (stop_rota_b, alvo, tempo) que disparar primeiro fecha a
    # posicao. Par especifico deste sinal (z_agf_3 h=3, venda) -- NUNCA
    # generalizar para outro sinal sem medir o proprio MAE/MFE dele.
    alvo_pontos: float | None = None
    stop_rota_b_pontos: float | None = None


class RiscoConfig(BaseModel):
    """
    Framework de gestao de risco do operador (2026-08-26, registrado em
    docs/EA_ARQUITETURA.md): preservacao de capital, mao fixa, expectativa
    matematica sobre taxa de acerto. Defaults = day trade de futuros
    (capital minimo R$5.000, risco max 2%, WIN a R$0,20/ponto).
    """
    capital: float = 5000.0
    risco_max_pct: float = 0.02
    valor_ponto_reais: float = 0.20      # WIN; acoes seria 1.0 (R$/ponto=R$)
    max_perdas_consecutivas: int = 3     # regra de ouro: 3 perdas -> para ate amanha

    @property
    def stop_catastrofico_pontos(self) -> float:
        """Derivado, nao configurado: 2% de R$5.000 = R$100 = 500 pts com
        1 contrato de WIN. E' o SEGURO do capital (cenario de cauda), NAO
        um stop tatico -- a saida normal da Rota A e' por TEMPO (horizonte
        do sinal), fiel ao procedimento que o research validou."""
        return (self.capital * self.risco_max_pct) / self.valor_ponto_reais



class EAConfig(BaseModel):
    symbol: str
    volume_barra: int               # CONGELADO do features.parquet que validou
                                    # o sinal -- nunca recalculado ao vivo
    janela_z: int
    sinais: list[SinalConfig]
    tamanho_posicao: int = 1        # contratos. Fixo ate' ter gestao de risco.
    custo_pontos_estimado: float = 11.0
    dry_run: bool = True            # NUNCA False sem decisao explicita
    usar_conta_real: bool = False   # NUNCA True sem decisao explicita e
                                    # documentada -- default e' SEMPRE demo
    risco: RiscoConfig = RiscoConfig()

    @classmethod
    def from_yaml(cls, caminho: Path) -> EAConfig:
        import yaml
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
        return cls(**dados)
