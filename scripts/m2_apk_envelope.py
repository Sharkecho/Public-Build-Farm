#!/usr/bin/env python3
"""Encrypt a review APK for private-repository delivery; never publish plaintext."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"M2APKv1\0"
MAX_APK_BYTES = 300 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encrypt(apk: bytes, source_sha: str, public_key_pem: bytes) -> tuple[bytes, dict]:
    if not SHA_PATTERN.fullmatch(source_sha):
        raise ValueError("Invalid immutable source SHA")
    if not apk.startswith(b"PK") or not 0 < len(apk) <= MAX_APK_BYTES:
        raise ValueError("Invalid or oversized APK")
    public_key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(public_key, rsa.RSAPublicKey) or public_key.key_size < 3072:
        raise ValueError("Review delivery requires a 3072-bit RSA public key")
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    wrapped = public_key.encrypt(
        key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    envelope = MAGIC + struct.pack(">H", len(wrapped)) + nonce + wrapped + AESGCM(key).encrypt(
        nonce, apk, source_sha.encode("ascii")
    )
    manifest = {
        "schema_version": 1,
        "source_sha": source_sha,
        "apk_sha256": _sha256(apk),
        "encrypted_sha256": _sha256(envelope),
        "apk_bytes": len(apk),
    }
    return envelope, manifest


def decrypt(envelope: bytes, manifest: dict, expected_source_sha: str, private_key_pem: bytes) -> bytes:
    if not SHA_PATTERN.fullmatch(expected_source_sha) or manifest.get("source_sha") != expected_source_sha:
        raise ValueError("Source SHA does not match review request")
    if manifest.get("schema_version") != 1 or _sha256(envelope) != manifest.get("encrypted_sha256"):
        raise ValueError("Encrypted artifact integrity mismatch")
    if not envelope.startswith(MAGIC) or len(envelope) < len(MAGIC) + 2 + 12 + 16:
        raise ValueError("Invalid encrypted artifact envelope")
    offset = len(MAGIC)
    wrapped_size = struct.unpack(">H", envelope[offset:offset + 2])[0]
    offset += 2
    nonce = envelope[offset:offset + 12]
    offset += 12
    wrapped = envelope[offset:offset + wrapped_size]
    ciphertext = envelope[offset + wrapped_size:]
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("Invalid review decryption key")
    key = private_key.decrypt(
        wrapped,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    apk = AESGCM(key).decrypt(nonce, ciphertext, expected_source_sha.encode("ascii"))
    if not apk.startswith(b"PK") or len(apk) != manifest.get("apk_bytes") or _sha256(apk) != manifest.get("apk_sha256"):
        raise ValueError("Decrypted APK integrity mismatch")
    return apk


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("encrypt", "decrypt"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--private-key-env")
    args = parser.parse_args()
    if args.mode == "encrypt":
        if args.public_key is None:
            parser.error("--public-key is required for encryption")
        envelope, manifest = encrypt(args.input.read_bytes(), args.source_sha, args.public_key.read_bytes())
        args.output.write_bytes(envelope)
        args.manifest.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        print(f"APK_SOURCE_SHA={args.source_sha}")
        print(f"APK_SHA256={manifest['apk_sha256']}")
        print(f"ENCRYPTED_SHA256={manifest['encrypted_sha256']}")
    else:
        if not args.private_key_env or not os.environ.get(args.private_key_env):
            parser.error("Private decryption key environment variable is required")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        apk = decrypt(args.input.read_bytes(), manifest, args.source_sha, os.environ[args.private_key_env].encode())
        args.output.write_bytes(apk)
        print(f"PRIVATE_APK_SOURCE_SHA={args.source_sha}")
        print(f"PRIVATE_APK_SHA256={_sha256(apk)}")


if __name__ == "__main__":
    main()
