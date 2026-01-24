#!/usr/bin/env -S uvx
# /// script
# requires-python = ">=3.13"
# dependencies = ["cryptography>=42"]
# ///
from __future__ import annotations

import argparse
import os
import sys

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit(
        "Missing dependency: cryptography. Install with: pip install cryptography"
    ) from exc


MAGIC = b"AES256GCM1"
SALT_LEN = 16
NONCE_LEN = 12
KDF_ITERATIONS = 200_000


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_file(in_path: str, out_path: str, password: str) -> None:
    with open(in_path, "rb") as f:
        data = f.read()

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    with open(out_path, "wb") as f:
        f.write(MAGIC + salt + nonce + ciphertext)


def decrypt_file(in_path: str, out_path: str, password: str) -> None:
    with open(in_path, "rb") as f:
        payload = f.read()

    header_len = len(MAGIC) + SALT_LEN + NONCE_LEN
    if len(payload) < header_len or not payload.startswith(MAGIC):
        raise ValueError("Invalid or unsupported encrypted file format.")

    offset = len(MAGIC)
    salt = payload[offset : offset + SALT_LEN]
    offset += SALT_LEN
    nonce = payload[offset : offset + NONCE_LEN]
    ciphertext = payload[offset + NONCE_LEN :]

    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError(
            "Decryption failed: wrong password or corrupted file."
        ) from exc

    with open(out_path, "wb") as f:
        f.write(plaintext)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Encrypt or decrypt files with AES-256-GCM."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--encrypt", action="store_true", help="Encrypt the file.")
    mode.add_argument("--decrypt", action="store_true", help="Decrypt the file.")
    parser.add_argument("filename", help="Base filename (without .encrypted).")
    parser.add_argument("password", help="Password for key derivation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.encrypt:
        in_path = args.filename
        out_path = f"{args.filename}.encrypted"
    else:
        in_path = f"{args.filename}.encrypted"
        out_path = args.filename

    if not os.path.isfile(in_path):
        print(f"Input file not found: {in_path}", file=sys.stderr)
        return 2
    if os.path.exists(out_path):
        print(f"Output file already exists: {out_path}", file=sys.stderr)
        return 2

    try:
        if args.encrypt:
            encrypt_file(in_path, out_path, args.password)
        else:
            decrypt_file(in_path, out_path, args.password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
