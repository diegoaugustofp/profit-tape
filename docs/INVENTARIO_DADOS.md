# Inventário de dados

> **Status:** **NÃO GERADO** — este arquivo é um marcador. O inventário lê os discos do operador
> (`data/raw`, `data/curated`, o disco de backup), que o repositório não tem. Gere com o comando
> abaixo; ele substitui este arquivo pelo inventário real, com data, máquina e versão no cabeçalho.

```powershell
profit-tape inventario-dados --backup D:\backup_raw\data\raw --dumps <pasta dos historicos de preco>
```

(confira a letra do disco de backup: `docs/OPERACAO.md` avisa que ela muda entre sessões; `--dumps` é
opcional.) Rode **depois das 18:00** — lê só o rodapé dos parquet, mas varre milhares de arquivos.

**Quando gerar:** não é diário. Antes de formular uma hipótese (para saber quanto dado e qual
período há por ativo) e quando uma coleta terminar. Depois de gerar, faça commit do `.md` e do CSV.

**O que o inventário mostra**
- por ativo: período do `trade` (o *tape*, negócios com agente), dias, linhas e se o ativo é
  **só trade** ou também **book**;
- origem de cada dia: **ao vivo**, **importado** depois (01 a 14/09 foram importados em 15/09) ou
  **misto**;
- em que camada está (raw local, curated, backup) e as lacunas (dias da semana sem dado);
- as **coletas em andamento** de `docs/coletas.yaml` cruzadas com o que existe em disco (por
  exemplo, em quantos dias os dois contratos do WDO negociaram juntos).
