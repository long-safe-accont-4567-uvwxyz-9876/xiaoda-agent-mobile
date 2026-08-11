#!/usr/bin/env bash
set -euo pipefail

launch_variant() {
  local label="$1"
  local package_name="$2"
  local apk_path="$3"

  echo "Installing ${label}: ${apk_path}"
  adb install -r "$apk_path"
  adb shell am force-stop "$package_name" || true
  adb logcat -c

  local launch_output
  launch_output="$(adb shell am start -W -n "${package_name}/com.xiaoda.agent.MainActivity")"
  echo "$launch_output"
  if ! grep -q "Status: ok" <<<"$launch_output"; then
    echo "${label} failed to report a successful Activity launch" >&2
    adb logcat -d '*:E' >&2 || true
    return 1
  fi

  sleep 4
  local pid
  pid="$(adb shell pidof "$package_name" | tr -d '' | xargs)"
  if [[ -z "$pid" ]]; then
    echo "${label} process exited after launch" >&2
    adb logcat -d '*:E' >&2 || true
    return 1
  fi

  local fatal_log
  fatal_log="$(adb logcat --pid="$pid" -d 2>/dev/null | grep -E 'FATAL EXCEPTION|AndroidRuntime: Process:' || true)"
  if [[ -n "$fatal_log" ]]; then
    echo "${label} emitted a fatal Android runtime error" >&2
    echo "$fatal_log" >&2
    return 1
  fi

  echo "${label} launch smoke test passed with pid ${pid}"
  adb shell am force-stop "$package_name"
  adb uninstall "$package_name" >/dev/null || true
}

launch_variant "debug" "com.xiaoda.agent.debug" "app/build/outputs/apk/debug/app-debug.apk"
launch_variant "staging" "com.xiaoda.agent.staging" "app/build/outputs/apk/staging/app-staging.apk"
launch_variant "release" "com.xiaoda.agent" "app/build/outputs/apk/release/app-release.apk"
