param(
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [ValidateSet('prepare','create','synth','collect')][string]$Stage = 'prepare',
    [string]$Vivado = 'E:\Xilinx\2025.2\Vivado\bin\vivado.bat'
)
$ErrorActionPreference = 'Stop'
$BuildDirectory = [System.IO.Path]::GetFullPath($BuildDirectory)
$resourceScriptDirectory = $PSScriptRoot
if ($Stage -eq 'prepare') {
    & python (Join-Path $resourceScriptDirectory 'resource_prepare.py') --out $BuildDirectory
} elseif ($Stage -eq 'collect') {
    & python (Join-Path $resourceScriptDirectory 'resource_collect.py') --build $BuildDirectory --dest (Join-Path $resourceScriptDirectory '..\reports')
} else {
    # The desktop command environment can omit this standard variable.
    if (-not $env:PROCESSOR_ARCHITECTURE) { $env:PROCESSOR_ARCHITECTURE = 'AMD64' }
    Push-Location -LiteralPath $BuildDirectory
    try {
        & $Vivado -mode batch -log (Join-Path $BuildDirectory "$Stage.log") -journal (Join-Path $BuildDirectory "$Stage.jou") -source (Join-Path $resourceScriptDirectory 'resource_build.tcl') -tclargs $BuildDirectory $Stage
    } finally {
        Pop-Location
    }
}
if ($LASTEXITCODE -ne 0) { throw "Resource $Stage failed (exit $LASTEXITCODE)" }
