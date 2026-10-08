"""Professional text encoding, decoding, hashing and encryption plugin for CythonX.

Commands
--------
.enc <method> [--key KEY] <text>
.dec <method> [--key KEY] <encoded/encrypted text>
.hash <algorithm> [--key KEY] <text>
.cipherhelp

Reply mode is supported: reply to a text message and omit the text argument.

This plugin deliberately distinguishes encoding, hashing and encryption:
- Encoding is reversible without a secret.
- Hashing is one-way and therefore has no decode operation.
- Encryption is reversible with the correct key/password.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import json
import re
import secrets
import shlex
import urllib.parse
from typing import Callable, Optional

from . import heartless_cmd

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
except ImportError:  # pragma: no cover - depends on deployment environment
    Fernet = None
    InvalidToken = Exception
    hashes = None
    AESGCM = None
    ChaCha20Poly1305 = None
    PBKDF2HMAC = None
    Scrypt = None


PLUGIN_VERSION = "2.0.0"
PREFIX = "CIPHER"
SALT_SIZE = 16
NONCE_SIZE = 12
PBKDF2_ITERATIONS = 390_000
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class CipherError(ValueError):
    """Expected user-facing conversion/encryption error."""


def _b64e(data: bytes, urlsafe: bool = False) -> str:
    fn = base64.urlsafe_b64encode if urlsafe else base64.b64encode
    return fn(data).decode("ascii")


def _b64d(value: str, urlsafe: bool = False) -> bytes:
    try:
        raw = value.strip().encode("ascii")
        raw += b"=" * (-len(raw) % 4)
        if urlsafe:
            return base64.urlsafe_b64decode(raw)
        return base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError) as exc:
        raise CipherError("Invalid Base64 data.") from exc


def _require_crypto() -> None:
    if AESGCM is None or Fernet is None:
        raise CipherError(
            "Modern encryption requires the 'cryptography' package. "
            "Install it with: pip install -U cryptography"
        )


def _password_bytes(key: str) -> bytes:
    if not key:
        raise CipherError("A non-empty key/password is required.")
    return key.encode("utf-8")


def _pbkdf2(password: str, salt: bytes, length: int = 32) -> bytes:
    _require_crypto()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(_password_bytes(password))


def _scrypt(password: str, salt: bytes, length: int = 32) -> bytes:
    _require_crypto()
    kdf = Scrypt(salt=salt, length=length, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(_password_bytes(password))


def _fernet_key(password: str, salt: bytes) -> bytes:
    return base64.urlsafe_b64encode(_pbkdf2(password, salt, 32))


def _pack(version: str, salt: bytes, nonce: bytes, ciphertext: bytes) -> str:
    return f"{PREFIX}${version}${_b64e(salt)}${_b64e(nonce)}${_b64e(ciphertext)}"


def _unpack(value: str, expected_version: str) -> tuple[bytes, bytes, bytes]:
    parts = value.strip().split("$")
    if len(parts) != 5 or parts[0] != PREFIX or parts[1] != expected_version:
        raise CipherError(f"Invalid {expected_version} ciphertext format.")
    try:
        salt = _b64d(parts[2])
        nonce = _b64d(parts[3])
        ciphertext = _b64d(parts[4])
    except CipherError:
        raise
    if len(salt) != SALT_SIZE or len(nonce) != NONCE_SIZE or not ciphertext:
        raise CipherError("Invalid ciphertext components.")
    return salt, nonce, ciphertext


def aesgcm_encrypt(text: str, password: str) -> str:
    _require_crypto()
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = _scrypt(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, text.encode("utf-8"), None)
    return _pack("AESGCM1", salt, nonce, ciphertext)


def aesgcm_decrypt(value: str, password: str) -> str:
    _require_crypto()
    salt, nonce, ciphertext = _unpack(value, "AESGCM1")
    try:
        plain = AESGCM(_scrypt(password, salt)).decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8")
    except Exception as exc:
        raise CipherError("Decryption failed: wrong password or corrupted data.") from exc


def chacha_encrypt(text: str, password: str) -> str:
    _require_crypto()
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = _scrypt(password, salt)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, text.encode("utf-8"), None)
    return _pack("CHACHA1", salt, nonce, ciphertext)


def chacha_decrypt(value: str, password: str) -> str:
    _require_crypto()
    salt, nonce, ciphertext = _unpack(value, "CHACHA1")
    try:
        plain = ChaCha20Poly1305(_scrypt(password, salt)).decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8")
    except Exception as exc:
        raise CipherError("Decryption failed: wrong password or corrupted data.") from exc


def fernet_encrypt(text: str, password: str) -> str:
    _require_crypto()
    salt = secrets.token_bytes(SALT_SIZE)
    token = Fernet(_fernet_key(password, salt)).encrypt(text.encode("utf-8"))
    return f"{PREFIX}$FERNET1${_b64e(salt)}${token.decode('ascii')}"


def fernet_decrypt(value: str, password: str) -> str:
    _require_crypto()
    parts = value.strip().split("$")
    if len(parts) != 4 or parts[0] != PREFIX or parts[1] != "FERNET1":
        raise CipherError("Invalid FERNET ciphertext format.")
    try:
        salt = _b64d(parts[2])
        token = parts[3].encode("ascii")
        plain = Fernet(_fernet_key(password, salt)).decrypt(token)
        return plain.decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError, CipherError) as exc:
        raise CipherError("Decryption failed: wrong password or corrupted data.") from exc


def _caesar(text: str, shift: int) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + shift) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + shift) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def _vigenere(text: str, key: str, decrypt: bool = False) -> str:
    key = "".join(c for c in key.upper() if c.isalpha() and c.isascii())
    if not key:
        raise CipherError("Vigenere key must contain ASCII letters.")
    out, i = [], 0
    for ch in text:
        if ch.isascii() and ch.isalpha():
            base = 65 if ch.isupper() else 97
            shift = ord(key[i % len(key)]) - 65
            if decrypt:
                shift = -shift
            out.append(chr((ord(ch) - base + shift) % 26 + base))
            i += 1
        else:
            out.append(ch)
    return "".join(out)


def _xor(data: bytes, key: bytes) -> bytes:
    if not key:
        raise CipherError("XOR key cannot be empty.")
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))



async def _get_input(event, args: str) -> str:
    if args.strip():
        return args.strip()
    reply = await event.get_reply_message()
    if reply and reply.raw_text:
        return reply.raw_text
    raise CipherError("Provide text or reply to a text message.")


def _parse_args(raw: str) -> tuple[str, Optional[str], str]:
    try:
        tokens = shlex.split(raw.strip())
    except ValueError as exc:
        raise CipherError(f"Invalid command quoting: {exc}") from exc
    if not tokens:
        raise CipherError("Missing method. Use .cipherhelp for usage.")
    method = tokens.pop(0).lower()
    key = None
    text_parts = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("--key", "-k"):
            if i + 1 >= len(tokens):
                raise CipherError("--key requires a value.")
            key = tokens[i + 1]
            i += 2
            continue
        if token.startswith("--key="):
            key = token[6:]
            i += 1
            continue
        text_parts.append(token)
        i += 1
    return method, key, " ".join(text_parts)


ENCODERS: dict[str, Callable[[str], str]] = {
    "base64": lambda s: _b64e(s.encode("utf-8")),
    "b64": lambda s: _b64e(s.encode("utf-8")),
    "base64url": lambda s: _b64e(s.encode("utf-8"), True),
    "b64url": lambda s: _b64e(s.encode("utf-8"), True),
    "base32": lambda s: base64.b32encode(s.encode("utf-8")).decode("ascii"),
    "base16": lambda s: base64.b16encode(s.encode("utf-8")).decode("ascii"),
    "hex": lambda s: s.encode("utf-8").hex(),
    "url": lambda s: urllib.parse.quote(s, safe=""),
    "urlquery": lambda s: urllib.parse.quote_plus(s),
    "html": html.escape,
    "unicode": lambda s: s.encode("unicode_escape").decode("ascii"),
    "json": lambda s: json.dumps(s, ensure_ascii=False),
    "binary": lambda s: " ".join(f"{b:08b}" for b in s.encode("utf-8")),
    "rot13": lambda s: __import__("codecs").decode(s, "rot_13"),
    "atbash": lambda s: _caesar(s, 0).translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvutsrqponmlkjihgfedcba",
    )),
}


def _decode_base16(s: str) -> str:
    try:
        return base64.b16decode(s.strip(), casefold=True).decode("utf-8")
    except Exception as exc:
        raise CipherError("Invalid Base16 data or non-UTF-8 content.") from exc


def _decode_hex(s: str) -> str:
    try:
        return bytes.fromhex(s.strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise CipherError("Invalid hexadecimal data or non-UTF-8 content.") from exc


def _decode_binary(s: str) -> str:
    try:
        bits = re.sub(r"\s+", "", s)
        if not bits:
            return ""
        if len(bits) % 8 or re.fullmatch(r"[01]+", bits) is None:
            raise ValueError
        return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise CipherError("Invalid binary UTF-8 data.") from exc


def _decode_json(s: str) -> str:
    try:
        value = json.loads(s)
        if not isinstance(value, str):
            raise CipherError("JSON value is valid but is not a string.")
        return value
    except json.JSONDecodeError as exc:
        raise CipherError("Invalid JSON string.") from exc


DECODERS: dict[str, Callable[[str], str]] = {
    "base64": lambda s: _b64d(s).decode("utf-8"),
    "b64": lambda s: _b64d(s).decode("utf-8"),
    "base64url": lambda s: _b64d(s, True).decode("utf-8"),
    "b64url": lambda s: _b64d(s, True).decode("utf-8"),
    "base32": lambda s: base64.b32decode(s.strip().upper() + "=" * (-len(s.strip()) % 8)).decode("utf-8"),
    "base16": _decode_base16,
    "hex": _decode_hex,
    "url": urllib.parse.unquote,
    "urlquery": urllib.parse.unquote_plus,
    "html": html.unescape,
    "unicode": lambda s: s.encode("ascii").decode("unicode_escape"),
    "json": _decode_json,
    "binary": _decode_binary,
    "rot13": lambda s: __import__("codecs").decode(s, "rot_13"),
    "atbash": ENCODERS["atbash"],
}


HASH_ALIASES = {
    "md5": "md5", "sha1": "sha1", "sha224": "sha224", "sha256": "sha256",
    "sha384": "sha384", "sha512": "sha512", "sha3-224": "sha3_224",
    "sha3-256": "sha3_256", "sha3-384": "sha3_384", "sha3-512": "sha3_512",
    "blake2b": "blake2b", "blake2s": "blake2s",
}


def _hash_text(algorithm: str, text: str, key: Optional[str]) -> str:
    name = HASH_ALIASES.get(algorithm.lower())
    if not name:
        raise CipherError("Unsupported hash. Use .cipherhelp for the supported algorithms.")
    data = text.encode("utf-8")
    if key is not None:
        digest = hmac.new(key.encode("utf-8"), data, getattr(hashlib, name)).hexdigest()
        return digest
    return hashlib.new(name, data).hexdigest()


def _help() -> str:
    return f"""**Heartless {PLUGIN_VERSION} — Encoding / Hashing / Encryption**

