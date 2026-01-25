param(
    [string]$LogDir = "logs",
    [int]$SeqLen = 60,
    [int]$HorizonDays = 5,
    [double]$RiseThreshold = 0.10,
    [int]$Epochs = 30,
    [string]$ModelOutDir = "d:/stock/shared_models",
    [double]$PosWeight = 0.0
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$configs = @(
    @{ hidden = 256; layers = 2 },
    @{ hidden = 512; layers = 2 },
    @{ hidden = 256; layers = 3 },
    @{ hidden = 512; layers = 3 }
)

function Invoke-Train {
    param(
        [int]$Hidden,
        [int]$Layers
    )

    $tag = "kr_${Hidden}_${Layers}"
    $modelPath = Join-Path $ModelOutDir "model_${tag}.pt"
    $logPath = Join-Path $LogDir "${tag}.log"

    $args = @(
        "model_kr.py",
        "--seq-len", $SeqLen,
        "--horizon-days", $HorizonDays,
        "--rise-threshold", $RiseThreshold,
        "--epochs", $Epochs,
        "--log-codes",
        "--model-out", $modelPath,
        "--hidden-size", $Hidden,
        "--num-layers", $Layers
    )
    if ($PosWeight -gt 0) {
        $args += @("--pos-weight", $PosWeight)
    }

    Write-Host ">> python -u $($args -join ' ')"
    $env:PYTHONUNBUFFERED = "1"
    & python -u @args 2>&1 | Tee-Object -FilePath $logPath

    return $logPath
}

function Get-MinValLoss {
    param([string]$LogPath)

    $vals = Select-String -Path $LogPath -Pattern "val_loss=" | ForEach-Object {
        if ($_.Line -match "val_loss=([0-9.]+)") { [double]$matches[1] }
    }
    if ($null -eq $vals -or $vals.Count -eq 0) { return $null }
    return ($vals | Measure-Object -Minimum).Minimum
}

$results = @()
foreach ($cfg in $configs) {
    $log = Invoke-Train -Hidden $cfg.hidden -Layers $cfg.layers
    $minVal = Get-MinValLoss -LogPath $log
    $results += [pscustomobject]@{
        hidden = $cfg.hidden
        layers = $cfg.layers
        min_val_loss = $minVal
        log = $log
    }
}

$results | Sort-Object min_val_loss | Format-Table -AutoSize
