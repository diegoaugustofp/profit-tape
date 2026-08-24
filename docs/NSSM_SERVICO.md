# Servico supervisionado (NSSM) — desenhado 2026-08-24

Terceira peca da infra, depois do agendamento (schtasks) e dos alertas
(Telegram). Sem mudanca de codigo Python — o contrato de exit code do
`record` ja' estava certo (`run()` devolve 0 em qualquer parada LIMPA
— horario agendado ou sinal externo — e 1 so' em excecao nao tratada).
O NSSM usa esse contrato para decidir sozinho quando reiniciar.

## Por que NSSM e nao "so' Automatic Startup"

Um servico Windows comum ("Automatic") fica sempre ligado, tentando rodar o
tempo todo — errado para um processo que so' deve existir das 08:50 as 18:30.
NSSM resolve isso mantendo o servico em modo **Manual**: o schtasks de 08:50
continua controlando O INICIO do dia (`nssm start` em vez de chamar o exe
direto); a partir dai', o NSSM supervisiona: se o processo cair no meio do
pregao (DLL travou, excecao nao tratada, o que for), reinicia sozinho em
segundos — sem esperar ate' o dia seguinte, que e' o que aconteceria hoje
sem NSSM.

## Instalacao

1. Baixe o NSSM em https://nssm.cc/download (pegue a versao estavel, extraia
   o `.zip`; use o executavel de `win64\nssm.exe` numa maquina 64-bit).
2. Rode o script deste repositorio:
   ```powershell
   cd C:\projetos\profit-tape
   .\scripts\nssm_instalar_servico.ps1 -NssmPath C:\ferramentas\nssm\nssm.exe
   ```
3. Teste manualmente ANTES de tocar no schtasks:
   ```powershell
   nssm start profit-tape-record
   nssm status profit-tape-record        # deve dizer SERVICE_RUNNING
   Get-Content logs\record_diario.jsonl -Wait -Tail 20
   ```
   Confirme no log que aparece `recorder.conectado` e `recorder.subscrito`
   dos ativos — e' a prova de que a ProfitDLL aceitou a conexao rodando
   como servico. Se falhar por causa de sessao interativa (ver secao
   "Se a conexao falhar" abaixo), reconfigure com `-ContaServico`.
4. Pare o teste: `nssm stop profit-tape-record`.

## Teste de resiliencia (fazer isso pelo menos uma vez, fora do pregao real)

O ponto inteiro do NSSM e' o auto-restart em crash. Confirme que funciona
ANTES de confiar nele num pregao de verdade:

```powershell
nssm start profit-tape-record
# pega o PID do processo python real (nao o service host do nssm):
Get-Process python | Select-Object Id, StartTime
# mata a força, simulando um crash de verdade:
Stop-Process -Id <PID> -Force
# espera uns 30-40s (RestartDelayMs) e confirma que voltou:
Start-Sleep -Seconds 40
nssm status profit-tape-record          # deve estar RUNNING de novo
Get-Content logs\record_diario.jsonl -Tail 10   # deve mostrar novo "record iniciado"
```
Se configurou o alerta do Telegram, voce deve ver DUAS mensagens: uma de
encerramento anormal nao chega (foi kill -9, sem chance de rodar o handler
de shutdown) mas a de "record iniciado" da nova instancia sim — e' o sinal
de que o crash-recovery e' silencioso sem alerta explicito de "crashei e
recuperei". Se quiser visibilidade explicita disso, e' um proximo passo
(o NSSM tem AppEvents que podem chamar um script proprio no restart —
nao implementado ainda, fica registrado como possivel proxima melhoria).

## Se a conexao com a ProfitDLL falhar rodando como servico

LocalSystem (o padrao) nao tem sessao de desktop interativa. Algumas DLLs
de plataforma de trading exigem isso (contexto de usuario logado, acesso a
pastas de perfil, etc). Se o log mostrar erro de conexao/login que nao
acontece quando voce roda `profit-tape record` manualmente no mesmo
usuario, reconfigure o servico para rodar como a SUA conta Windows:

```powershell
.\scripts\nssm_instalar_servico.ps1 -NssmPath C:\ferramentas\nssm\nssm.exe -ContaServico ".\diego"
```
Vai pedir a senha da conta de forma segura (nunca aparece na tela). Se der
erro 1069/1053 ao iniciar, a conta precisa do direito "Log on as a service":
`secpol.msc` -> Local Policies -> User Rights Assignment -> Log on as a
service -> adicione o usuario.

## Atualizando o schtasks de inicio

Depois de confirmar que o servico conecta e grava (secao "Instalacao",
passo 3), troque o schtasks existente para chamar `nssm start` em vez do
exe direto:

```powershell
schtasks /Change /TN "profit-tape-record" /TR "nssm.exe start profit-tape-record"
```
(ajuste o caminho do nssm.exe se nao estiver no PATH do sistema)

O horario (08:50), os dias (MON-FRI) e os dois flags de energia continuam
os mesmos — so' o comando executado muda.

### Rede de seguranca opcional: stop tardio

O `record` se auto-encerra as 18:30 (`encerrar_em` no yaml) e o NSSM nao
reinicia depois disso (exit 0 -> Exit). Um `nssm stop` agendado mais tarde
e' redundante mas barato — se algum dia o auto-encerramento falhar por
algum motivo nao previsto, isso garante que o servico nao fica a noite
inteira tentando reconectar:

```powershell
schtasks /Create /TN "profit-tape-record-stop-seguranca" /SC WEEKLY `
  /D MON,TUE,WED,THU,FRI /ST 19:00 `
  /TR "nssm.exe stop profit-tape-record" /RL LIMITED /F
```

## Comandos do dia a dia

| O que | Comando |
|---|---|
| Ver status | `nssm status profit-tape-record` |
| Iniciar na mao | `nssm start profit-tape-record` |
| Parar na mao | `nssm stop profit-tape-record` |
| Ver config atual | `nssm dump profit-tape-record` |
| Editar via GUI | `nssm edit profit-tape-record` |
| Remover o servico | `nssm remove profit-tape-record confirm` |

## O que NAO mudou

- O `vigia` (watchdog externo, `docs/OPERACAO.md`) continua rodando via
  schtasks proprio a cada 5min — ele cobre "nunca iniciou" (schtasks
  ausente/maquina desligada), que e' diferente de "iniciou e caiu no meio",
  que agora e' o NSSM que cobre. Sao camadas complementares, nao
  redundantes.
- O `curate`, `agents`, `features`, `research` continuam manuais (ou via
  schtasks proprio se voce decidir automatizar depois) — nao fazem sentido
  como servico continuo, sao processos de duracao finita.
