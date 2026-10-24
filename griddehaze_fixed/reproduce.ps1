param(
    [string]$Python = 'python',
    [string]$Out = '',
    [string]$FogZip = '',
    [string]$RainZip = '',
    [string]$Scales = '',
    [switch]$FullSize
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repoRoot
if (-not $Out) { $Out = Join-Path $repoRoot ('outputs/griddehaze/replay_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) }
if (Test-Path -LiteralPath $Out) { throw 'Choose a new output directory to preserve previous evidence.' }
New-Item -ItemType Directory -Path $Out | Out-Null
function Run-Recorded([string]$Label, [string[]]$Arguments) {
    & $Python -m griddehaze_fixed.record (Join-Path $Out 'commands') $Label -- $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Recorded step failed: $Label" }
}
$source = Join-Path $Out 'source'
Run-Recorded 'fetch' @('-m','griddehaze_fixed.fetch',$source)
if (-not $Scales) {
    if (-not $FogZip -or -not $RainZip) { throw 'Supply frozen -Scales, or both original -FogZip and -RainZip.' }
    $dataRoot = Join-Path $Out 'userdata'
    Run-Recorded 'data' @('-m','griddehaze_fixed.data','--fog-zip',$FogZip,'--rain-zip',$RainZip,'--out',$dataRoot)
    $Scales = Join-Path $Out 'calibration.json'
    Run-Recorded 'calibration' @('-m','griddehaze_fixed.calibrate','--source',$source,'--split',(Join-Path $dataRoot 'splits.json'),'--out',$Scales)
}
$suiteRoot = Join-Path $Out 'suite'
Run-Recorded 'suite' @('-m','griddehaze_fixed.suite','--source',$source,'--out',$suiteRoot,'--scales',$Scales)
$package = Join-Path $suiteRoot 'w16cal'
Run-Recorded 'independent_export_check' @('-m','griddehaze_fixed.check_export',$source,$package,'--report',(Join-Path $Out 'parameter_audit.json'))
if ($FullSize) {
    if ($FogZip) {
        $dataRoot = Join-Path $Out 'userdata'
        if (-not (Test-Path -LiteralPath $dataRoot)) {
            if (-not $RainZip) { throw 'Full approved image extraction also requires -RainZip.' }
            Run-Recorded 'data' @('-m','griddehaze_fixed.data','--fog-zip',$FogZip,'--rain-zip',$RainZip,'--out',$dataRoot)
        }
        $approved = Join-Path $dataRoot 'images/Fog/Fog/foggy-001.jpg'
        Run-Recorded 'full_approved' @('-m','griddehaze_fixed.large','--package',$package,'--source',$source,'--image',$approved,'--out',(Join-Path $Out 'full_approved'))
    }
    Run-Recorded 'full_720p' @('-m','griddehaze_fixed.large','--package',$package,'--source',$source,'--height','720','--width','1280','--out',(Join-Path $Out 'full_720p'))
}
Write-Output "Evidence directory: $Out"
