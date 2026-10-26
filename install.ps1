param(
    [string]$Target = "claude,cursor,codex",
    [ValidateSet("global", "project")][string]$Scope = "global",
    [string]$ProjectDir = "",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$argList = @(
    (Join-Path $root "scripts\install.py"),
    "--target", $Target,
    "--scope", $Scope,
    "--tools-dir", $root
)
if ($ProjectDir) { $argList += @("--project-dir", $ProjectDir) }
if ($Remove) { $argList += "--remove" }

& $python @argList
exit $LASTEXITCODE
