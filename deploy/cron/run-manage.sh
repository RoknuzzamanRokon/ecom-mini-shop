#!/bin/sh
# Runs one manage.py command for cron (deploy/cron/minishop.crontab).
#
#     run-manage.sh <command> [arguments...]
#
# Settings, each from the environment (the crontab sets MINISHOP_ROOT):
#   MINISHOP_ROOT           the checkout (default: two folders above this script)
#   MINISHOP_PYTHON         the interpreter (default: $MINISHOP_ROOT/backend/venv/bin/python)
#   MINISHOP_LOG_DIR        where the logs go (default: $MINISHOP_ROOT/logs/cron)
#   DJANGO_SETTINGS_MODULE  default: config.settings.prod
#
# Each command appends to its own <command>.log. A lock per command makes a
# run that finds the previous one still going skip itself instead of piling
# up behind it. A failure is also printed to stderr, so cron mails it when
# the crontab sets MAILTO.
set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 <manage.py command> [arguments...]" >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=${MINISHOP_ROOT:-$(dirname -- "$(dirname -- "$script_dir")")}
python=${MINISHOP_PYTHON:-$root/backend/venv/bin/python}
log_dir=${MINISHOP_LOG_DIR:-$root/logs/cron}
name=$1
log=$log_dir/$name.log
lock=$log_dir/$name.lock

if [ ! -x "$python" ]; then
    echo "$0: no Python interpreter at $python (set MINISHOP_PYTHON)" >&2
    exit 1
fi
mkdir -p "$log_dir"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"
cd "$root/backend"

started=$(date '+%Y-%m-%d %H:%M:%S %z')
echo "--- $started manage.py $*" >>"$log"
status=0
# 75 (EX_TEMPFAIL) means the lock is held: the previous run is still going.
flock --nonblock --conflict-exit-code 75 "$lock" "$python" manage.py "$@" >>"$log" 2>&1 || status=$?

case $status in
    0) ;;
    75)
        echo "skipped: the run before it still holds $lock" >>"$log"
        status=0
        ;;
    *)
        echo "failed with exit code $status" >>"$log"
        echo "$started manage.py $* failed with exit code $status; see $log" >&2
        ;;
esac
exit $status
