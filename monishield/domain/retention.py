"""Data retention rules (pure; owner request 2026-10-08). Which date folders are past their keeping period.

Two settings, 0 = keep forever:
  S4_RETENTION_DAYS        folders older than N days are removed from the database. Their log files are not touched;
                           ingest and the S3 sync skip folders past the cut-off, so they do not come back.
  S4_RETENTION_INBOX_DAYS  inbox folders (S3 imports, uploads, Kafka) older than N days are deleted from disk. Their data
                           stays in the database until S4_RETENTION_DAYS removes it.
Folder dates are WIB dates (a folder D holds the logs up to D 00:00 WIB). A folder is past the cut-off when its date is
before today minus N days.
"""
import datetime

MIN_DAYS = 8         # the dashboard compares a folder with the average of the 7 before it (Command Center, notifications)
MIN_INBOX_DAYS = 2   # the S3 sync re-checks yesterday's folder; its inbox copy must still be there
MAX_DAYS = 3650


def today_wib(now_utc): return (now_utc + datetime.timedelta(hours=7)).date()


def cutoff(today, days):
    """-> 'YYYY-MM-DD' (folders before it are past the period) or None (keep forever)."""
    return (today - datetime.timedelta(days=days)).isoformat() if days else None


def expired(folder, cut): return cut is not None and str(folder) < cut


def keep(folders, cut): return [f for f in folders if not expired(f, cut)]


def watch_days(s3_watch_days, retention_days):
    """Days the S3 sync looks back: never further than the database keeps (else it would fetch what retention removes)."""
    if not retention_days: return s3_watch_days
    return min(s3_watch_days, retention_days) if s3_watch_days else retention_days


def plan(db_folders, inbox_folders, today, days, inbox_days):
    cut_db, cut_inbox = cutoff(today, days), cutoff(today, inbox_days)
    return dict(cutoff_db=cut_db, cutoff_inbox=cut_inbox,
                db=sorted(f for f in db_folders if expired(f, cut_db)), inbox=sorted(f for f in inbox_folders if expired(f, cut_inbox)))


def validate(days, inbox_days):
    """-> error message or None."""
    if days and not MIN_DAYS <= days <= MAX_DAYS:
        return f'Database retention must be 0 (keep forever) or {MIN_DAYS}–{MAX_DAYS} days: the dashboard compares each folder with the 7 before it.'
    if inbox_days and not MIN_INBOX_DAYS <= inbox_days <= MAX_DAYS:
        return f'Inbox retention must be 0 (keep forever) or {MIN_INBOX_DAYS}–{MAX_DAYS} days.'
    return None
