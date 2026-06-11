#!/usr/bin/env bats

setup() {
  export HEALTH_PROBE_SKIP_LAUNCHD=1
  export HEALTH_PROBE_BRIDGE_PORT=18081
  export HEALTH_PROBE_BRIDGE_BUSINESS_PORT=18082
  export HEALTH_PROBE_NOTIFY_PORT=18083
}

teardown() {
  if [[ -n "${server_one_pid:-}" ]]; then
    kill "$server_one_pid" 2>/dev/null || true
  fi
  if [[ -n "${server_two_pid:-}" ]]; then
    kill "$server_two_pid" 2>/dev/null || true
  fi
  if [[ -n "${server_three_pid:-}" ]]; then
    kill "$server_three_pid" 2>/dev/null || true
  fi
}

start_http_server() {
  local port="$1"
  python3 -m http.server "$port" --bind 127.0.0.1 >/dev/null 2>&1 &
  echo "$!"
}

wait_for_port() {
  local port="$1"
  local attempt
  for attempt in {1..40}; do
    if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

require_port() {
  local port="$1"
  if ! wait_for_port "$port"; then
    echo "Server on port $port failed to start" >&2
    return 1
  fi
}

@test "prints one-line OK summary when all services are reachable" {
  server_one_pid="$(start_http_server "$HEALTH_PROBE_BRIDGE_PORT")"
  server_two_pid="$(start_http_server "$HEALTH_PROBE_BRIDGE_BUSINESS_PORT")"
  server_three_pid="$(start_http_server "$HEALTH_PROBE_NOTIFY_PORT")"
  require_port "$HEALTH_PROBE_BRIDGE_PORT"
  require_port "$HEALTH_PROBE_BRIDGE_BUSINESS_PORT"
  require_port "$HEALTH_PROBE_NOTIFY_PORT"

  run bash scripts/health-probe.sh

  [ "$status" -eq 0 ]
  [[ "$output" == OK:* ]]
  [[ "$output" == *"bridge (18081)"* ]]
  [[ "$output" == *"bridge-business (18082)"* ]]
  [[ "$output" == *"notify-server (18083)"* ]]
}

@test "prints loud DOWN line and exits non-zero for unreachable service" {
  server_one_pid="$(start_http_server "$HEALTH_PROBE_BRIDGE_PORT")"
  server_three_pid="$(start_http_server "$HEALTH_PROBE_NOTIFY_PORT")"
  require_port "$HEALTH_PROBE_BRIDGE_PORT"
  require_port "$HEALTH_PROBE_NOTIFY_PORT"

  run bash scripts/health-probe.sh

  [ "$status" -ne 0 ]
  [[ "$output" == *"DOWN: bridge-business (18082)"* ]]
}
