# Inventário de dados

> **Status:** **NÃO GERADO** — este arquivo é um marcador. O inventário lê os discos do operador
> (`data/raw`, `data/curated`, o disco de backup) e os *dumps*, que o repositório não tem.

**Antes de rodar (a v4.23 travou uma máquina; leia `docs/OPERACAO.md`, incidente de 03/10).**
1. **Pare o `record`.** O comando recusa rodar se `logs/record_diario.jsonl` foi escrito nos últimos 2 min.
2. Primeiro o plano, sem abrir nenhum parquet:

```powershell
profit-tape inventario-dados --nivel listar
```

3. Depois o padrão (`leve`: só os rodapés de `curated/trade`):

```powershell
profit-tape inventario-dados --backup D:\backup_raw\data\raw --dumps <pasta ou arquivo dos dumps>
```

`--nivel trade` (lê também o raw/trade) e `--nivel completo` (book e backup) só com o record parado e depois
de ver o plano; há teto de 20.000 arquivos (`--max-arquivos`). Confira a letra do disco de backup.

**O que é `--dumps`.** *Dump* é o arquivo de **texto** com as linhas que um indicador NTSL escreve no
console do Profit (`PRCBARRA|1150102|900|...`, `ABSBARRA|...`, `VWAPVP|...`) e que você copia à mão: não é CSV
nem parquet. É o "histórico (amostra) out/2015 a dez/2022" do glossário (preço, sem agente). O projeto **não
fixa** a pasta: passe onde você os guardou, ou o arquivo concatenado. Opcional.

**Quando gerar:** não é diário. Antes de formular uma hipótese e quando uma coleta terminar. Depois de gerar,
faça commit do `.md` e do CSV.
