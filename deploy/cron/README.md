# Cron jobs

MiniShop has no scheduler of its own. These files run its periodic
`manage.py` commands from cron on a Linux server.

| When | Command | What it does |
|---|---|---|
| Every minute | `run_notification_worker --once` | Routes notifications and sends their email. |
| Every 5 minutes | `notification_health` | Prints, and so mails, only when the notification pipeline is unhealthy. |
| 00:05 | `expire_points` | Expires seller and staff points that reached their date. |
| 02:00 | `close_resolved_tickets` | Closes resolved support tickets left without a reply. |
| 03:30 | `purge_notifications` | Deletes notification rows past their retention. |
| 09:00 | `expire_listings` | Expires ended product listings and sends the ending-soon notices. |

Each job also works without cron. Points and listings expire on their own
whenever someone reads them, so a missed run only delays statuses, the
Console counts and the notices.

## Install

1. Check out the project at `/srv/minishop` (or change `MINISHOP_ROOT` in
   `minishop.crontab`), with the virtualenv at `backend/venv` and
   `backend/.env` holding the production settings.
2. Make the script executable: `chmod +x deploy/cron/run-manage.sh`.
3. Try one job by hand as the user that runs the app:

   ```sh
   MINISHOP_ROOT=/srv/minishop deploy/cron/run-manage.sh expire_listings --dry-run
   cat /srv/minishop/logs/cron/expire_listings.log
   ```

4. Install the crontab for that user. This **replaces** the user's crontab, so
   if it already has one, add these lines to it with `crontab -e` instead:

   ```sh
   crontab -u minishop deploy/cron/minishop.crontab
   crontab -u minishop -l
   ```

5. Set the server's time zone to Asia/Dhaka (`timedatectl set-timezone
   Asia/Dhaka`), or move the times. Set `MAILTO` to get failure mail.

## Logs

`run-manage.sh` appends each command's output to
`logs/cron/<command>.log`, with a header line per run. A failure is also
printed to stderr, so cron mails it. A run that finds the previous one still
going skips itself and says so in the log.

The worker writes two lines a minute, so rotate the logs, for example with
`/etc/logrotate.d/minishop`:

```
/srv/minishop/logs/cron/*.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

## Settings

`run-manage.sh` reads these from the environment:

- `MINISHOP_ROOT`: the checkout. The crontab sets it.
- `MINISHOP_PYTHON`: the interpreter. Default: `backend/venv/bin/python`.
- `MINISHOP_LOG_DIR`: the log folder. Default: `logs/cron`.
- `DJANGO_SETTINGS_MODULE`: default `config.settings.prod`.

On Windows, use Task Scheduler instead:
`docs/NOTIFICATION_SYSTEM.md` §17.3 and §17.5 show how.
