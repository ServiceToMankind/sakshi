"""The other charges in a case, in plain words, from the public charge codes (#267).

A case's main offence comes from ``pipeline/severity.py``. This adds the rest of what the
accused is charged with (kidnapping, criminal intimidation, house trespass and so on), so a
case can say clearly what happened without any detail about the victim.

The table is deliberately short and fixed: only well-known sections whose meaning is clear,
in both the old IPC numbering and the new BNS one. Two things are left out on purpose:
- charges under the SC/ST (Prevention of Atrocities) Act, because naming them would reveal
  the victim's caste;
- wording that names a gender ("insulting a woman's modesty" becomes "insulting words or
  gestures"), because for a child even the gender must not be published.
Sexual-offence sections aren't listed here; the severity label already names them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

__all__ = ["other_charges"]

# (code, section number) -> plain words. The order of this table is the order we list them in.
_PLAIN_CHARGES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("IPC", ("302",), "murder"),
    ("BNS", ("103",), "murder"),
    ("IPC", ("307",), "attempted murder"),
    ("BNS", ("109",), "attempted murder"),
    ("IPC", ("363", "364", "365"), "kidnapping"),
    ("BNS", ("137", "140"), "kidnapping"),
    ("IPC", ("366",), "abduction"),
    ("BNS", ("87",), "abduction"),
    ("IPC", ("368",), "hiding a kidnapped person"),
    ("IPC", ("370", "372", "373"), "trafficking"),
    ("BNS", ("143",), "trafficking"),
    ("IPC", ("366A",), "procuring a minor"),
    ("BNS", ("96",), "procuring a minor"),
    ("IPC", ("342",), "wrongful confinement"),
    ("BNS", ("127",), "wrongful confinement"),
    ("IPC", ("341",), "wrongful restraint"),
    ("BNS", ("126",), "wrongful restraint"),
    ("IPC", ("328",), "drugging"),
    ("BNS", ("123",), "drugging"),
    ("IPC", ("324", "326"), "causing hurt with a weapon"),
    ("BNS", ("118",), "causing hurt with a weapon"),
    ("IPC", ("325",), "causing grievous hurt"),
    ("BNS", ("117",), "causing grievous hurt"),
    ("IPC", ("323",), "causing hurt"),
    ("BNS", ("115",), "causing hurt"),
    ("IPC", ("448", "450", "451", "452"), "house trespass"),
    ("BNS", ("329", "331", "332", "333"), "house trespass"),
    ("IPC", ("506",), "criminal intimidation"),
    ("BNS", ("351",), "criminal intimidation"),
    ("IPC", ("354D",), "stalking"),
    ("BNS", ("78",), "stalking"),
    ("IPC", ("354C",), "voyeurism"),
    ("BNS", ("77",), "voyeurism"),
    ("IPC", ("354B",), "assault to disrobe"),
    ("BNS", ("76",), "assault to disrobe"),
    ("IPC", ("509",), "insulting words or gestures"),
    ("BNS", ("79",), "insulting words or gestures"),
    ("BNS", ("81",), "deceit about marriage"),
    ("IPC", ("384",), "extortion"),
    ("BNS", ("308",), "extortion"),
    ("IPC", ("419",), "impersonation"),
    ("BNS", ("319",), "impersonation"),
    ("IPC", ("420",), "cheating"),
    ("BNS", ("318",), "cheating"),
    ("IPC", ("201",), "destroying evidence"),
    ("BNS", ("238",), "destroying evidence"),
    ("IPC", ("120", "120B"), "criminal conspiracy"),
    ("BNS", ("61",), "criminal conspiracy"),
    ("IPC", ("511",), "attempting the offence"),
    ("BNS", ("62",), "attempting the offence"),
    ("POCSO", ("18",), "attempting the offence"),
    ("POCSO", ("13", "14", "15"), "child sexual abuse material"),
    ("IT", ("67B",), "child sexual abuse material"),
    ("IT", ("67", "67A"), "sharing sexual material online"),
    ("IT", ("66E",), "capturing private images"),
    ("POCSO", ("17",), "abetment"),
    ("POCSO", ("21",), "failing to report the offence"),
    ("BNS", ("296",), "obscene acts in public"),
)

_SECTION_RE = re.compile(r"^\s*(IPC|BNS|POCSO|IT)\s*(?:ACT\s*)?(\d+[A-Z]?)", re.IGNORECASE)


def other_charges(sections: Sequence[str]) -> list[str]:
    """Plain names for the non-sexual charges among ``sections``, each once, in table order."""
    present: set[tuple[str, str]] = set()
    for section in sections:
        match = _SECTION_RE.match(str(section))
        if match:
            present.add((match.group(1).upper(), match.group(2).upper()))
    names: list[str] = []
    for code, numbers, plain in _PLAIN_CHARGES:
        if any((code, number) in present for number in numbers) and plain not in names:
            names.append(plain)
    return names
