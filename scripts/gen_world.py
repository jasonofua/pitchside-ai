"""Generate data/world.json and data/crests/*.svg for the fictional league.

Every club, player name and crest here is invented. Names are hand-written (not
randomly combined) so they can be reviewed for clashes with real people; only the
attribute ratings are drawn from a seeded RNG.

    uv run python scripts/gen_world.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from contracts import World
from sim.formation import FORMATIONS

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261020

# Mean rating per position: pace, passing, finishing, pressing, stamina.
PROFILES: dict[str, tuple[int, int, int, int, int]] = {
    "GK": (55, 60, 20, 30, 62),
    "CB": (65, 64, 35, 70, 72),
    "RB": (78, 68, 45, 72, 80),
    "LB": (78, 68, 45, 72, 80),
    "RWB": (80, 68, 48, 70, 82),
    "LWB": (80, 68, 48, 70, 82),
    "DM": (64, 74, 50, 76, 80),
    "CM": (68, 77, 60, 72, 80),
    "AM": (72, 79, 70, 64, 72),
    "RM": (82, 71, 66, 66, 76),
    "LM": (82, 71, 66, 66, 76),
    "RW": (84, 71, 68, 64, 74),
    "LW": (84, 71, 68, 64, 74),
    "ST": (79, 64, 79, 62, 72),
}
ATTRS = ("pace", "passing", "finishing", "pressing", "stamina")

# (shirt, name, position). The first 11 are the starting XI in formation slot order.
CLUBS: list[dict[str, Any]] = [
    {
        "team_id": "LAG",
        "name": "Lagos Lions",
        "short_name": "Lions",
        "city": "Lagos",
        "colors": {"primary": "#F2B705", "secondary": "#14213D"},
        "crest": {"shape": "shield", "motif": "star"},
        "formation": "4-3-3",
        "quality": 74,
        "style": {},
        "stars": {9: {"finishing": 88, "pace": 90}},
        "squad": [
            (1, "Babajide Oyerinde", "GK"),
            (2, "Tobi Akinwale", "RB"),
            (5, "Chukwuemeka Nwadike", "CB"),
            (4, "Segun Adewuyi", "CB"),
            (3, "Kelechi Amadike", "LB"),
            (6, "Musa Danladi", "DM"),
            (8, "Femi Olorunfemi", "CM"),
            (10, "Ayodele Bankole", "CM"),
            (7, "Ikenna Obiora", "RW"),
            (9, "Dapo Okunade", "ST"),
            (11, "Chidi Ezeugo", "LW"),
            (16, "Uchenna Agbaje", "GK"),
            (15, "Ibrahim Kolawole", "CB"),
            (12, "Sola Fagbemi", "RB"),
            (14, "Yakubu Bitrus", "DM"),
            (18, "Damilare Ojediran", "AM"),
            (17, "Obinna Ukaegbu", "RW"),
            (19, "Kunle Arogundade", "ST"),
        ],
    },
    {
        "team_id": "HCF",
        "name": "Harbour City FC",
        "short_name": "Harbour",
        "city": "Harbour City",
        "colors": {"primary": "#0E7C86", "secondary": "#F4F1DE"},
        "crest": {"shape": "circle", "motif": "wave"},
        "formation": "4-2-3-1",
        "quality": 75,
        "style": {},
        "stars": {10: {"passing": 89}},
        "squad": [
            (1, "Mateus Arruda", "GK"),
            (2, "Kofi Adomako", "RB"),
            (4, "Lucien Marchetti", "CB"),
            (5, "Ebo Mensah-Arthur", "CB"),
            (3, "Rafael Duarte-Lima", "LB"),
            (6, "Yaw Sarpong-Kyei", "DM"),
            (8, "Davi Vasconcelos", "DM"),
            (7, "Jamal Kingsley-Ward", "RW"),
            (10, "Nuno Seabra", "AM"),
            (11, "Kojo Amissah", "LW"),
            (9, "Emmanuel Darko-Fynn", "ST"),
            (13, "Silas Okyere", "GK"),
            (15, "Bastien Leclair", "CB"),
            (23, "Marlon Pryce", "LB"),
            (18, "Fiifi Ankrah", "DM"),
            (20, "Tiago Moura", "AM"),
            (17, "Desmond Ashby", "LW"),
            (19, "Ruben Calado", "ST"),
        ],
    },
    {
        "team_id": "NBR",
        "name": "Northbank Rovers",
        "short_name": "Rovers",
        "city": "Northbank",
        "colors": {"primary": "#B3261E", "secondary": "#FFFFFF"},
        "crest": {"shape": "hexagon", "motif": "chevron"},
        "formation": "4-4-2",
        "quality": 71,
        # A high-pressing side that tires: the pressing_collapse scenario leans on this.
        "style": {"pressing": 8, "stamina": -5},
        "stars": {9: {"pace": 91}},
        "squad": [
            (1, "Callum Hartigan", "GK"),
            (2, "Owen Pritchard", "RB"),
            (5, "Declan Furlong", "CB"),
            (6, "Magnus Halvorsen", "CB"),
            (3, "Rhys Penhallow", "LB"),
            (7, "Jonah Whitcombe", "RM"),
            (8, "Finlay Gorrie", "CM"),
            (4, "Aksel Brennhaug", "CM"),
            (11, "Theo Ashdown", "LM"),
            (9, "Ciaran Mulvey", "ST"),
            (10, "Ludo Marsh", "ST"),
            (13, "Ellis Vane", "GK"),
            (15, "Gareth Lowther", "CB"),
            (12, "Niall Cushnahan", "RB"),
            (14, "Soren Lykke", "CM"),
            (16, "Harvey Elstob", "CM"),
            (17, "Bram Okoro-Hale", "RM"),
            (18, "Tomas Wedderburn", "ST"),
        ],
    },
    {
        "team_id": "KVA",
        "name": "Kestrel Vale Athletic",
        "short_name": "Kestrels",
        "city": "Kestrel Vale",
        "colors": {"primary": "#5B3FA0", "secondary": "#FFD23F"},
        "crest": {"shape": "diamond", "motif": "ring"},
        "formation": "3-5-2",
        "quality": 72,
        "style": {},
        "stars": {2: {"pace": 91}},
        "squad": [
            (1, "Iker Albeniz", "GK"),
            (4, "Gaspard Morel", "CB"),
            (5, "Alejandro Iturbe", "CB"),
            (6, "Samuel Ndongala", "CB"),
            (2, "Lucas Ferrandis", "RWB"),
            (8, "Mateo Larrain", "CM"),
            (16, "Hugo Valcarce", "DM"),
            (10, "Andres Quiroga", "CM"),
            (3, "Noe Balandier", "LWB"),
            (9, "Bruno Ascarate", "ST"),
            (11, "Yannick Sorel", "ST"),
            (13, "Pau Ribelles", "GK"),
            (15, "Elias Corbalan", "CB"),
            (12, "Malo Treguier", "LWB"),
            (14, "Diego Altuna", "CM"),
            (20, "Rayan Benhaddou", "AM"),
            (7, "Joaquin Esparza", "RM"),
            (19, "Leo Castellvi", "ST"),
        ],
    },
]


def build_world() -> dict[str, Any]:
    rng = random.Random(SEED)
    clubs = []
    for spec in CLUBS:
        slots = FORMATIONS[spec["formation"]]
        squad = spec["squad"]
        assert len(squad) == 18, spec["team_id"]
        for slot, (_, _, position) in zip(slots, squad[:11], strict=True):
            assert slot.role == position, (spec["team_id"], slot.name, position)

        players = []
        for shirt, name, position in squad:
            offset = spec["quality"] - 73
            ratings = {}
            for attr, mean in zip(ATTRS, PROFILES[position], strict=True):
                value = mean + offset + spec["style"].get(attr, 0) + rng.gauss(0, 5)
                ratings[attr] = int(max(30, min(97, round(value))))
            ratings.update(spec["stars"].get(shirt, {}))
            players.append(
                {
                    "player_id": f"{spec['team_id']}-{shirt:02d}",
                    "name": name,
                    "short_name": name.split(" ", 1)[1],
                    "shirt_number": shirt,
                    "position": position,
                    "attributes": ratings,
                }
            )
        clubs.append(
            {
                "team_id": spec["team_id"],
                "name": spec["name"],
                "short_name": spec["short_name"],
                "city": spec["city"],
                "colors": spec["colors"],
                "crest": spec["crest"],
                "formation": spec["formation"],
                "starting_xi": [p["player_id"] for p in players[:11]],
                "players": players,
            }
        )
    return {"version": 1, "clubs": clubs}


SHAPES = {
    "shield": "M10 8 H110 V70 C110 105 85 125 60 136 C35 125 10 105 10 70 Z",
    "circle": "M60 8 A64 64 0 1 1 59.9 8 Z",
    "hexagon": "M60 6 L114 37 V103 L60 134 L6 103 V37 Z",
    "diamond": "M60 4 L116 70 L60 136 L4 70 Z",
}
MOTIFS = {
    "stripe": '<rect x="48" y="0" width="24" height="140" fill="{c}"/>',
    "chevron": '<path d="M0 30 L60 65 L120 30 V52 L60 87 L0 52 Z" fill="{c}"/>',
    "star": (
        '<path d="M60 22 L69 48 L97 48 L75 64 L83 91 L60 75 L37 91 L45 64 L23 48 L51 48 Z"'
        ' fill="{c}"/>'
    ),
    "wave": '<path d="M0 78 Q30 58 60 78 T120 78 V100 Q90 80 60 100 T0 100 Z" fill="{c}"/>',
    "ring": '<circle cx="60" cy="56" r="26" fill="none" stroke="{c}" stroke-width="9"/>',
}

LABEL_Y = {"shield": 118, "circle": 116, "hexagon": 112, "diamond": 106}


def crest_svg(club: dict[str, Any]) -> str:
    primary = club["colors"]["primary"]
    secondary = club["colors"]["secondary"]
    path = SHAPES[club["crest"]["shape"]]
    motif = MOTIFS[club["crest"]["motif"]].format(c=secondary)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 140" '
        f'role="img" aria-label="{club["name"]} crest">\n'
        f'  <clipPath id="c"><path d="{path}"/></clipPath>\n'
        f'  <path d="{path}" fill="{primary}" stroke="{secondary}" stroke-width="4"/>\n'
        f'  <g clip-path="url(#c)" opacity="0.9">{motif}</g>\n'
        f'  <text x="60" y="{LABEL_Y[club["crest"]["shape"]]}" '
        'text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="16" '
        f'font-weight="700" fill="{secondary}">{club["team_id"]}</text>\n'
        "</svg>\n"
    )


def main() -> None:
    world = build_world()
    World.model_validate(world)
    (ROOT / "data" / "world.json").write_text(json.dumps(world, indent=2) + "\n")
    crests = ROOT / "data" / "crests"
    crests.mkdir(parents=True, exist_ok=True)
    for club in world["clubs"]:
        (crests / f"{club['team_id']}.svg").write_text(crest_svg(club))
    print(f"wrote {len(world['clubs'])} clubs to data/world.json and data/crests/")


if __name__ == "__main__":
    main()
