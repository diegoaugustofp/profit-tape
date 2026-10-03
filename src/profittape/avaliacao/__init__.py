"""AVALIACAO dos EAs: resultado, drawdown, capital e evolucao da ficha (v4.18).

Fronteira (imposta por tests/test_avaliacao_fronteira.py): este pacote le ARQUIVOS --
`operacoes.csv`, `dias.csv`, `eas_config.csv`, `docs/eas/metas.yaml`, as fichas e o `git log`
delas -- e NUNCA importa codigo de EA, record, DLL, pipeline ou storage. Assim ele pode sair
deste repositorio (mover a pasta) sem arrastar nada, e uma avaliacao nao herda os defeitos do
codigo que ela julga. Criterio de avaliacao tem UMA fonte: a ficha (via metas.yaml)."""
