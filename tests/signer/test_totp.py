"""RFC 6238's SHA1 rows and the window the check accepts: the current step, one either side, nothing else."""

from __future__ import annotations

import base64

import pytest

from isidium.signer import totp
from isidium.store.core.refusal import Refusal

SECRET = b"12345678901234567890"  # RFC 6238 Appendix B's SHA1 secret

# Appendix B's SHA1 rows (T, 8-digit TOTP), truncated to the six digits the service speaks.
VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


def test_rfc6238_vectors_and_window() -> None:
    for epoch, eight in VECTORS:
        assert totp.code_at(SECRET, epoch) == eight[-6:]

    epoch = 1234567890
    step = totp.step_of(epoch)
    code = totp.code_at(SECRET, epoch)
    for offset in (-1, 0, 1):  # a code for step s is accepted while the clock is in s-1, s and s+1
        assert totp.matching_step(SECRET, code, epoch + offset * totp.STEP_S) == step
    for offset in (-2, 2):
        assert totp.matching_step(SECRET, code, epoch + offset * totp.STEP_S) is None
    # the other direction: the clock's step is fixed and the code comes from a neighbouring step
    for offset, expected in ((-1, step - 1), (1, step + 1), (-2, None), (2, None)):
        other = totp.code_at(SECRET, epoch + offset * totp.STEP_S)
        assert totp.matching_step(SECRET, other, epoch) == expected

    for bad in (code[:5], code + "0", "12345a", "", "١٢٣٤٥٦"):  # short, long, non-digit, empty, non-ASCII digits
        assert totp.matching_step(SECRET, bad, epoch) is None

    b32 = base64.b32encode(SECRET).decode().rstrip("=")
    spaced = " ".join(b32.lower()[i : i + 4] for i in range(0, len(b32), 4))
    assert totp.secret_from_base32(spaced) == SECRET
    with pytest.raises(Refusal) as err:
        totp.secret_from_base32("not base32 !!")
    assert err.value.rule == "signer.secret-format"
    assert "base32 !!" not in err.value.detail
