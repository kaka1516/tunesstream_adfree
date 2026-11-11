# Visuals auto-update

Weekly (Monday 04:00 Asia/Calcutta) the player pulls new **dance clips**, **Poly Haven HDRIs**, and (when available) **Butterchurn presets** from allowlisted CC0/CC-BY/CMU/MIT sources. License is checked per item. Franchise, swimwear, unclear, or not-clearly-adult character models are skipped. `CREDITS.md` is appended automatically.

Caps: **50 MB** network per run, **1 GB** of updater-managed files. Downloads land in a temp folder, are validated, then merged atomically. `clips.json.lastgood` (and friends) are kept for rollback. The music server is never restarted; `assets/viz/rev.js` is the cache-bust the player reads on the next open.

## Turn it off

```
python3 scripts/viz-update.py --off
```

That writes `assets/viz/update/disabled` and sets `enabled: false` in `config.json`. On the phone you can also comment out the `viz-update` line in `crontab -l`. On the desktop: `schtasks /Change /TN MusicStream8121_VizUpdate /DISABLE`.

Re-enable: `python3 scripts/viz-update.py --on` and re-enable the task/cron line.

## Manual run

```
python3 scripts/viz-update.py --once
python3 scripts/viz-update.py --dry-run --once
python3 scripts/viz-update.py --once --limit 1 --max-bytes 400000
```
