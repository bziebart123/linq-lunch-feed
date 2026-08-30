# run_weekly.ps1 - Weekly refresh of the lunch-menu feeds.
#
# Registered as a Windows Scheduled Task by setup_schedule.ps1. Runs
# refresh.py, which rebuilds this month and next month for every school in
# config.json and pushes only if something actually changed.
#
# LinqConnect blocks datacenter IPs, so this has to run on a home machine --
# that is the whole reason it is a local task and not a GitHub Action.

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$python = 'C:\Users\brian\AppData\Local\Programs\Python\Python312\python.exe'
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source } else { $python = 'python' }
}

$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ('refresh-{0}.log' -f (Get-Date -Format 'yyyy-MM-dd'))

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8

# Pick up any changes made from another machine before regenerating.
& git pull --ff-only 2>&1 | Out-File $log -Append -Encoding utf8

& $python refresh.py 2>&1 | Out-File $log -Append -Encoding utf8
$code = $LASTEXITCODE

if ($code -eq 0) {
    "RESULT: ok" | Out-File $log -Append -Encoding utf8
} else {
    "RESULT: failed (exit $code)" | Out-File $log -Append -Encoding utf8
    # Surface failures instead of letting them pass silently for weeks.
    try {
        [void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Warning
        $n.Visible = $true
        $n.ShowBalloonTip(10000, 'Lunch feed refresh failed',
            "See $log", [System.Windows.Forms.ToolTipIcon]::Warning)
        Start-Sleep -Seconds 12
        $n.Dispose()
    } catch { }
}

# Keep the log directory from growing without bound.
Get-ChildItem $logDir -Filter 'refresh-*.log' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 12 |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