**Encoding / decoding**
` .enc base64 text `
` .dec base64 encoded `

Methods: `base64`, `base64url`, `base32`, `base16`, `hex`, `binary`, `url`, `urlquery`, `html`, `unicode`, `json`, `rot13`, `atbash`

**Classical ciphers**
`.enc caesar --key 13 text`
`.dec caesar --key 13 text`
`.enc vigenere --key KEY text`
`.dec vigenere --key KEY text`
`.enc xor --key KEY text`
`.dec xor --key KEY encoded`

**Modern authenticated encryption**
`.enc aesgcm --key "password" text`
`.dec aesgcm --key "password" ciphertext`
`.enc chacha20 --key "password" text`
`.dec chacha20 --key "password" ciphertext`
`.enc fernet --key "password" text`
`.dec fernet --key "password" ciphertext`

**Hashes (one-way; cannot be decoded)**
`.hash sha256 text`
`.hash sha3-512 text`
`.hash blake2b text`
`.hash hmac-sha256 --key "secret" text`

Reply to a text message and omit the text argument to process the replied message.
"""


def _safe_code_block(value: str) -> str:
    return value.replace("```", "` ` `")


async def _send_result(event, title: str, method: str, result: str) -> None:
    safe = _safe_code_block(result)
    if len(safe) <= 3500:
        await event.eor(f"🔐 **{title} — `{method}`**\n\n```\n{safe}\n```")
        return
    # Keep large output intact instead of truncating encoded/encrypted data.
    from io import BytesIO
    payload = result.encode("utf-8")
    stream = BytesIO(payload)
    stream.name = f"cipher_{method}.txt"
    await event.reply(
        f"🔐 **{title} — `{method}`**\n\nOutput is {len(payload):,} bytes and was sent as a document.",
        file=stream,
        force_document=True,
    )
    try:
        await event.delete()
    except Exception:
        pass


async def _run_transform(event, decode: bool) -> None:
    raw = event.pattern_match.group(1) or ""
    method, key, text = _parse_args(raw)
    text = await _get_input(event, text)

    if method in {"aesgcm", "aes", "chacha20", "chacha", "fernet"}:
        if key is None:
            raise CipherError("Modern encryption requires --key.")
        if method in {"aesgcm", "aes"}:
            result = aesgcm_decrypt(text, key) if decode else aesgcm_encrypt(text, key)
        elif method in {"chacha20", "chacha"}:
            result = chacha_decrypt(text, key) if decode else chacha_encrypt(text, key)
        else:
            result = fernet_decrypt(text, key) if decode else fernet_encrypt(text, key)
    elif method in {"caesar", "rot"}:
        if key is None:
            raise CipherError("Caesar requires --key with an integer shift.")
        try:
            shift = int(key)
        except ValueError as exc:
            raise CipherError("Caesar key must be an integer.") from exc
        result = _caesar(text, -shift if decode else shift)
    elif method == "vigenere":
        result = _vigenere(text, key or "", decrypt=decode)
    elif method == "xor":
        if key is None:
            raise CipherError("XOR requires --key.")
        if decode:
            raw_data = _b64d(text)
            result = _xor(raw_data, key.encode("utf-8")).decode("utf-8")
        else:
            result = _b64e(_xor(text.encode("utf-8"), key.encode("utf-8")))
    else:
        table = DECODERS if decode else ENCODERS
        fn = table.get(method)
        if fn is None:
            raise CipherError(f"Unknown method: `{method}`. Use .cipherhelp.")
        try:
            result = fn(text)
        except UnicodeDecodeError as exc:
            raise CipherError("Decoded bytes are not valid UTF-8 text.") from exc
        except Exception as exc:
            if isinstance(exc, CipherError):
                raise
            raise CipherError(f"Conversion failed: {exc}") from exc

    title = "Decoded" if decode else "Encoded"
    await _send_result(event, title, method, result)


@heartless_cmd(pattern=r"(?:enc|encode)(?:\s+(.*)|$)")
async def encode_command(event):
    try:
        await _run_transform(event, False)
    except CipherError as exc:
        await event.eor(f"❌ `{exc}`")


@heartless_cmd(pattern=r"(?:dec|decode)(?:\s+(.*)|$)")
async def decode_command(event):
    try:
        await _run_transform(event, True)
    except CipherError as exc:
        await event.eor(f"❌ `{exc}`")


@heartless_cmd(pattern=r"hash(?:\s+(.*)|$)")
async def hash_command(event):
    try:
        raw = event.pattern_match.group(1) or ""
        method, key, text = _parse_args(raw)
        if method.startswith("hmac-"):
            method = method[5:]
            if not key:
                raise CipherError("HMAC requires --key.")
        text = await _get_input(event, text)
        result = _hash_text(method, text, key)
        label = f"HMAC-{method}" if key else method
        await event.eor(f"#️⃣ **Hash — `{label}`**\n\n`{result}`")
    except CipherError as exc:
        await event.eor(f"❌ `{exc}`")


@heartless_cmd(pattern=r"cipherhelp$")
async def cipher_help(event):
    await event.eor(_help())
