$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project

$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements first.' }
$pyinstaller = Join-Path $project '.venv\Scripts\pyinstaller.exe'
if (-not (Test-Path -LiteralPath $pyinstaller)) { throw 'Install PyInstaller in .venv first.' }

& $pyinstaller --noconfirm --clean --onedir --console --name WaveTypeEngine --icon 'assets\WaveType.ico' `
    --additional-hooks-dir 'packaging\hooks' `
    --add-binary 'runtime\parakeet-cli.exe;runtime' engine.py
if ($LASTEXITCODE -ne 0) { throw 'Engine bundle failed.' }

& $pyinstaller --noconfirm --clean --onedir --windowed --name WaveType --icon 'assets\WaveType.ico' `
    --add-data 'assets\WaveType.ico;assets' `
    --add-data 'assets\logo_expanded.png;assets' `
    --add-data 'assets\InterVariable.ttf;assets' `
    --add-data 'assets\Figtree.ttf;assets' `
    --add-data 'assets\EBGaramond.ttf;assets' `
    --add-data 'assets\JetBrainsMono.ttf;assets' `
    --add-data 'assets\icons;assets\icons' `
    --add-data 'assets\lock_frames;assets\lock_frames' desktop.py
if ($LASTEXITCODE -ne 0) { throw 'UI bundle failed.' }

$bundle = (Resolve-Path -LiteralPath (Join-Path $project 'dist\WaveType')).Path
$engine = (Resolve-Path -LiteralPath (Join-Path $project 'dist\WaveTypeEngine')).Path
$nested = Join-Path $bundle 'engine'
if (-not $bundle.StartsWith($project, [StringComparison]::OrdinalIgnoreCase) -or
    -not $engine.StartsWith($project, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Bundle paths escaped the workspace.'
}
if (Test-Path -LiteralPath $nested) { Remove-Item -LiteralPath $nested -Recurse -Force }
Copy-Item -LiteralPath $engine -Destination $nested -Recurse
Copy-Item -LiteralPath (Join-Path $project 'LICENSES.md') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $project 'licenses') -Destination (Join-Path $bundle 'licenses') -Recurse

$makensis = 'C:\Program Files (x86)\NSIS\makensis.exe'
if (-not (Test-Path -LiteralPath $makensis)) { throw 'NSIS is required for the installer.' }
& $makensis (Join-Path $project 'installer.nsi')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
