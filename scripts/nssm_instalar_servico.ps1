<#
.SYNOPSIS
    Instala/reconfigura o profit-tape record como servico Windows via NSSM.

.DESCRIPTION
    IDEMPOTENTE: pode ser rodado de novo a qualquer momento para reaplicar a
    configuracao (remove o servico existente e recria do zero).

    O contrato de exit code do processo ja' esta correto para o NSSM
    diferenciar por si so' "hoje acabou" de "quebrou":
      - 0 = encerramento LIMPO (horario agendado OU sinal de parada externo)
      - 1 = excecao nao tratada (crash de verdade)
    Por isso: AppExit 0 -> Exit (nao reinicia sozinho no fim do dia normal);
    AppExit Default -> Restart (qualquer outro codigo reinicia).

    O servico fica em modo MANUAL (Start=SERVICE_DEMAND_START) de proposito:
    quem decide QUANDO come?ar o dia e' o schtasks de 08:50 chamando
    `nssm start`, exatamente como hoje. O NSSM so' assume a partir dai',
    supervisionando durante o pregao — reinicio automatico se cair no meio
    do dia, sem esperar ate' o dia seguinte.

.PARAMETER NssmPath
    Caminho do nssm.exe. Baixe em https://nssm.cc/download (a versao 2.24
    tem os binarios win32/win64), extraia, e aponte para o executavel — ou
    coloque a pasta no PATH e use so' "nssm.exe".

.PARAMETER ProjetoDir
    Raiz do projeto (onde ficam .venv, config, logs).

.PARAMETER ContaServico
    Conta sob a qual o servico roda. Default: LocalSystem (mais simples, sem
    senha). SE a ProfitDLL falhar ao conectar rodando como servico (comum em
    DLLs de plataforma de trading que esperam contexto de usuario logado —
    LocalSystem NAO tem sessao de desktop interativa), rode este script de
    novo com -ContaServico ".\<seu_usuario_windows>" — ele vai pedir a senha
    de forma segura (Read-Host -AsSecureString, nunca aparece na tela nem
    fica salva em texto puro neste script).

.EXAMPLE
    .\nssm_instalar_servico.ps1 -NssmPath C:\ferramentas\nssm\nssm.exe

.EXAMPLE
    # se o LocalSystem nao conseguir conectar na ProfitDLL:
    .\nssm_instalar_servico.ps1 -NssmPath C:\ferramentas\nssm\nssm.exe -ContaServico ".\diego"
#>
param(
    [string]$NssmPath = "nssm.exe",
    [string]$ServiceName = "profit-tape-record",
    [string]$ProjetoDir = "C:\projetos\profit-tape",
    [string]$ContaServico = "",
    [int]$RestartDelayMs = 30000
)

$ErrorActionPreference = "Stop"

$exe = Join-Path $ProjetoDir ".venv\Scripts\profit-tape.exe"
$configPath = Join-Path $ProjetoDir "config\recorder.yaml"
$logDir = Join-Path $ProjetoDir "logs"
$logFile = Join-Path $logDir "record_diario.jsonl"

if (-not (Test-Path $exe)) {
    throw "Nao achei $exe -- confirme ProjetoDir e se 'pip install -e .[dev]' ja' rodou."
}
if (-not (Test-Path $configPath)) {
    throw "Nao achei $configPath -- copie e preencha config\recorder.example.yaml antes."
}
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "Removendo servico existente (se houver) para reaplicar do zero..."
& $NssmPath stop $ServiceName 2>$null | Out-Null
& $NssmPath remove $ServiceName confirm 2>$null | Out-Null

Write-Host "Instalando '$ServiceName'..."
& $NssmPath install $ServiceName $exe "record" "-c" $configPath "--log-file" $logFile

& $NssmPath set $ServiceName AppDirectory $ProjetoDir
& $NssmPath set $ServiceName DisplayName "profit-tape record (B3 tape/book)"
& $NssmPath set $ServiceName Description "Gravador de tape e offer book via ProfitDLL. Manual: iniciado pelo schtasks 08:50, supervisionado pelo NSSM durante o pregao."

# MANUAL de proposito -- o schtasks decide quando o dia comeca.
& $NssmPath set $ServiceName Start SERVICE_DEMAND_START

# O CONTRATO QUE IMPORTA: 0 nao reinicia (fim de dia normal ou stop pedido),
# qualquer outro codigo reinicia (crash de verdade).
& $NssmPath set $ServiceName AppExit 0 Exit
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay $RestartDelayMs

# stdout/stderr do NSSM sao so' para capturar falhas ANTES do nosso proprio
# --log-file existir (ex.: python.exe nem conseguiu subir) -- nosso logging
# estruturado continua sendo a fonte de verdade operacional.
$nssmStdout = Join-Path $logDir "nssm_stdout.log"
$nssmStderr = Join-Path $logDir "nssm_stderr.log"
& $NssmPath set $ServiceName AppStdout $nssmStdout
& $NssmPath set $ServiceName AppStderr $nssmStderr
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760

if ($ContaServico -ne "") {
    $senha = Read-Host -AsSecureString "Senha da conta $ContaServico"
    $senhaPlana = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($senha))
    & $NssmPath set $ServiceName ObjectName $ContaServico $senhaPlana
    Write-Host "Servico configurado para rodar como $ContaServico."
    Write-Host "NOTA: essa conta precisa do direito 'Log on as a service' -- "
    Write-Host "se o `nssm start` falhar com erro 1069/1053, adicione o"
    Write-Host "direito em: secpol.msc -> Local Policies -> User Rights"
    Write-Host "Assignment -> Log on as a service."
} else {
    Write-Host "Servico configurado para rodar como LocalSystem (padrao)."
    Write-Host "Se a ProfitDLL falhar ao conectar (comum -- LocalSystem nao"
    Write-Host "tem sessao de desktop), rode este script de novo com"
    Write-Host "-ContaServico '.\<seu_usuario>'."
}

Write-Host ""
Write-Host "=== Pronto. Proximos passos ==="
Write-Host "1. Teste manual:  nssm start $ServiceName"
Write-Host "2. Confira:       nssm status $ServiceName"
Write-Host "3. Veja o log:    Get-Content $logFile -Wait -Tail 20"
Write-Host "4. Pare o teste:  nssm stop $ServiceName"
Write-Host "5. So' depois de confirmar que conecta e grava, atualize o"
Write-Host "   schtasks de inicio para chamar 'nssm start $ServiceName'"
Write-Host "   em vez do profit-tape.exe direto (ver docs/NSSM_SERVICO.md)."
