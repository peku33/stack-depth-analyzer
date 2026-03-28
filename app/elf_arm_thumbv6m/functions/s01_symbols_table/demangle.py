import re
from itertools import takewhile


def name_demangle(name: str) -> str:
    # demangle itanium style name
    demangled = _name_demangle(name)
    if demangled is None:
        return name

    return demangled


_PART_SUBSTITUTION_REGEX = re.compile(r"\$([A-Z]+)\$")
_PART_SUBSTITUTIONS = {
    "LT": "<",
    "GT": ">",
    "LP": "(",
    "RP": ")",
    "C": ",",
    "SP": " ",
    "u20": " ",
}


def _part_substitutions_callback(match: re.Match[str]) -> str:
    pattern = match.group(1)
    return _PART_SUBSTITUTIONS.get(pattern, pattern)


def _name_demangle(name: str) -> str | None:
    # try demangling itanium style name, return None if not possible
    if not name.startswith("_Z"):
        return None

    # strip _Z
    name = name[2:]
    if not name:
        return None

    parts = list[str]()

    # handle N-E region
    if name[0] == "N":
        name = name[1:]
        while name:
            if name[0] == "E":
                name = name[1:]
                break

            # extract length
            length_str = "".join(takewhile(lambda character: character.isdigit(), name))
            name = name[len(length_str) :]
            length = int(length_str)

            # extract name
            part = name[:length]
            name = name[length:]

            # apply language-specific substitutions
            part = re.sub(_PART_SUBSTITUTION_REGEX, _part_substitutions_callback, part)

            parts.append(part)

    # handle rest region
    if name:
        parts.append(name)

    demangled = "::".join(parts)

    return demangled
