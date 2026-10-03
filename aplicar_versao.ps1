<#
.SYNOPSIS
  Aplica um bundle incremental do profit-tape: fetch da tag, merge e push.

.EXAMPLE
  .\aplicar_versao.ps1 3.79
  .\aplicar_versao.ps1 v3.79
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Versao,

    [string]$Repo = "C:\projetos\profit-tape",

    [string]$PastaBundles = "C:\projetos"
)

$Versao = $Versao.TrimStart("v", "V")
if ($Versao -notmatch '^\d+\.\d+$') {
    Write-Error "Versao invalida: '$Versao'. Use o formato 3.79."
    exit 1
}

$tag    = "entregue-v$Versao"
$bundle = Join-Path $PastaBundles "profit-tape-incremento-v$Versao.bundle"

function Passo([string]$titulo, [scriptblock]$comando) {
    Write-Host ""
    Write-Host "==> $titulo" -ForegroundColor Cyan
    & $comando
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FALHOU: $titulo (codigo $LASTEXITCODE). Nada depois disso foi executado." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

if (-not (Test-Path $bundle)) {
    Write-Error "Bundle nao encontrado: $bundle"
    exit 1
}

Set-Location $Repo

Passo "Verificando bundle" { git bundle verify $bundle }

Passo "1/3 fetch $tag" { git fetch $bundle "refs/tags/${tag}:refs/tags/${tag}" }

Passo "2/3 merge $tag" { git merge $tag }

# Protecao contra orfanar commit feito pela web (engenharia 3.3):
# so faz push se o main remoto ja estiver contido no HEAD local.
Passo "Conferindo origin/main" { git fetch origin }
git merge-base --is-ancestor origin/main HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "PARADO antes do push: origin/main tem commits que o seu HEAD nao tem." -ForegroundColor Yellow
    Write-Host "Provavel commit feito pela web. Resolva com:" -ForegroundColor Yellow
    Write-Host "    git merge origin/main"
    Write-Host "    git push origin HEAD:main --tags"
    exit 1
}

Passo "3/3 push" { git push origin HEAD:main --tags }

Write-Host ""
Write-Host "Versao $Versao aplicada e enviada." -ForegroundColor Green
git log --oneline -3
