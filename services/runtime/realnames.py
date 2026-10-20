"""Guard against real-world football names (rule 3: fictional data only).

The deny-list holds only SHA-256 prefixes of the names (major leagues, governing bodies,
famous clubs and players), so the repo never spells them out. `real_names_in` hashes every
one-to-three-word phrase of a text and reports the phrases that match.
"""

from __future__ import annotations

import hashlib
import re

DENY_HASHES = frozenset({
    "01735c5ff1608734",
    "043ccc0426d6d4c8",
    "06ae4e35f69c4cf9",
    "11148d8f6ad4d4f2",
    "15c6d611193988e4",
    "183e79efd135ecf3",
    "1ecd41c03ef78bd6",
    "1fb7a48476f1ff64",
    "2bc0659381c5a5ea",
    "407d2025f7644cd0",
    "40cea1fd091bafe9",
    "42a36e2ff644aa23",
    "49151b985b3b68ed",
    "49ffa0597506d255",
    "51f8e35a14314fdc",
    "52b07f18c831ba4b",
    "599665a263e93b10",
    "5e15fddd30f7053b",
    "635450503029fc24",
    "7d005ccf181d00b7",
    "991b08408c2e4625",
    "9bcdae8ebc2a970a",
    "9e861941ad8bf5bc",
    "a5cca33940ed2a85",
    "a6c4937e7fe6ed54",
    "aab3fce96b5bdd7e",
    "b60bfc19ae1492c0",
    "cb9c298a2925bb01",
    "ccd7b7d60748e82b",
    "dffc504aa55359b9",
    "e0d628575cd460fe",
    "e24dd2210803b473",
    "e647708a52060743",
    "ebae5d4caac701c4",
    "ef90f09b368bbfa4",
    "efee614420c57ddd",
    "f3c3c8f5bc889e69",
    "f97557ce9b1cf089",
    "f99dc183918e3a55",
    "ff479f9d891005c5",
})  # fmt: skip

WORD = re.compile(r"[a-z0-9]+")


def _digest(phrase: str) -> str:
    return hashlib.sha256(phrase.encode()).hexdigest()[:16]


def real_names_in(text: str) -> list[str]:
    """Phrases in `text` that are on the deny-list (as they appear, lowercased)."""
    words = WORD.findall(text.lower().replace("é", "e"))
    hits = []
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i : i + n])
            if _digest(phrase) in DENY_HASHES:
                hits.append(phrase)
    return hits
