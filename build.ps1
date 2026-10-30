param(
    [string]$Version = '0.1.0-beta1.01',
    [switch]$Sign,
    [string]$SignToolPath = 'signtool.exe',
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project
if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$') { throw 'Use a semantic release version.' }

$python = Join-Path $project '.venv\Scripts\python.exe'
$pyinstaller = Join-Path $project '.venv\Scripts\pyinstaller.exe'
$makensis = 'C:\Program Files (x86)\NSIS\makensis.exe'
if ($Sign) {
    $signtool = (Get-Command $SignToolPath -ErrorAction Stop).Source
    $thumbprint = $env:WAVETYPE_SIGN_CERT_THUMBPRINT
    if ($thumbprint -notmatch '^[0-9A-Fa-f]{40}$') {
        throw 'Set WAVETYPE_SIGN_CERT_THUMBPRINT to the trusted code-signing certificate thumbprint.'
    }
}

function Sign-OwnedFile([string]$Path) {
    & $signtool sign /sha1 $thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $Path" }
    & $signtool verify /pa /v $Path
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $Path" }
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv first.' }
if (-not (Test-Path -LiteralPath $pyinstaller)) { throw 'Install requirements-build.txt in .venv first.' }
if (-not (Test-Path -LiteralPath $makensis)) { throw 'Install NSIS 3 first.' }
& $python -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Build with x64 Python.' }
& $python packaging\release_metadata.py prepare --version $Version
if ($LASTEXITCODE -ne 0) { throw 'Version metadata failed.' }

& $pyinstaller --noconfirm --clean --noupx --onedir --console --name WaveTypeEngine `
    --icon 'assets\WaveType.ico' --version-file 'build\WaveTypeEngine-version.txt' `
    --exclude-module numpy --exclude-module torch `
    --additional-hooks-dir 'packaging\hooks' `
    --add-binary 'runtime\parakeet-cli.exe;runtime' engine.py
if ($LASTEXITCODE -ne 0) { throw 'Engine bundle failed.' }

& $pyinstaller --noconfirm --clean --noupx --onedir --windowed --name WaveType `
    --icon 'assets\WaveType.ico' --version-file 'build\WaveType-version.txt' `
    --add-data 'assets\WaveType.ico;assets' `
    --add-data 'assets\logo_expanded.png;assets' `
    --add-data 'assets\InterVariable.ttf;assets' `
    --add-data 'assets\Figtree.ttf;assets' `
    --add-data 'assets\EBGaramond.ttf;assets' `
    --add-data 'assets\JetBrainsMono.ttf;assets' `
    --add-data 'assets\icons;assets\icons' `
    --add-data 'assets\lock_frames;assets\lock_frames' `
    --add-data 'packaging\update_helper.ps1;packaging' desktop.py
if ($LASTEXITCODE -ne 0) { throw 'UI bundle failed.' }

$bundle = (Resolve-Path -LiteralPath (Join-Path $project 'dist\WaveType')).Path
$engineBundle = (Resolve-Path -LiteralPath (Join-Path $project 'dist\WaveTypeEngine')).Path
$nested = [IO.Path]::GetFullPath((Join-Path $bundle 'engine'))
$workspacePrefix = $project.TrimEnd('\') + '\'
if (-not $bundle.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not $engineBundle.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not $nested.StartsWith(($bundle.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Bundle paths escaped the workspace.'
}
if (Test-Path -LiteralPath $nested) { Remove-Item -LiteralPath $nested -Recurse -Force }
Copy-Item -LiteralPath $engineBundle -Destination $nested -Recurse
Copy-Item -LiteralPath (Join-Path $project 'LICENSE') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $project 'LICENSES.md') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $project 'licenses') -Destination (Join-Path $bundle 'licenses') -Recurse
Copy-Item -LiteralPath (Join-Path $project 'packaging\INSTALL-NOTICES.txt') -Destination $bundle
if ($Sign) {
    Sign-OwnedFile (Join-Path $bundle 'WaveType.exe')
    Sign-OwnedFile (Join-Path $nested 'WaveTypeEngine.exe')
}
& $python packaging\release_metadata.py manifest --version $Version --bundle $bundle
if ($LASTEXITCODE -ne 0) { throw 'Bundle manifest or privacy check failed.' }

$versionParts = ($Version.Split('-')[0].Split('.') + '0') -join '.'
& $makensis /WX "/DAPP_VERSION=$Version" "/DFILE_VERSION=$versionParts" (Join-Path $project 'installer.nsi')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
$installer = Join-Path $project "dist\WaveType-$Version-Setup-x64.exe"
if ($Sign) { Sign-OwnedFile $installer }
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($installer))" | Set-Content -LiteralPath (Join-Path $project 'dist\SHA256SUMS.txt') -Encoding ascii
Write-Output "Created $installer"
if ($Sign) {
    Write-Output 'Signed build. Clean-machine and Defender validation remain release gates.'
} else {
    Write-Output 'Unsigned development build. Do not publish as a SmartScreen fix.'
}
