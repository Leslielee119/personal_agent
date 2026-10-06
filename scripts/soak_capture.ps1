param(
    [double]$DurationSeconds = 28800,
    [double]$SampleIntervalSeconds = 5,
    [int]$RawTtlSeconds = 900,
    [string]$DataDir = "",
    [string[]]$WatchRoot = @(),
    [string[]]$ForbidString = @(),
    [switch]$NoOpenAdapt
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python venv not found: $Python"
}
if ([string]::IsNullOrWhiteSpace($DataDir)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $DataDir = Join-Path $RepoRoot "data\soak-$stamp"
}
if ($WatchRoot.Count -eq 0) {
    $WatchRoot = @($RepoRoot)
}
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

function Get-ProcessTreeIds([int]$RootPid) {
    $rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $ids = @($RootPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $rows) {
            $pidValue = [int]$row.ProcessId
            $parentValue = [int]$row.ParentProcessId
            if (($ids -contains $parentValue) -and -not ($ids -contains $pidValue)) {
                $ids += $pidValue
                $changed = $true
            }
        }
    }
    return @($ids | Sort-Object -Unique)
}

function Quote-Arg([string]$Value) {
    return '"' + $Value.Replace('"', '\"') + '"'
}

$stopFile = Join-Path $DataDir "stop.requested"
$samplesPath = Join-Path $DataDir "soak_samples.jsonl"
$stdoutPath = Join-Path $DataDir "capture.stdout.log"
$stderrPath = Join-Path $DataDir "capture.stderr.log"
$statusPath = Join-Path $DataDir "runtime_status.json"
$reportPath = Join-Path $DataDir "health_report.json"
$replayPath = Join-Path $DataDir "replay.txt"
Remove-Item $stopFile, $samplesPath, $stdoutPath, $stderrPath, $statusPath, $reportPath, $replayPath `
    -Force -ErrorAction SilentlyContinue

$durationText = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0}",
    $DurationSeconds
)
$argParts = @(
    "-m",
    "personal_predictive_ai.cli",
    "--data-dir",
    (Quote-Arg $DataDir),
    "--raw-ttl-seconds",
    ([string]$RawTtlSeconds),
    "capture",
    "--duration",
    $durationText,
    "--stop-file",
    (Quote-Arg $stopFile)
)
foreach ($root in $WatchRoot) {
    $argParts += "--watch-root"
    $argParts += (Quote-Arg $root)
}
if ($NoOpenAdapt) {
    $argParts += "--no-openadapt"
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Python
$psi.Arguments = ($argParts -join " ")
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
if (-not $proc.Start()) {
    throw "Failed to start capture runtime."
}

$logicalCpuCount = [Environment]::ProcessorCount
$exitCode = $null
$outText = ""
$errText = ""
$forcedKill = $false
try {
    while (-not $proc.HasExited) {
        $treeIds = Get-ProcessTreeIds $proc.Id
        $treeProcesses = @()
        foreach ($treePid in $treeIds) {
            $treeProcess = Get-Process -Id $treePid -ErrorAction SilentlyContinue
            if ($null -ne $treeProcess) {
                $treeProcesses += $treeProcess
            }
        }
        if ($treeProcesses.Count -eq 0) {
            break
        }

        $cpuTotal = 0.0
        $rssTotal = [int64]0
        foreach ($treeProcess in $treeProcesses) {
            if ($null -ne $treeProcess.CPU) {
                $cpuTotal += [double]$treeProcess.CPU
            }
            $rssTotal += [int64]$treeProcess.WorkingSet64
        }

        $external = @()
        foreach ($treePid in $treeIds) {
            $connections = Get-NetTCPConnection -OwningProcess $treePid -State Established -ErrorAction SilentlyContinue
            foreach ($connection in $connections) {
                $ip = $null
                $parsed = [System.Net.IPAddress]::TryParse($connection.RemoteAddress, [ref]$ip)
                $isLoopback = $parsed -and [System.Net.IPAddress]::IsLoopback($ip)
                if (-not $isLoopback) {
                    $external += ("{0}:{1}@{2}" -f $connection.RemoteAddress, $connection.RemotePort, $treePid)
                }
            }
        }

        $measure = Get-ChildItem -Path $DataDir -File -Recurse -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum
        $dataBytes = 0
        if ($null -ne $measure.Sum) {
            $dataBytes = [int64]$measure.Sum
        }
        $timestampNs = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000
        $sample = [ordered]@{
            timestamp_ns = $timestampNs
            cpu_total_seconds = $cpuTotal
            logical_cpu_count = $logicalCpuCount
            rss_bytes = $rssTotal
            data_bytes = $dataBytes
            process_count = $treeProcesses.Count
            process_ids = @($treeIds)
            external_established = $external.Count
            external_remote = @($external)
        }
        Add-Content -Path $samplesPath -Value ($sample | ConvertTo-Json -Compress -Depth 4) -Encoding utf8
        Start-Sleep -Milliseconds ([int]([Math]::Max(100, $SampleIntervalSeconds * 1000)))
        $proc.Refresh()
    }
}
finally {
    if (-not $proc.HasExited) {
        Set-Content -Path $stopFile -Value "stop" -Encoding ascii
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while (-not $proc.HasExited -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 100
            $proc.Refresh()
        }
        if (-not $proc.HasExited) {
            $forcedKill = $true
            $proc.Kill()
        }
    }
    $proc.WaitForExit()
    $outText = $proc.StandardOutput.ReadToEnd()
    $errText = $proc.StandardError.ReadToEnd()
    $exitCode = $proc.ExitCode
    Set-Content -Path $stdoutPath -Value $outText -Encoding utf8
    Set-Content -Path $stderrPath -Value $errText -Encoding utf8
    $proc.Dispose()
}

$statusLines = @($outText -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($statusLines.Count -gt 0) {
    Set-Content -Path $statusPath -Value $statusLines[-1] -Encoding utf8
}

$reportArgs = @(
    (Join-Path $RepoRoot "scripts\report_capture_health.py"),
    $DataDir,
    "--samples", $samplesPath,
    "--runtime-status", $statusPath,
    "--raw-ttl-seconds", ([string]$RawTtlSeconds),
    "--output", $reportPath
)
foreach ($value in $ForbidString) {
    $reportArgs += "--forbid-string"
    $reportArgs += $value
}
& $Python @reportArgs | Out-Null
& $Python (Join-Path $RepoRoot "scripts\replay_capture.py") $DataDir --limit 200 |
    Set-Content -Path $replayPath -Encoding utf8

if ($forcedKill) {
    throw "Capture runtime did not honor clean stop-file shutdown within 10 seconds."
}
if ($exitCode -ne 0) {
    throw "Capture runtime exited with code ${exitCode}: $errText"
}

Write-Output "SOAK_CAPTURE_OK"
Write-Output "data_dir=$DataDir"
Write-Output "samples=$samplesPath"
Write-Output "report=$reportPath"
Write-Output "replay=$replayPath"
