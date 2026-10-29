param(
    [ValidateSet('Check', 'RemoveData')][string]$Action,
    [string]$InstallDir
)
$ErrorActionPreference = 'Stop'

# Directory junctions and symbolic links are never traversed, including the root.
function Assert-NotLinked([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Linked path was left untouched: $Path"
    }
    return $item
}

function Get-SafeFiles([string]$Path) {
    $item = Assert-NotLinked $Path
    if ($item.PSIsContainer) {
        foreach ($child in Get-ChildItem -LiteralPath $Path -Force) {
            Get-SafeFiles $child.FullName
        }
    } else { $item.FullName }
}

function Remove-SafeTree([string]$Path, [string]$Root) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute -ne $Root -and -not $absolute.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Data path escaped the WaveType data folder.'
    }
    $item = Assert-NotLinked $absolute
    if ($item.PSIsContainer) {
        foreach ($child in Get-ChildItem -LiteralPath $absolute -Force) {
            Remove-SafeTree $child.FullName $Root
        }
        # No -Recurse: even a newly introduced link is never traversed.
        [IO.Directory]::Delete($absolute, $false)
    } else { [IO.File]::Delete($absolute) }
}

try {
    $dataRoot = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'STTCore'))
    if ($Action -eq 'RemoveData') {
        if (Test-Path -LiteralPath $dataRoot) {
            # Validate the entire tree before removing anything.
            $null = @(Get-SafeFiles $dataRoot)
            Remove-SafeTree $dataRoot $dataRoot
        }
        if (Test-Path -LiteralPath $dataRoot) { throw "Data remains at $dataRoot" }
    } else {
        if (Test-Path -LiteralPath $dataRoot) {
            $null = Assert-NotLinked $dataRoot
            foreach ($name in 'ui.lock', 'engine.lock') {
                $lockPath = Join-Path $dataRoot $name
                if (Test-Path -LiteralPath $lockPath) { $null = Assert-NotLinked $lockPath }
            }
        }
        $target = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
        # File checks also catch old releases without reliable lock files.
        if (Test-Path -LiteralPath $target) {
            foreach ($file in Get-SafeFiles $target) {
                if ($file -eq (Join-Path $target 'Uninstall.exe')) { continue }
                $stream = [IO.File]::Open($file, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
                $stream.Dispose()
            }
        }
        # CIM returns 64-bit executable paths even under NSIS's 32-bit PowerShell.
        foreach ($process in Get-CimInstance Win32_Process -Filter "Name = 'WaveType.exe' OR Name = 'WaveTypeEngine.exe' OR Name = 'llama-server.exe' OR Name = 'parakeet-cli.exe'") {
            $image = $process.ExecutablePath
            if ($image -and ($image.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase) -or
                            $image.StartsWith($dataRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
                throw "WaveType is still running (process $($process.ProcessId)). Exit it from the tray first."
            }
        }
    }
    exit 0
} catch {
    Write-Output $_.Exception.Message
    if ($Action -eq 'RemoveData') { exit 3 }
    exit 2
}
