# Explicit yt-dlp updater for Windows (ms-v75). Never runs by itself. Usage: .\scripts\update-ytdlp.ps1 [-Pre]
param([switch]$Pre)
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = (Select-String -Path music.env -Pattern '^YTDLP_PY=(.*)$' -ErrorAction SilentlyContinue | Select-Object -First 1).Matches.Groups[1].Value
if (-not $py) { $py = 'python' }
Write-Host "yt-dlp before: $(& $py -m yt_dlp --version 2>$null)"
$args2 = @('-m','pip','install','-U'); if ($Pre) { $args2 += '--pre' }; $args2 += 'yt-dlp[default]'
& $py @args2
Write-Host "yt-dlp after:  $(& $py -m yt_dlp --version 2>$null)"
Write-Host "Restart the server so it loads the new extractor."
