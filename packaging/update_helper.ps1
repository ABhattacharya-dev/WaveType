param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][int]$AppPid,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$ResultFile
)
$ErrorActionPreference = 'Stop'
$result = @{ status = 'failed'; message = 'Update did not complete.' }
try {
    # The app shuts down its engine before its own process exits.
    $process = Get-Process -Id $AppPid -ErrorAction SilentlyContinue
    if ($process) { $process.WaitForExit(60000) }
    if (Get-Process -Id $AppPid -ErrorAction SilentlyContinue) {
        throw 'WaveType did not close in time. The update was not installed.'
    }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne $ExpectedSha256) {
        throw 'The downloaded installer changed after verification. The update was not installed.'
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Installer
    # NSIS requires /D= to be last and unquoted, including paths with spaces.
    $start.Arguments = '/S /UPDATE /D=' + $InstallDir
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $installerProcess = [System.Diagnostics.Process]::Start($start)
    $installerProcess.WaitForExit()
    if ($installerProcess.ExitCode -ne 0) {
        throw "Setup returned exit code $($installerProcess.ExitCode)."
    }
    $result = @{ status = 'installed'; message = '' }
} catch {
    $result.message = $_.Exception.Message
} finally {
    $result | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultFile -Encoding UTF8
    $app = Join-Path $InstallDir 'WaveType.exe'
    if (Test-Path -LiteralPath $app) {
        Start-Process -FilePath $app -WorkingDirectory $InstallDir -WindowStyle Hidden
    }
}
