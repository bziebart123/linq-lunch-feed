# setup_schedule.ps1 - Register (or re-register) the weekly refresh task.
#
#   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1 -DayOfWeek Wednesday -At 7:30am
#   powershell -ExecutionPolicy Bypass -File setup_schedule.ps1 -Remove
#
# No admin rights needed: the task runs as the current user, only while logged
# on, so no stored password is involved.

param(
    [string]$DayOfWeek = 'Sunday',
    [string]$At        = '9:00am',
    [switch]$Remove
)

$name = 'LinqLunchFeed Weekly Refresh'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $repo 'run_weekly.ps1'

Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
if ($Remove) { Write-Output "Removed scheduled task '$name'."; exit 0 }

if (-not (Test-Path $script)) { throw "Cannot find $script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $At
# StartWhenAvailable is what makes a missed run (laptop asleep, machine off)
# fire at the next opportunity instead of being skipped until the next week.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description 'Rebuilds Hamilton School District lunch menu ICS feeds and pushes to GitHub Pages. Must run on a home network; LinqConnect blocks datacenter IPs.' | Out-Null

$info = Get-ScheduledTaskInfo -TaskName $name
Write-Output "Registered '$name' - $DayOfWeek at $At."
Write-Output "Next run: $($info.NextRunTime)"
Write-Output "Run it now with:  Start-ScheduledTask -TaskName '$name'"
