#!/bin/zsh
# Copy one validated, sanitized status snapshot from Korea to the US panel.
set -euo pipefail

REPO=${REPO:-/Users/silas/Desktop/agentsociety}
EXP=$REPO/examples/v2/elder_support
KR_EXP=${KR_EXP:-/srv/agentsociety/examples/v2/elder_support}
KR_PY=${KR_PY:-/srv/agentsociety/.venv/bin/python}
US_PY=${US_PY:-/srv/agentsociety-panel/venv/bin/python}
KR_VM=${KR_VM:-silasvps-kr}
KR_ZONE=${KR_ZONE:-asia-northeast3-a}
US_VM=${US_VM:-silasvps}
US_ZONE=${US_ZONE:-us-west1-b}
KR_STATUS=${KR_STATUS:-/var/lib/elder-support-remote-status/status.json}
US_APP=${US_APP:-/srv/agentsociety-panel/app}
MAX_BYTES=${MAX_BYTES:-65536}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
local_status=$work/status.json
incoming=$work/status.incoming.json

# The exporter has its own timer in production. Running it here makes this script
# safe for an explicit one-shot refresh without touching the cohort directory.
gcloud compute ssh "$KR_VM" --zone "$KR_ZONE" --tunnel-through-iap \
  --command="sudo $KR_PY $KR_EXP/tools/export_remote_status.py"
gcloud compute scp --zone "$KR_ZONE" --tunnel-through-iap \
  "$KR_VM:$KR_STATUS" "$local_status"

size=$(wc -c < "$local_status" | tr -d ' ')
if (( size < 1 || size > MAX_BYTES )); then
  echo "Refusing snapshot size $size bytes" >&2
  exit 1
fi
PYTHONPATH="$EXP/panel" uv --directory "$REPO" run python - "$local_status" <<'PY'
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from remote_status import parse_snapshot

snapshot = parse_snapshot(Path(sys.argv[1]).read_bytes())
now = datetime.now(UTC)
if snapshot.collected_at > now + timedelta(minutes=2):
    raise SystemExit("snapshot collection time is in the future")
if snapshot.collected_at < now - timedelta(hours=2):
    raise SystemExit("snapshot is too old to install")
PY
cp "$local_status" "$incoming"

gcloud compute scp --zone "$US_ZONE" --tunnel-through-iap \
  "$incoming" "$US_VM:/tmp/elder-support-status.incoming.json"
gcloud compute ssh "$US_VM" --zone "$US_ZONE" --tunnel-through-iap --command="\
sudo env US_APP='$US_APP' MAX_BYTES='$MAX_BYTES' $US_PY - <<'PY'
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

app = Path(os.environ['US_APP'])
sys.path.insert(0, str(app / 'panel'))
from remote_status import parse_snapshot

incoming = Path('/tmp/elder-support-status.incoming.json')
target = app / 'remote_status' / 'status.json'
size = incoming.stat().st_size
if not 0 < size <= int(os.environ['MAX_BYTES']):
    raise SystemExit(f'invalid snapshot size: {size}')
new = parse_snapshot(incoming.read_bytes())
now = datetime.now(UTC)
if new.collected_at > now + timedelta(minutes=2):
    raise SystemExit('snapshot collection time is in the future')
if target.exists():
    old = parse_snapshot(target.read_bytes())
    if new.collected_at <= old.collected_at:
        raise SystemExit('snapshot collection time did not advance')
target.parent.mkdir(parents=True, exist_ok=True)
temporary = target.with_name('.status.incoming.json')
temporary.write_bytes(new.canonical_json().encode('utf-8'))
with temporary.open('rb') as stream:
    os.fsync(stream.fileno())
os.replace(temporary, target)
os.chmod(target, 0o644)
directory_fd = os.open(target.parent, os.O_RDONLY)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
incoming.unlink(missing_ok=True)
PY"

echo "Installed sanitized snapshot collected at $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["collected_at"])' "$local_status")"
