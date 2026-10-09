#!/usr/bin/env bash
set -euo pipefail

PACKAGE='com.sharkecho.ai_translator'
APK='source/mobile/build/app/outputs/flutter-apk/app-release.apk'

fail() {
  echo "EMULATOR_GATE=$1" >&2
  exit 1
}

assert_flutter_home() {
  local stage="$1" xml
  [[ "$(adb get-state 2>/dev/null || true)" == device ]] || fail "FAIL_DEVICE_CONNECTION_${stage}"
  for _ in 1 2 3; do
    if adb shell uiautomator dump /sdcard/trustlyta-smoke.xml >/dev/null 2>&1; then
      xml="$(adb shell cat /sdcard/trustlyta-smoke.xml 2>/dev/null || true)"
      if [[ "$xml" == *"package=\"$PACKAGE\""* && "$xml" == *'翻译文字'* && "$xml" == *'语音翻译'* ]]; then
        echo "FLUTTER_HOME_${stage}=PASS"
        return 0
      fi
    fi
    sleep 2
  done
  fail "FAIL_FLUTTER_HOME_${stage}"
}

[[ -f "$APK" ]] || fail FAIL_SCRIPT_APK_MISSING
adb install -r "$APK" >/tmp/trustlyta-install.log 2>&1 || { cat /tmp/trustlyta-install.log; fail FAIL_INSTALL; }

for attempt in 1 2 3; do
  adb logcat -c -b crash
  start_output="$(adb shell am start -W -n "$PACKAGE/.MainActivity" 2>&1 || true)"
  printf '%s\n' "$start_output"
  sleep 5
  pid="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
  [[ -n "$pid" ]] || fail FAIL_APP_EXIT_${attempt}
  activity="$(adb shell dumpsys activity activities 2>/dev/null || true)"
  window="$(adb shell dumpsys window windows 2>/dev/null || true)"
  if ! printf '%s\n%s\n' "$activity" "$window" | grep -Eq "$PACKAGE|mCurrentFocus"; then
    fail FAIL_FIRST_FRAME_${attempt}
  fi
  assert_flutter_home "$attempt"
  crash="$(adb logcat -d -b crash -v threadtime 2>/dev/null || true)"
  if printf '%s\n' "$crash" | grep -Eq 'FATAL EXCEPTION|Fatal signal|ANR in'; then
    printf '%s\n' "$crash" | tail -160
    fail FAIL_APP_FATAL_${attempt}
  fi
  sleep 30
  pid="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
  [[ -n "$pid" ]] || fail FAIL_APP_EXIT_AFTER_30S_${attempt}
  echo "STARTUP_ATTEMPT_${attempt}=PASS"
  adb shell am force-stop "$PACKAGE"
done

adb shell svc wifi disable >/dev/null 2>&1 || true
adb shell svc data disable >/dev/null 2>&1 || true
adb shell am start -W -n "$PACKAGE/.MainActivity" || fail FAIL_OFFLINE_START
sleep 8
pid="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
[[ -n "$pid" ]] || fail FAIL_OFFLINE_EXIT
activity="$(adb shell dumpsys activity activities 2>/dev/null || true)"
window="$(adb shell dumpsys window windows 2>/dev/null || true)"
printf '%s\n%s\n' "$activity" "$window" | grep -Eq "$PACKAGE|mCurrentFocus" || fail FAIL_OFFLINE_FIRST_FRAME
assert_flutter_home OFFLINE
adb shell svc wifi enable >/dev/null 2>&1 || true
adb shell svc data enable >/dev/null 2>&1 || true
echo 'OFFLINE_FIRST_FRAME=PASS'
echo 'EMULATOR_INSTALL_LAUNCH_SMOKE=PASS'
