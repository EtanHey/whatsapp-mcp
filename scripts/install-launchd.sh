#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
template_path="${repo_root}/launchd/com.whatsapp-mcp.health-probe.plist.template"
target_path="${HOME}/Library/LaunchAgents/com.whatsapp-mcp.health-probe.plist"
service_name="gui/$(id -u)/com.whatsapp-mcp.health-probe"

mkdir -p "$(dirname -- "$target_path")"

python3 - "$template_path" "$target_path" "$repo_root" <<'PY'
from pathlib import Path
import sys

template_path, target_path, repo_root = sys.argv[1:]
template = Path(template_path).read_text()
Path(target_path).write_text(template.replace("{{PROJECT_PATH}}", repo_root))
PY

plutil -lint "$target_path"

if launchctl print "$service_name" >/dev/null 2>&1; then
  launchctl kickstart -k "$service_name"
else
  launchctl bootstrap "gui/$(id -u)" "$target_path"
fi

printf 'Installed %s\n' "$target_path"
