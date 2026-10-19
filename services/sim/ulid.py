"""Deterministic, monotonic ULIDs.

A ULID is a 48-bit millisecond timestamp followed by 80 random bits, encoded as 26
Crockford base32 characters. Here the timestamp comes from the match timeline and
the random bits from a seeded RNG, so a replayed match gets identical ids. Within
one millisecond the random part is incremented, which keeps ids strictly sortable.
"""

from __future__ import annotations

import hashlib
import random

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MAX_RANDOM = (1 << 80) - 1


def encode(timestamp_ms: int, randomness: int) -> str:
    if not 0 <= timestamp_ms < (1 << 48):
        raise ValueError("timestamp out of range")
    if not 0 <= randomness <= _MAX_RANDOM:
        raise ValueError("randomness out of range")
    value = (timestamp_ms << 80) | randomness
    chars = []
    for _ in range(26):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def decode_timestamp(ulid: str) -> int:
    value = 0
    for char in ulid:
        value = (value << 5) | ALPHABET.index(char)
    return value >> 80


class UlidFactory:
    def __init__(self, namespace: str) -> None:
        digest = hashlib.sha256(namespace.encode()).digest()
        self._rng = random.Random(int.from_bytes(digest[:8], "big"))
        self._last_ts = -1
        self._last_rand = 0

    def new(self, timestamp_ms: int) -> str:
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts
            if self._last_rand == _MAX_RANDOM:
                timestamp_ms += 1
                self._last_rand = self._rng.getrandbits(79)
            else:
                self._last_rand += 1
        else:
            # 79 bits leaves headroom to increment within a millisecond.
            self._last_rand = self._rng.getrandbits(79)
        self._last_ts = timestamp_ms
        return encode(timestamp_ms, self._last_rand)
