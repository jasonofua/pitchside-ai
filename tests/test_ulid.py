from __future__ import annotations

import pytest

from sim.ulid import UlidFactory, decode_timestamp, encode


def test_encode_bounds() -> None:
    assert encode(0, 0) == "0" * 26
    assert encode(2**48 - 1, 2**80 - 1) == "7" + "Z" * 25
    with pytest.raises(ValueError):
        encode(2**48, 0)


def test_timestamp_round_trip() -> None:
    assert decode_timestamp(encode(1_793_124_000_000, 12345)) == 1_793_124_000_000


def test_monotonic_within_and_across_milliseconds() -> None:
    factory = UlidFactory("match-a")
    ids = [factory.new(ts) for ts in (1000, 1000, 1000, 1001, 1001, 999, 2000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_deterministic_per_namespace() -> None:
    a = [UlidFactory("m1").new(t) for t in range(5)]
    b = [UlidFactory("m1").new(t) for t in range(5)]
    c = [UlidFactory("m2").new(t) for t in range(5)]
    assert a == b
    assert a != c
