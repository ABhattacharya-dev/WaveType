param([string]$TestRoot)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($TestRoot)
if (-not $root.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'This test only operates inside the temporary directory.'
}
$source = Join-Path $PSScriptRoot 'maintenance.ps1'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Maintenance script has parse errors.' }
foreach ($function in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($function.Extent.Text))
}

$data = Join-Path $root 'STTCore'
$outside = Join-Path $root 'outside'
$null = New-Item -ItemType Directory -Path $data, $outside
[IO.File]::WriteAllText((Join-Path $data 'history.json'), 'history')
[IO.File]::WriteAllText((Join-Path $outside 'keep.txt'), 'preserve')
$junction = Join-Path $data 'linked'
$null = New-Item -ItemType Junction -Path $junction -Target $outside
try {
    $rejected = $false
    try { $null = @(Get-SafeFiles $data) } catch { $rejected = $true }
    if (-not $rejected) { throw 'Directory link was followed.' }
    if (-not (Test-Path -LiteralPath (Join-Path $outside 'keep.txt'))) { throw 'Outside data was changed.' }
} finally {
    # Remove only the junction itself, never its target.
    [IO.Directory]::Delete($junction, $false)
}
$file = Join-Path $data 'locked.txt'
[IO.File]::WriteAllText($file, 'locked')
$stream = [IO.File]::Open($file, 'Open', 'ReadWrite', 'None')
try {
    $rejected = $false
    try { Remove-SafeTree $data $data } catch { $rejected = $true }
    if (-not $rejected -or -not (Test-Path -LiteralPath $file)) { throw 'Locked file was incorrectly reported removed.' }
} finally { $stream.Dispose() }
Remove-SafeTree $data $data
if (Test-Path -LiteralPath $data) { throw 'Retry did not finish removing data.' }
if ([IO.File]::ReadAllText((Join-Path $outside 'keep.txt')) -ne 'preserve') { throw 'Unrelated data was changed.' }
Write-Output 'PASS: junction refusal, locked-file failure, retry and unrelated-data preservation.'
