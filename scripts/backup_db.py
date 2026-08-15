"""
Rentritz Dubai - PostgreSQL backup script.

Reads DATABASE_URL from .env, dumps the database with pg_dump using a
timestamped filename, saves it to backups/ at the project root, and
automatically removes backups older than 7 days.

─── SCHEDULE AS A DAILY WINDOWS TASK (run once in an elevated Command Prompt) ───

  schtasks /create /sc daily /tn "RentritzBackup" /tr "python C:\\Users\\BSO Employee\\Documents\\rentright\\scripts\\backup_db.py" /st 02:00

Other useful commands:
  schtasks /query  /tn "RentritzBackup"        # check status
  schtasks /delete /tn "RentritzBackup" /f     # remove the scheduled task

pg_dump must be on PATH (installed with PostgreSQL). If not, use the full path,
e.g. "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_dump.exe".
─────────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Load .env from the project root (one level up from scripts/)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass  # python-dotenv not available; rely on env vars already set

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print('ERROR: DATABASE_URL not set in .env')
    sys.exit(1)

# Normalise postgres:// -> postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

parsed   = urlparse(DATABASE_URL)
db_host  = parsed.hostname or 'localhost'
db_port  = str(parsed.port or 5432)
db_name  = parsed.path.lstrip('/')
db_user  = parsed.username or ''
db_pass  = parsed.password or ''

if not db_name:
    print('ERROR: Could not parse database name from DATABASE_URL')
    sys.exit(1)

# Resolve backups/ directory relative to this script's project root
BACKUP_DIR = Path(__file__).parent.parent / 'backups'
BACKUP_DIR.mkdir(exist_ok=True)

# Timestamped filename - custom (compressed) pg_dump format
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_file = BACKUP_DIR / f'rentritz_{timestamp}.dump'

# Inject password via environment variable (never via command-line argument)
env = os.environ.copy()
env['PGPASSWORD'] = db_pass

cmd = [
    'pg_dump',
    '-h', db_host,
    '-p', db_port,
    '-U', db_user,
    '-F', 'c',            # custom format: compressed and restore-able with pg_restore
    '-f', str(backup_file),
    db_name,
]

print(f'Starting backup -> {backup_file}')
result = subprocess.run(cmd, env=env, capture_output=True, text=True)

if result.returncode != 0:
    print(f'ERROR: pg_dump exited with code {result.returncode}')
    if result.stderr:
        print(result.stderr.strip())
    sys.exit(1)

size_kb = backup_file.stat().st_size // 1024
print(f'Backup complete: {backup_file.name} ({size_kb} KB)')

# ── Prune backups older than 7 days ──────────────────────────────────────────
cutoff  = datetime.now() - timedelta(days=7)
deleted = 0
for old_file in BACKUP_DIR.glob('rentritz_*.dump'):
    if datetime.fromtimestamp(old_file.stat().st_mtime) < cutoff:
        old_file.unlink()
        deleted += 1
        print(f'Deleted old backup: {old_file.name}')

if deleted:
    print(f'Pruned {deleted} backup(s) older than 7 days.')
else:
    print('No old backups to prune.')
