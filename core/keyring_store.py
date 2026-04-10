"""
core/keyring_store.py

Secure credential storage for QuillAI.
Uses the system keyring (KWallet / GNOME Keyring / libsecret)
as the primary store, with AES-256-GCM encryption as fallback.

Usage:
    from core.keyring_store import set_secret, get_secret, delete_secret

    set_secret("gitlab", "my_project_hash", "glpat-xxxx")
    token = get_secret("gitlab", "my_project_hash")
    delete_secret("gitlab", "my_project_hash")

Keyring service name format:  "quillai.<service>"
Keyring username format:      "<key>"

Fallback encrypted store:     ~/.config/quillai/secrets.enc
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

_APP     = "quillai"
_ENC_DIR = Path(os.path.expanduser("~")) / ".config" / "quillai"
_ENC_FILE = _ENC_DIR / "secrets.enc"

# ── Keyring backend ───────────────────────────────────────────────────────────

def _keyring_available() -> bool:
    try:
        import keyring
        kr = keyring.get_keyring()
        # ChainerBackend with no viable backends falls back to null
        return "null" not in type(kr).__name__.lower()
    except Exception:
        return False


def set_secret(service: str, key: str, value: str) -> bool:
    """
    Store a secret. Returns True on success.
    Tries system keyring first, falls back to encrypted file.
    """
    if not value:
        delete_secret(service, key)
        return True

    if _keyring_available():
        try:
            import keyring
            keyring.set_password(f"{_APP}.{service}", key, value)
            return True
        except Exception as e:
            print(f"[keyring] set failed, using fallback: {e}")

    return _enc_set(service, key, value)


def get_secret(service: str, key: str) -> Optional[str]:
    """
    Retrieve a secret. Returns None if not found.
    """
    if _keyring_available():
        try:
            import keyring
            val = keyring.get_password(f"{_APP}.{service}", key)
            if val is not None:
                return val
        except Exception as e:
            print(f"[keyring] get failed, using fallback: {e}")

    return _enc_get(service, key)


def delete_secret(service: str, key: str) -> bool:
    """Delete a secret from both stores."""
    deleted = False

    if _keyring_available():
        try:
            import keyring
            keyring.delete_password(f"{_APP}.{service}", key)
            deleted = True
        except Exception:
            pass

    if _enc_delete(service, key):
        deleted = True

    return deleted


# ── AES-256-GCM fallback ──────────────────────────────────────────────────────

def _machine_key() -> bytes:
    """
    Derive a 256-bit key from machine-specific data.
    Not perfect security but much better than plain text.
    """
    sources = [
        os.environ.get("USER", ""),
        os.environ.get("HOME", ""),
        str(os.getuid()) if hasattr(os, "getuid") else "",
    ]
    # Try to add machine-id for extra entropy
    for mid_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            sources.append(Path(mid_path).read_text().strip())
            break
        except Exception:
            pass

    seed = "|".join(sources).encode()
    return hashlib.sha256(seed).digest()


def _enc_load() -> dict:
    """Load encrypted secrets store."""
    if not _ENC_FILE.exists():
        return {}
    try:
        data = _ENC_FILE.read_bytes()
        return _aes_decrypt_store(data)
    except Exception as e:
        print(f"[keyring_store] failed to load encrypted store: {e}")
        return {}


def _enc_save(store: dict):
    """Save encrypted secrets store."""
    _ENC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = _aes_encrypt_store(store)
        _ENC_FILE.write_bytes(data)
        _ENC_FILE.chmod(0o600)
    except Exception as e:
        print(f"[keyring_store] failed to save encrypted store: {e}")


def _enc_set(service: str, key: str, value: str) -> bool:
    store = _enc_load()
    store[f"{service}/{key}"] = value
    _enc_save(store)
    return True


def _enc_get(service: str, key: str) -> Optional[str]:
    store = _enc_load()
    return store.get(f"{service}/{key}")


def _enc_delete(service: str, key: str) -> bool:
    store = _enc_load()
    k = f"{service}/{key}"
    if k in store:
        del store[k]
        _enc_save(store)
        return True
    return False


def _aes_encrypt_store(store: dict) -> bytes:
    """Encrypt store dict with AES-256-GCM."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key   = _machine_key()
        nonce = os.urandom(12)
        data  = json.dumps(store).encode()
        ct    = AESGCM(key).encrypt(nonce, data, None)
        # Format: 4-byte magic + 12-byte nonce + ciphertext
        return b"QSEC" + nonce + ct
    except ImportError:
        # cryptography not available — base64 obfuscation only
        # (better than plain text, not true encryption)
        data = json.dumps(store).encode()
        obf  = base64.b85encode(
            bytes(b ^ k for b, k in
                  zip(data, (_machine_key() * (len(data) // 32 + 1))[:len(data)]))
        )
        return b"QOBS" + obf


def _aes_decrypt_store(data: bytes) -> dict:
    """Decrypt store bytes."""
    if data[:4] == b"QSEC":
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            key   = _machine_key()
            nonce = data[4:16]
            ct    = data[16:]
            plain = AESGCM(key).decrypt(nonce, ct, None)
            return json.loads(plain)
        except Exception as e:
            print(f"[keyring_store] AES decrypt failed: {e}")
            return {}
    elif data[:4] == b"QOBS":
        try:
            key  = _machine_key()
            obf  = base64.b85decode(data[4:])
            plain = bytes(b ^ k for b, k in
                          zip(obf, (key * (len(obf) // 32 + 1))[:len(obf)]))
            return json.loads(plain)
        except Exception as e:
            print(f"[keyring_store] obf decrypt failed: {e}")
            return {}
    else:
        # Legacy plain JSON
        try:
            return json.loads(data)
        except Exception:
            return {}


# ── Convenience wrappers for QuillAI credential types ────────────────────────

def store_api_key(provider: str, value: str):
    """Store a global API key (openai, anthropic, etc.)"""
    set_secret("apikeys", provider, value)


def load_api_key(provider: str) -> str:
    return get_secret("apikeys", provider) or ""


def store_project_token(project_hash: str, service: str, value: str):
    """Store a per-project token (gitlab token, etc.)"""
    set_secret(f"project.{project_hash}", service, value)


def load_project_token(project_hash: str, service: str) -> str:
    return get_secret(f"project.{project_hash}", service) or ""