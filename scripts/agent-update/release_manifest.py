#!/usr/bin/env python3
"""Fail-closed versioned GitHub Release metadata for GPT-AndroidOS.

No APK or keystore is handled by this script. Called by the manual,
protected release workflow after signing and before publishing metadata.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

REPOSITORY = "Sharkecho/Public-Build-Farm"
MIN_PRODUCTION_VERSION = 3
MAX_VERSION = 999999999
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def checked_code(text: str, previous: int) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise ValueError("version_code must be a positive decimal integer")
    code = int(text)
    if code < MIN_PRODUCTION_VERSION or code > MAX_VERSION:
        raise ValueError("version_code outside supported release range")
    if code <= previous:
        raise ValueError("version_code must increase beyond last published release")
    return code


def current_code(path: Path) -> int:
    info = json.loads(path.read_text(encoding="utf-8"))
    if info.get("schema_version") != 1:
        raise ValueError("unknown update manifest schema")
    value = info.get("version_code")
    if type(value) is not int or value < 0:
        raise ValueError("invalid current manifest version")
    return value


def signed_release(code: int, digest: str, cert_digest: str) -> dict:
    digest, cert_digest = digest.lower(), cert_digest.lower().replace(":", "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("invalid APK SHA-256")
    if not SHA256_PATTERN.fullmatch(cert_digest):
        raise ValueError("invalid signing certificate SHA-256")
    return {
        "schema_version": 1,
        "version_code": code,
        "version_name": f"0.2.0-gpt.{code}",
        "apk_url": (
            f"https://github.com/{REPOSITORY}/releases/download/"
            f"gpt-androidos-v{code}/gpt-androidos.apk"
        ),
        "sha256": digest,
        "certificate_sha256": cert_digest,
        "status": "SIGNED_RELEASE",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=Path("updates/gpt-androidos/stable.json"))
    parser.add_argument("--version-code", required=True)
    parser.add_argument("--sha256")
    parser.add_argument("--certificate-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    code = checked_code(args.version_code, current_code(args.current))
    if not args.output:
        print(f"Release version {code} is newer than current stable manifest.")
        return
    if not (args.sha256 and args.certificate_sha256):
        parser.error("--sha256 and --certificate-sha256 are required with --output")
    release = signed_release(code, args.sha256, args.certificate_sha256)
    args.output.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared stable metadata for signed version {code}")


if __name__ == "__main__":
    main()
