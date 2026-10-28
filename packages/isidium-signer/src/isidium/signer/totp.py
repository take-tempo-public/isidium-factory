"""RFC 6238 TOTP over the standard library: HMAC-SHA1, a 30-second step, 6 digits (the parameters Aegis uses).

No dependency: RFC 4226's dynamic truncation is a few lines over `hmac`, and `tests/signer/test_totp.py` reproduces
RFC 6238 Appendix B's SHA1 rows to prove it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
from typing import Final

from isidium.store.core.refusal import Refusal

# RFC 6238 / Aegis parameters, fixed by the protocol the phone speaks. They are not deployment limits (C-1 governs
# those, and they come from the settings file): changing one here would make every code the phone shows wrong.
STEP_S: Final = 30
DIGITS: Final = 6
# One step either side of the current one: a phone's clock and the service's differ by seconds, and a code shown
# at the end of one step is typed in the next. Wider would widen the time a stolen code stays usable.
WINDOW: Final = 1


def hotp(secret: bytes, counter: int) -> str:
    """RFC 4226: HMAC-SHA1 over the 8-byte counter, dynamic truncation, DIGITS digits."""
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def step_of(epoch: int) -> int:
    return epoch // STEP_S


def code_at(secret: bytes, epoch: int) -> str:
    return hotp(secret, step_of(epoch))


def matching_step(secret: bytes, code: str, epoch: int) -> int | None:
    """The step in the window around `epoch` whose code is `code`, or None. Anything that is not exactly DIGITS
    ASCII digits is None at once; each candidate is compared in constant time."""
    if len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    now = step_of(epoch)
    found: int | None = None
    for step in range(now - WINDOW, now + WINDOW + 1):  # no early exit: the time taken does not say which step
        if hmac.compare_digest(hotp(secret, step), code):
            found = step
    return found


def secret_from_base32(text: str) -> bytes:
    """The secret as Aegis takes it on manual entry: base32, whitespace and case tolerated, padding optional.
    A refusal never carries the text."""
    squeezed = "".join(text.split()).upper().rstrip("=")
    squeezed += "=" * (-len(squeezed) % 8)
    try:
        secret = base64.b32decode(squeezed)
    except (binascii.Error, ValueError) as e:
        raise Refusal("signer.secret-format", "", "the TOTP secret is not base32") from e
    if not secret:
        raise Refusal("signer.secret-format", "", "the TOTP secret is empty")
    return secret
