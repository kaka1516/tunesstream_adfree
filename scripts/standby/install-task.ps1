# failover-20261111: registers the per-user "MusicStreamStandby" task (every minute, hidden, no password needed).
# Does not touch any other task (MusicStream, MusicStream8121_VizUpdate ...).
$ps1 = Join-Path $PSScriptRoot 'ms-standby.ps1'
$vbs = Join-Path $env:USERPROFILE '.ms-standby\tick.vbs'
# wscript keeps the window fully hidden (no console flash every minute)
"CreateObject(""WScript.Shell"").Run ""powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """"$ps1"""" tick"", 0, False" | Set-Content -Path $vbs -Encoding ASCII
$act = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$vbs`""
$t1 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$pr = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'MusicStreamStandby' -Action $act -Trigger @($t1, $t2) -Settings $set -Principal $pr -Description 'Music Stream backup server: takes over music link only when the main phone is down (failover-20261111)' -Force | Out-Null
Write-Host 'Scheduled task MusicStreamStandby: every minute.'
