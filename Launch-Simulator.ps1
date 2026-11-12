[CmdletBinding()]
param(
    [ValidateSet('intro','starflight','tunnel','terrain','planet','swarm','kaleidoscope','blackhole','finale')][string]$Scene,
    [ValidateSet('tour','idle','swarm')][string]$Showcase = 'tour',
    [switch]$Swarm,
    [ValidateSet('solo','joined','trio','burst','handover','departed')][string]$SwarmStage,
    [switch]$Screenshot,
    [string]$OutputPath,
    [string]$Record,
    [string]$Soundtrack,
    [ValidateRange(1,180)][double]$Seconds = 48,
    [ValidateRange(5,30)][int]$VideoFps = 15,
    [ValidateSet('lcd','window')][string]$RecordView = 'lcd',
    [string]$Gallery,
    [switch]$Expansions,
    [ValidateRange(0,1)][double]$Quality = 0.9,
    [string]$PythonPath,
    [string]$SimRoot
)
$ErrorActionPreference = 'Stop'
if (([int][bool]$Screenshot + [int][bool]$Record + [int][bool]$Gallery) -gt 1) {
    throw 'Choose one screenshot, recording or gallery capture.'
}
if ($OutputPath -and -not $Screenshot) { throw 'OutputPath requires Screenshot.' }
if ($Soundtrack -and -not $Record) { throw 'Soundtrack requires Record.' }
if (-not $SimRoot) { $SimRoot = $env:TILDAGON_HORIZON_SIM_ROOT }
if (-not $SimRoot) { $SimRoot = Join-Path $PSScriptRoot '.simulator' }
$SimRoot = [System.IO.Path]::GetFullPath($SimRoot)
$setup = Join-Path $PSScriptRoot 'tools\prepare_simulator.py'
$launcher = Join-Path $PSScriptRoot 'simulator\launch.py'
$manifest = Join-Path $SimRoot 'runtime.json'
$runtimePython = $null
if (Test-Path -LiteralPath $manifest) {
    $runtime = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if (Test-Path -LiteralPath $runtime.python) { $runtimePython = $runtime.python }
}
if (-not $runtimePython) {
    $setupArguments = @($setup, '--sim-root', $SimRoot)
    if ($PythonPath) { & $PythonPath @setupArguments }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3.10 @setupArguments }
    elseif (Get-Command python3.10 -ErrorAction SilentlyContinue) { & python3.10 @setupArguments }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python @setupArguments }
    else { throw 'Git and CPython3.10 are required; see simulator/README.md.' }
    if ($LASTEXITCODE -ne 0) { throw 'Local simulator setup failed.' }
    $runtime = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    $runtimePython = $runtime.python
}
$verification = & $runtimePython $setup --sim-root $SimRoot --check
if ($LASTEXITCODE -ne 0) { throw 'Simulator verification failed.' }
$arguments = @($launcher, '--showcase', $Showcase, '--quality', [string]$Quality)
if ($Scene) { $arguments += @('--scene', $Scene) }
if ($Expansions) { $arguments += '--expansions' }
if ($Swarm) { $arguments += '--swarm' }
if ($SwarmStage) { $arguments += @('--swarm-stage', $SwarmStage) }
if ($Record) { $arguments += @('--record', $Record, '--seconds', [string]$Seconds, '--video-fps', [string]$VideoFps, '--record-view', $RecordView) }
if ($Soundtrack) { $arguments += @('--soundtrack', $Soundtrack) }
if ($Gallery) { $arguments += @('--gallery', $Gallery) }
if ($Screenshot) {
    $arguments += '--screenshot'
    if ($OutputPath) { $arguments += @('--output', $OutputPath) }
}
$oldRoot, $oldDriver = $env:TILDAGON_HORIZON_SIM_ROOT, $env:SDL_VIDEODRIVER
try {
    $env:TILDAGON_HORIZON_SIM_ROOT = $SimRoot
    if ($Screenshot -or $Record -or $Gallery) {
        $env:SDL_VIDEODRIVER = 'dummy'
        & $runtimePython @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Simulator capture failed.' }
    } else {
        Remove-Item Env:SDL_VIDEODRIVER -ErrorAction SilentlyContinue
        $guiPython = Join-Path (Split-Path -Parent $runtimePython) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $guiPython)) { $guiPython = $runtimePython }
        $quoted = foreach ($argument in $arguments) {
            '"' + (($argument -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
        }
        $start = @{ FilePath = $guiPython; ArgumentList = $quoted; WorkingDirectory = $PSScriptRoot }
        if ($env:OS -eq 'Windows_NT') { $start.WindowStyle = 'Normal' }
        Start-Process @start
        Write-Host 'Event Horizon opened. Arrows/Enter: joystick;1..0,-,=: touch;A-F: badge;S: settings;Esc: exit.'
    }
} finally {
    if ($null -eq $oldRoot) { Remove-Item Env:TILDAGON_HORIZON_SIM_ROOT -ErrorAction SilentlyContinue }
    else { $env:TILDAGON_HORIZON_SIM_ROOT = $oldRoot }
    if ($null -eq $oldDriver) { Remove-Item Env:SDL_VIDEODRIVER -ErrorAction SilentlyContinue }
    else { $env:SDL_VIDEODRIVER = $oldDriver }
}
