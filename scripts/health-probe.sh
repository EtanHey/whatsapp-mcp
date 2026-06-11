#!/usr/bin/env bash
set -euo pipefail

HOST="${HEALTH_PROBE_HOST:-127.0.0.1}"
TIMEOUT_SECONDS="${HEALTH_PROBE_TIMEOUT_SECONDS:-3}"
BRIDGE_LABEL="${HEALTH_PROBE_BRIDGE_LABEL:-com.whatsapp-mcp.bridge}"
BRIDGE_BUSINESS_LABEL="${HEALTH_PROBE_BRIDGE_BUSINESS_LABEL:-com.whatsapp-mcp.bridge-business}"
NOTIFY_LABEL="${HEALTH_PROBE_NOTIFY_LABEL:-com.golemszikaron.telegram}"
LAUNCH_AGENTS_DIR="${HEALTH_PROBE_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

is_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( "$1" > 0 && "$1" < 65536 ))
}

plist_path_for_label() {
  local label="$1"
  local path="${LAUNCH_AGENTS_DIR}/${label}.plist"

  if [[ -f "$path" ]]; then
    printf '%s\n' "$path"
  fi
}

launchd_env_value() {
  local label="$1"
  local var_name="$2"
  local plist_path

  if [[ "${HEALTH_PROBE_SKIP_LAUNCHD:-0}" == "1" ]]; then
    return 1
  fi

  plist_path="$(plist_path_for_label "$label")"
  if [[ -z "$plist_path" ]]; then
    return 1
  fi

  plutil -extract "EnvironmentVariables.${var_name}" raw -o - "$plist_path" 2>/dev/null || true
}

launchd_stdout_path() {
  local label="$1"
  local plist_path

  if [[ "${HEALTH_PROBE_SKIP_LAUNCHD:-0}" == "1" ]]; then
    return 1
  fi

  plist_path="$(plist_path_for_label "$label")"
  if [[ -z "$plist_path" ]]; then
    return 1
  fi

  plutil -extract StandardOutPath raw -o - "$plist_path" 2>/dev/null || true
}

port_from_bridge_log() {
  local label="$1"
  local log_path
  local matches

  log_path="$(launchd_stdout_path "$label")"
  if [[ -z "$log_path" || ! -f "$log_path" ]]; then
    return 1
  fi

  matches="$(grep -Eo 'Starting REST API server on :[0-9]+' "$log_path" 2>/dev/null || true)"
  if [[ -z "$matches" ]]; then
    return 1
  fi

  printf '%s\n' "$matches" | tail -n 1 | sed -E 's/.*:([0-9]+)$/\1/'
}

resolve_port() {
  local override_value="$1"
  local label="$2"
  local launchd_var="$3"
  local fallback_port="$4"
  local resolved=""

  if [[ -n "$override_value" ]]; then
    resolved="$override_value"
  else
    resolved="$(launchd_env_value "$label" "$launchd_var" || true)"
    if [[ -z "$resolved" ]]; then
      resolved="$(port_from_bridge_log "$label" || true)"
    fi
    if [[ -z "$resolved" ]]; then
      resolved="$fallback_port"
    fi
  fi

  if ! is_port "$resolved"; then
    printf 'DOWN: %s (invalid port: %s)\n' "$label" "$resolved"
    return 1
  fi

  printf '%s\n' "$resolved"
}

probe_port() {
  local service_name="$1"
  local port="$2"

  if nc -z -w "$TIMEOUT_SECONDS" "$HOST" "$port" >/dev/null 2>&1; then
    return 0
  fi

  printf 'DOWN: %s (%s)\n' "$service_name" "$port"
  return 1
}

main() {
  local bridge_port
  local bridge_business_port
  local notify_port
  local failures=0
  local ok_services=()

  bridge_port="$(resolve_port "${HEALTH_PROBE_BRIDGE_PORT:-}" "$BRIDGE_LABEL" WHATSAPP_BRIDGE_PORT 8741)" || return 1
  bridge_business_port="$(resolve_port "${HEALTH_PROBE_BRIDGE_BUSINESS_PORT:-}" "$BRIDGE_BUSINESS_LABEL" WHATSAPP_BRIDGE_PORT 8742)" || return 1
  notify_port="$(resolve_port "${HEALTH_PROBE_NOTIFY_PORT:-}" "$NOTIFY_LABEL" NOTIFY_SERVER_PORT 3847)" || return 1

  if probe_port "bridge" "$bridge_port"; then
    ok_services+=("bridge (${bridge_port})")
  else
    failures=$((failures + 1))
  fi

  if probe_port "bridge-business" "$bridge_business_port"; then
    ok_services+=("bridge-business (${bridge_business_port})")
  else
    failures=$((failures + 1))
  fi

  if probe_port "notify-server" "$notify_port"; then
    ok_services+=("notify-server (${notify_port})")
  else
    failures=$((failures + 1))
  fi

  if (( failures > 0 )); then
    return 1
  fi

  local summary
  printf -v summary '%s, ' "${ok_services[@]}"
  printf 'OK: %s\n' "${summary%, }"
}

main "$@"
