param([string]$BundleDirectory = (Join-Path $PSScriptRoot 'dist/VideoConverter'))
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ConverterSmokeWindows {
  public delegate bool Callback(IntPtr handle, IntPtr data);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Callback cb, IntPtr data);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr handle, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr handle, uint msg, IntPtr wparam, IntPtr lparam);
}
'@
$exePath = Join-Path $BundleDirectory 'VideoConverter.exe'
foreach ($name in @('ffmpeg', 'ffprobe')) {
    $toolPath = Join-Path $BundleDirectory "tools/ffmpeg/bin/$name.exe"
    $versionText = & $toolPath -version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$name failed verification" }
    Write-Output $versionText[0]
}
$converterProcess = Start-Process -FilePath $exePath -WorkingDirectory $BundleDirectory -WindowStyle Hidden -PassThru
$foundWindows = [System.Collections.Generic.List[object]]::new()
$enumerate = [ConverterSmokeWindows+Callback]{ param($handle, $data)
    [uint32]$windowProcessId = 0
    [void][ConverterSmokeWindows]::GetWindowThreadProcessId($handle, [ref]$windowProcessId)
    if ($windowProcessId -eq $converterProcess.Id) {
        $buffer = [System.Text.StringBuilder]::new(1024)
        [void][ConverterSmokeWindows]::GetWindowText($handle, $buffer, 1024)
        if ($buffer.Length -gt 0) {
            $foundWindows.Add([pscustomobject]@{ Handle=$handle; Title=$buffer.ToString() })
        }
    }
    return $true
}
$deadline = [DateTime]::UtcNow.AddSeconds(15)
$mainWindow = $null
try {
    do {
        $foundWindows.Clear()
        [void][ConverterSmokeWindows]::EnumWindows($enumerate, [IntPtr]::Zero)
        $mainWindow = $foundWindows | Where-Object { $_.Title -eq '视频格式转换器' } | Select-Object -First 1
        if ($foundWindows | Where-Object { $_.Title -eq 'Unhandled exception in script' }) {
            throw 'Bundled app opened an exception dialog instead of the converter.'
        }
        if ($mainWindow) { break }
        if ($converterProcess.HasExited) { throw 'Bundled app exited before creating its window.' }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $mainWindow) { throw 'Converter window not found within 15 seconds.' }
    Write-Output "Real bundled window found: $($mainWindow.Title)"
    [void][ConverterSmokeWindows]::PostMessage($mainWindow.Handle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    if (-not $converterProcess.WaitForExit(5000)) { throw 'Bundled app failed to close.' }
    if ($converterProcess.ExitCode -ne 0) { throw "Bundled app exited with $($converterProcess.ExitCode)" }
    Write-Output 'Bundled startup and normal close: PASS'
} finally {
    if (-not $converterProcess.HasExited) { $converterProcess.Kill() }
}
