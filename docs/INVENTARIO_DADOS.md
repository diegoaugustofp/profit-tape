# Inventário de dados

> **Status:** **NÃO GERADO** — este arquivo é um marcador. O inventário lê os discos do operador
> (`data/raw`, `data/curated`, o disco de backup) e os *dumps*, que o repositório não tem. Gere com o
> comando abaixo; ele substitui este arquivo pelo inventário real, com data, máquina e versão no cabeçalho.

```powershell
profit-tape inventario-dados --backup D:\backup_raw\data\raw --dumps <pasta ou arquivo dos dumps>
```

Confira a letra do disco de backup (`docs/OPERACAO.md` avisa que ela muda entre sessões). Rode **depois
das 18:00**: lê só o rodapé dos parquet, mas varre milhares de arquivos.

**O que é `--dumps`.** *Dump* é o arquivo de **texto** com as linhas que um indicador NTSL escreve no
console do Profit (`PRCBARRA|1150102|900|...`, `ABSBARRA|...`, `VWAPVP|...`) e que você copia à mão: não
é CSV nem parquet. É o "histórico (amostra) out/2015 a dez/2022" do glossário (preço, sem agente). O
projeto **não fixa** a pasta: passe onde você os guardou, ou o arquivo concatenado. Opcional.

**Quando gerar:** não é diário. Antes de formular uma hipótese (quanto dado e qual período há por ativo)
e quando uma coleta terminar. Depois de gerar, faça commit do `.md` e do CSV.

**O que o inventário mostra**
- por ativo: período do `trade` (o *tape*, negócios com agente), dias, linhas e se o ativo é **só trade**
  ou também **book**;
- origem de cada dia: **ao vivo**, **importado** depois (01 a 14/09 foram importados em 15/09) ou
  **misto**; camada (raw local, curated, backup) e lacunas (dias da semana sem dado);
- as **coletas em andamento** de `docs/coletas.yaml` cruzadas com o que há em disco;
- dos dumps: tipo de linha, período, dias, barras por dia e barras **repetidas** (dumps sobrepostos).
