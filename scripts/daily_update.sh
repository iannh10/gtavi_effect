#!/usr/bin/env bash
# Daily GTA V halo-test update: collect -> track -> commit -> push.
# Loaded by ~/Library/LaunchAgents/com.ianhuang.gtavi-daily.plist (7:00 AM PT).
# Self-disables after FINAL_RUN_DATE.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/.venv"
LOGDIR="$REPO/logs"
LOGFILE="$LOGDIR/daily_update.log"
FINAL_RUN_DATE="2027-01-05"
LAUNCHD_LABEL="com.ianhuang.gtavi-daily"

mkdir -p "$LOGDIR"
log() { printf "[%s] %s\n" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*" | tee -a "$LOGFILE"; }
die() { log "ERROR: $*"; exit 1; }

log "--- daily_update start ---"

# Use Python for a portable local-date comparison (macOS BSD date is awkward).
TODAY="$(python3 -c 'from datetime import date; print(date.today().isoformat())')"
log "today=$TODAY  final_run_date=$FINAL_RUN_DATE"

# Past the final run date: unload and exit cleanly.
if python3 -c "import sys; sys.exit(0 if '$TODAY' > '$FINAL_RUN_DATE' else 1)"; then
    log "Past final run date; job disabled"
    launchctl bootout "gui/$(id -u)/$LAUNCHD_LABEL" 2>/dev/null || true
    exit 0
fi

# Activate venv.
# shellcheck disable=SC1091
source "$VENV/bin/activate" || die "venv not found at $VENV; run: python -m venv $VENV && pip install -r $REPO/requirements.txt"

cd "$REPO"

# Pull remote changes first so the working tree is clean before data files are written.
log "git pull --rebase..."
git pull --rebase --autostash >> "$LOGFILE" 2>&1 || die "git pull --rebase failed"

# Collect: backfill is idempotent and catches any missed days.
log "collect_players backfill..."
python scripts/collect_players.py backfill >> "$LOGFILE" 2>&1 || die "backfill failed"

# Track: hash check runs first; exits non-zero if frozen files changed.
log "halo.track..."
python -m halo.track >> "$LOGFILE" 2>&1 || die "halo.track failed"

# Stage only the data/output files (never frozen files or code).
git add data/post/ outputs/tracker/ outputs/dashboard/ >> "$LOGFILE" 2>&1

if git diff --cached --quiet; then
    log "Nothing changed; skipping commit."
else
    if [ "$TODAY" = "$FINAL_RUN_DATE" ]; then
        COMMIT_MSG="Final scoring run $FINAL_RUN_DATE"
        log "FINAL RUN COMPLETE: review outputs/tracker/ and tag results-v1"
    else
        COMMIT_MSG="Daily update $TODAY"
    fi
    git commit -m "$COMMIT_MSG

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" >> "$LOGFILE" 2>&1 || die "git commit failed"
    git push >> "$LOGFILE" 2>&1 || die "git push failed"
    log "Pushed: $COMMIT_MSG"
fi

log "--- daily_update done ---"
