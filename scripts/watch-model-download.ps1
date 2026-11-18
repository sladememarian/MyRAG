# Live progress of the one-off embedding-model download inside the `web` container.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\watch-model-download.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\watch-model-download.ps1 -Once
#
# The download runs inside the first upload request, so the admin page stays
# "loading" until it finishes. This script reads the same counter Hugging Face
# xet writes to its log and prints speed / ETA every few seconds.
[CmdletBinding()]
param(
    [int]$IntervalSeconds = 5,
    [long]$TotalBytes = 470641600,
    [int]$Samples = 0,
    [switch]$Once
)

$ErrorActionPreference = 'Stop'

function Invoke-InWeb {
    param([string]$Command)
    $output = docker compose exec -T web sh -c $Command 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    ($output | Out-String).Trim()
}

function Format-Bytes {
    param([double]$Value)
    if ($Value -ge 1GB) { return ('{0:N2} GB' -f ($Value / 1GB)) }
    if ($Value -ge 1MB) { return ('{0:N0} MB' -f ($Value / 1MB)) }
    ('{0:N0} KB' -f ($Value / 1KB))
}

$bytesCommand = "grep -ho 'observed bytes sent so far = [0-9]*' /data/hf/xet/logs/*.log 2>/dev/null | sed 's/.*= //' | sort -n | tail -1"
$partialCommand = "find /data/hf/hub -name '*.incomplete' 2>/dev/null | wc -l"

Write-Host 'Model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
Write-Host ('Size:  {0}' -f (Format-Bytes $TotalBytes))

$lastBytes = 0L
$lastStamp = Get-Date
$speed = 0.0
$taken = 0

while ($true) {
    $raw = Invoke-InWeb $bytesCommand
    $bytes = 0L
    if ($raw) { [void][long]::TryParse($raw, [ref]$bytes) }

    $now = Get-Date
    $elapsed = ($now - $lastStamp).TotalSeconds
    if ($bytes -gt 0) {
        if ($lastBytes -gt 0 -and $bytes -gt $lastBytes -and $elapsed -gt 0) {
            $speed = ($bytes - $lastBytes) / $elapsed
        }
        elseif ($bytes -lt $lastBytes) {
            $speed = 0.0   # counter restarted: a new download session began
        }
        $lastBytes = $bytes
        $lastStamp = $now
    }

    $fraction = if ($TotalBytes -gt 0) { [Math]::Min(1.0, $bytes / $TotalBytes) } else { 0 }
    $filled = [int]($fraction * 30)
    $bar = ('#' * $filled).PadRight(30, '.')

    $eta = '--:--'
    if ($speed -gt 0) {
        $seconds = [int](($TotalBytes - $bytes) / $speed)
        $eta = '{0:hh\:mm\:ss}' -f [TimeSpan]::FromSeconds($seconds)
    }
    $rate = if ($speed -gt 0) { '{0:N0} KB/s' -f ($speed / 1KB) } else { 'measuring...' }

    Write-Host ('[{0}] {1,8} / {2} ({3,3:N0}%)  {4,12}  ETA {5}' -f `
        $bar, (Format-Bytes $bytes), (Format-Bytes $TotalBytes), ($fraction * 100), $rate, $eta)

    if ($Once) { break }

    $taken++
    if ($Samples -gt 0 -and $taken -ge $Samples) { break }

    $partial = Invoke-InWeb $partialCommand
    if ($bytes -gt 0 -and $partial -eq '0') {
        Write-Host ''
        Write-Host 'Download finished. Indexing is running now; follow it with:'
        Write-Host '  docker compose logs -f web'
        break
    }

    Start-Sleep -Seconds $IntervalSeconds
}
