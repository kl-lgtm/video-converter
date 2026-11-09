$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv312/Scripts/python.exe')) {
    py -3.12 -m venv .venv312
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 (64-bit) from python.org, then retry.' }
}
& '.venv312/Scripts/python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

$targetPath = Join-Path $PSScriptRoot 'tools/ffmpeg'
if (Test-Path -LiteralPath $targetPath) {
    Write-Host 'Existing tools/ffmpeg preserved. Verifying tools...'
} else {
    $stagePath = Join-Path $PSScriptRoot ('work/ffmpeg-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stagePath -Force | Out-Null
    $zipPath = Join-Path $stagePath 'ffmpeg.zip'
    Write-Host 'Downloading FFmpeg 9.0.2 Essentials (about 110 MB)...'
    Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip' -OutFile $zipPath
    $expectedHash = '60F467265B1E312373DBCD92200C2618A74850F98D3D078E94296BB3FA2047BA'
    if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Download checksum mismatch. No tools were installed.'
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath (Join-Path $stagePath 'extracted')
    $roots = @(Get-ChildItem -LiteralPath (Join-Path $stagePath 'extracted') -Directory)
    if ($roots.Count -ne 1) { throw 'Unexpected archive layout.' }
    New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'tools') -Force | Out-Null
    Copy-Item -LiteralPath $roots[0].FullName -Destination $targetPath -Recurse
}
foreach ($toolName in @('ffmpeg', 'ffprobe')) {
    $toolPath = Join-Path $targetPath "bin/$toolName.exe"
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Missing: $toolPath" }
    $versionOutput = & $toolPath -version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$toolName failed to start." }
    Write-Host $versionOutput[0]
}
Write-Host 'Setup complete. Double-click start.cmd.'
