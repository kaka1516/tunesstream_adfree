# Windows autostart TEMPLATE (ms-v75). Not run by the installer unless you pass -Autostart to install.ps1.
# Registers a per-user logon task that runs scripts\start.ps1 hidden. Remove with: Unregister-ScheduledTask MusicStream
param([string]$Dir = (Split-Path $PSScriptRoot -Parent | Split-Path -Parent))
$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dir\scripts\start.ps1`"" -WorkingDirectory $Dir
$trg = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName 'MusicStream' -Action $act -Trigger $trg -Description 'Music Stream server (per-user)' -Force | Out-Null
Write-Host "Scheduled task 'MusicStream' registered for $env:USERNAME"
