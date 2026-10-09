#!/usr/bin/env python3
"""Read-only Android device smoke check, with an explicit opt-in APK install.

Run on a PC connected via ADB (not inside GitHub's cloud runner). No root,
no background phone service, no logcat, no model/voice/recording collection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENT_PKG = "com.clawgui.ng"
AUDIO_PKG = "com.note9.uac2"


class DeviceError(RuntimeError):
    pass


def adb_run(adb: str, parts: list[str], serial: str | None = None, timeout: int = 30) -> str:
    args = [adb] + (["-s", serial] if serial else []) + parts
    try:
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise DeviceError(f"ADB unavailable or timed out for action: {parts[0]}") from exc
    if proc.returncode:
        raise DeviceError(f"ADB action failed: {parts[0]}, exit={proc.returncode}")
    return proc.stdout.strip()


def choose_serial(adb: str, preferred: str | None) -> str:
    lines = adb_run(adb, ["devices"]).splitlines()[1:]
    connected = [m.group(1) for line in lines
                 if (m := re.fullmatch(r"\s*(\S+)\s+device\s*", line))]
    if preferred:
        if preferred not in connected:
            raise DeviceError("Requested device serial is not connected and authorized")
        return preferred
    if len(connected) != 1:
        raise DeviceError("Connect and authorize exactly one Android device, or specify --serial")
    return connected[0]


def hash_file(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_installed(adb: str, serial: str, package: str) -> bool:
    output = adb_run(adb, ["shell", "pm", "path", package], serial)
    return any(s.strip().startswith("package:") for s in output.splitlines())


def getprop(adb: str, serial: str, name: str) -> str:
    return adb_run(adb, ["shell", "getprop", name], serial)


def smoke(adb: str, serial: str | None = None, apk: Path | None = None,
          expected_sha256: str | None = None, install: bool = False,
          launch_agent: bool = False) -> dict:
    device = choose_serial(adb, serial)
    model = getprop(adb, device, "ro.product.model")
    sdk = getprop(adb, device, "ro.build.version.sdk")
    boot = getprop(adb, device, "sys.boot_completed")
    if boot != "1":
        raise DeviceError("Device has not finished booting; refusing to install or launch")

    installed_by_script = False
    if install:
        if apk is None or not expected_sha256 or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
            raise DeviceError("--install requires --apk and a 64-character --expected-sha256")
        if not apk.is_file():
            raise DeviceError("APK file not found")
        actual = hash_file(apk)
        if actual.lower() != expected_sha256.lower():
            raise DeviceError("APK SHA-256 differs from pinned build; refusing installation")
        result = adb_run(adb, ["install", "-r", str(apk.resolve())], device, timeout=120)
        if "Success" not in result:
            raise DeviceError("ADB install did not report Success")
        installed_by_script = True

    agent_present = is_installed(adb, device, AGENT_PKG)
    audio_present = is_installed(adb, device, AUDIO_PKG)
    launched = False
    if launch_agent:
        if not agent_present:
            raise DeviceError("Agent package is not installed; cannot launch")
        result = adb_run(adb, ["shell", "monkey", "-p", AGENT_PKG,
                               "-c", "android.intent.category.LAUNCHER", "1"], device)
        if "Events injected: 1" not in result:
            raise DeviceError("Agent launch could not be confirmed")
        launched = True

    return {
        "schema_version": 1, "utc": datetime.now(timezone.utc).isoformat(),
        "device_model": model, "android_sdk": sdk, "boot_completed": boot == "1",
        "agent_package": AGENT_PKG, "agent_installed": agent_present,
        "audio_package": AUDIO_PKG, "audio_installed": audio_present,
        "apk_installed_this_run": installed_by_script, "agent_launched": launched,
        "gui_task_test": "UNVERIFIED", "audio_ipc": "NOT_IMPLEMENTED",
        "rom_integration": "UNVERIFIED",
        "result": "SMOKE_PASS" if agent_present and (not launch_agent or launched) else "AGENT_NOT_INSTALLED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--install", action="store_true", help="explicitly opt in to updating the Agent APK")
    parser.add_argument("--launch-agent", action="store_true", help="explicitly opt in to launching the Agent")
    parser.add_argument("--report", type=Path, help="optional local-only, sanitized JSON report")
    args = parser.parse_args()
    try:
        report = smoke(args.adb, args.serial, args.apk, args.expected_sha256,
                       args.install, args.launch_agent)
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        print(payload)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload + "\n", encoding="utf-8")
        return 0 if report["result"] == "SMOKE_PASS" else 2
    except DeviceError as exc:
        print(json.dumps({"result": "FAIL", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
