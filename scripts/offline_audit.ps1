param(
    [double]$DurationSeconds = 5.0,
    [string]$DataDir = "",
    [switch]$NoOpenAdapt
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python venv not found: $Python"
}
if ([string]::IsNullOrWhiteSpace($DataDir)) {
    $DataDir = Join-Path $RepoRoot "data\offline-audit"
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

$stdout = Join-Path $DataDir "capture.stdout.log"
$stderr = Join-Path $DataDir "capture.stderr.log"
Remove-Item $stdout, $stderr -Force -ErrorAction SilentlyContinue

$durationText = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0}",
    $DurationSeconds
)
$escapedDataDir = $DataDir.Replace('"', '\"')
$arguments = "-m personal_predictive_ai.cli --data-dir `"$escapedDataDir`" capture --duration $durationText"
if ($NoOpenAdapt) {
    $arguments += " --no-openadapt"
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Python
$psi.Arguments = $arguments
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
if (-not $proc.Start()) {
    throw "Failed to start capture runtime."
}

$external = @()
$auditedIds = @()
$outText = ""
$errText = ""
$exitCode = $null
try {
    while (-not $proc.HasExited) {
        $treeIds = Get-ProcessTreeIds $proc.Id
        $auditedIds += $treeIds
        foreach ($treePid in $treeIds) {
            $connections = Get-NetTCPConnection -OwningProcess $treePid -State Established -ErrorAction SilentlyContinue
            foreach ($connection in $connections) {
                $ip = $null
                $parsed = [System.Net.IPAddress]::TryParse($connection.RemoteAddress, [ref]$ip)
                $isLoopback = $parsed -and [System.Net.IPAddress]::IsLoopback($ip)
                if (-not $isLoopback) {
                    $external += [pscustomobject]@{
                        pid = $treePid
                        remote_address = $connection.RemoteAddress
                        remote_port = $connection.RemotePort
                    }
                }
            }
        }
        if ($external.Count -gt 0) {
            $proc.Kill()
            break
        }
        Start-Sleep -Milliseconds 100
    }
    $proc.WaitForExit()
    $outText = $proc.StandardOutput.ReadToEnd()
    $errText = $proc.StandardError.ReadToEnd()
    $exitCode = $proc.ExitCode
    Set-Content -Path $stdout -Value $outText -Encoding utf8
    Set-Content -Path $stderr -Value $errText -Encoding utf8
}
finally {
    $proc.Dispose()
}

if ($external.Count -gt 0) {
    $external | Format-Table -AutoSize | Out-String | Write-Error
    throw "Offline audit observed non-loopback established TCP connections."
}
if ($exitCode -ne 0) {
    throw "Capture runtime exited with code ${exitCode}: $errText"
}

$uniqueAudited = @($auditedIds | Sort-Object -Unique)
Write-Output "OFFLINE_AUDIT_OK external_established=0 audited_processes=$($uniqueAudited.Count)"
Write-Output ("audited_pids=" + ($uniqueAudited -join ','))
if ($outText) {
    Write-Output $outText.Trim()
}
