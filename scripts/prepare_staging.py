"""Run ON THE TARGET SERVER interactively. Never prints generated secrets."""
from getpass import getpass
from pathlib import Path
import hashlib, os, secrets

root = Path(__file__).resolve().parents[1] / 'infra/staging'
folder = root / 'secrets'
if folder.exists():
    raise SystemExit('Secrets already exist; refusing to overwrite credentials.')
password = getpass('New staging admin password (16+ characters): ')
if len(password) < 16 or password != getpass('Confirm password: '):
    raise SystemExit('Passwords must match and contain at least 16 characters.')
salt = secrets.token_bytes(16)
digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
db = secrets.token_hex(32)
values = {'admin_hash': f'scrypt${salt.hex()}${digest}', 'db_password': db,
          'database_url': f'postgresql+psycopg://agn:{db}@postgres:5432/agn',
          'backup_passphrase': secrets.token_urlsafe(48)}
folder.mkdir(mode=0o700)
for name, value in values.items():
    fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(value + '\n')
# Compose file secrets retain host permissions. Permit the non-root API reader
# through its numeric group; the parent directory remains accessible only to owner.
for name in ('admin_hash','database_url'):
    try: os.chown(folder / name, -1, 10001)
    except PermissionError: raise SystemExit('Run setup with sudo so API secret permissions can be assigned.')
    os.chmod(folder / name, 0o640)
# PostgreSQL drops privileges inside its container before reading this file.
# The host parent remains mode 0700; only explicitly mounted containers see it.
os.chmod(folder / 'db_password', 0o444)
(root / 'backups').mkdir(mode=0o700, exist_ok=True)
print('Credentials prepared. Store backup_passphrase separately in a password manager. Never commit secrets.')
