$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.venv312/Scripts/python.exe' -m pip install pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
& '.venv312/Scripts/python.exe' -m PyInstaller --noconfirm video_converter.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
$toolsDestination = Join-Path $PSScriptRoot 'dist/VideoConverter/tools'
New-Item -ItemType Directory -Force -Path $toolsDestination | Out-Null
# Copy only the required complete package, not every file in tools/.
Copy-Item -LiteralPath 'tools/ffmpeg' -Destination $toolsDestination -Recurse -Force
foreach ($tool in @('ffmpeg', 'ffprobe')) {
    $toolPath = Join-Path $toolsDestination "ffmpeg/bin/$tool.exe"
    $versionText = & $toolPath -version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$tool failed verification." }
    Write-Host $versionText[0]
}
Write-Host 'Build complete: dist/VideoConverter/VideoConverter.exe'
