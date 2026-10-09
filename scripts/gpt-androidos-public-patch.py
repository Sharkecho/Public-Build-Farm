#!/usr/bin/env python3
"""Apply only public, GUI-level Android Agent customization to pinned ClawGUI.

This script is deliberately independent of any private GPT-AndroidOS repo,
audio model, Android ROM, token or hardware API. It is idempotent.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ALIASES = (
    '        "声音工作站" to "com.note9.uac2",',
    '        "USB 音频控制" to "com.note9.uac2",',
    '        "Note9 LiveAudio" to "com.note9.uac2",',
)
ANCHOR = "        // Social & Messaging"
OLD_LABEL = '<string name="app_name">ClawGUI</string>'
NEW_LABEL = '<string name="app_name">GPT-AndroidOS</string>'


def update_file(path: Path, old: str, new: str, verify_only: bool) -> None:
    data = path.read_text(encoding="utf-8")
    if old not in data and new not in data:
        raise RuntimeError(f"upstream patch anchor missing: {path}")
    if new in data:
        if old in data:
            raise RuntimeError(f"ambiguous partial patch: {path}")
        return
    if data.count(old) != 1:
        raise RuntimeError(f"upstream patch anchor not unique: {path}")
    if verify_only:
        raise RuntimeError(f"patch not applied: {path}")
    path.write_text(data.replace(old, new, 1), encoding="utf-8")


def apply(root: Path, verify_only: bool) -> None:
    apps = root / "app/src/main/kotlin/com/clawgui/ng/runtime/phone/config/Apps.kt"
    strings = root / "app/src/main/res/values/strings.xml"
    data = apps.read_text(encoding="utf-8")
    existing = [alias in data for alias in ALIASES]
    if all(existing):
        pass
    elif any(existing):
        raise RuntimeError("partially patched Apps.kt; refusing to write")
    else:
        if data.count(ANCHOR) != 1:
            raise RuntimeError("upstream Apps.kt anchor not unique")
        if verify_only:
            raise RuntimeError("audio aliases not applied")
        apps.write_text(data.replace(ANCHOR, "\n".join(ALIASES) + "\n" + ANCHOR, 1), encoding="utf-8")
    update_file(strings, OLD_LABEL, NEW_LABEL, verify_only)
    check = apps.read_text(encoding="utf-8")
    label = strings.read_text(encoding="utf-8")
    if not all(a in check for a in ALIASES) or NEW_LABEL not in label:
        raise RuntimeError("post-patch validation failed")
    print("GUI_AUDIO_ALIAS=PASS")
    print("APP_NAME=GPT-AndroidOS")
    print("REALTIME_AUDIO_UNCHANGED=YES")
    print("PRIVILEGED_AUDIO_BRIDGE=NOT_IMPLEMENTED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    apply(args.source, args.verify_only)


if __name__ == "__main__":
    main()
