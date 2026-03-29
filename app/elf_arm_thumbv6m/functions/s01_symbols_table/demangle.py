import re
from itertools import takewhile
from typing import ClassVar


def name_demangle(name: str) -> str:
    demangled = _name_demangle(name)
    if demangled is None:
        return name

    return demangled


def _name_demangle(name: str) -> str | None:
    if name.startswith("_Z"):
        return _ia64_name_demangle(name)
    if name.startswith("_R"):
        return _rust_v0_name_demangle(name)
    return None


def _ia64_name_demangle(name: str) -> str | None:
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
            part = re.sub(_IA64_PART_SUBSTITUTION_REGEX, _ia64_part_substitutions_callback, part)

            parts.append(part)

    # handle rest region
    if name:
        parts.append(name)

    demangled = "::".join(parts)

    return demangled


_IA64_PART_SUBSTITUTION_REGEX = re.compile(r"\$([A-Z]+)\$")
_IA64_PART_SUBSTITUTIONS = {
    "LT": "<",
    "GT": ">",
    "LP": "(",
    "RP": ")",
    "C": ",",
    "SP": " ",
    "u20": " ",
}


def _ia64_part_substitutions_callback(match: re.Match[str]) -> str:
    pattern = match.group(1)
    return _IA64_PART_SUBSTITUTIONS.get(pattern, pattern)


def _rust_v0_name_demangle(name: str) -> str | None:
    if not name.startswith("_R"):
        return None

    return _RustV0Demangler(name).parse_symbol_name()


class _RustV0Demangler:
    _BACKREF_OFFSET: ClassVar[int] = 2  # backrefs are offsets from just after `_R`

    _symbol: str
    _position: int

    def __init__(self, symbol: str) -> None:
        super().__init__()

        self._symbol = symbol
        self._position = 0

    # reading helpers
    def _peek(self) -> str | None:
        if self._position < len(self._symbol):
            return self._symbol[self._position]
        else:
            return None

    def _next(self) -> str:
        char_ = self._symbol[self._position]
        self._position += 1
        return char_

    def _eat(self, expected: str) -> bool:
        if self._position + len(expected) > len(self._symbol):
            return False

        if self._symbol[self._position : self._position + len(expected)] != expected:
            return False

        self._position += len(expected)
        return True

    # parsers as in https://doc.rust-lang.org/rustc/symbol-mangling/v0.html
    def parse_symbol_name(self) -> str | None:
        # strip _R prefix
        if not self._eat("_R"):
            return None

        # optional encoding version number - unknown version, bail out
        if (encoding_version := self._peek()) is not None and encoding_version.isdigit():
            return None

        # parse the path (main content)
        name = self._parse_path()

        # skip optional instantiating-crate and vendor-specific-suffix
        # (we just ignore whatever remains)

        return name

    def _parse_path(self) -> str:
        tag = self._next()
        match tag:
            case "C":
                return self._parse_crate_root()
            case "M":
                return self._parse_inherent_impl()
            case "X":
                return self._parse_trait_impl()
            case "Y":
                return self._parse_trait_definition()
            case "N":
                return self._parse_nested_path()
            case "I":
                return self._parse_generic_args()
            case "B":
                # offset from _R
                offset = self._parse_base62_number()

                # the hacky part
                saved = self._position
                self._position = offset + self._BACKREF_OFFSET
                result = self._parse_path()
                self._position = saved

                return result
            case _:
                raise ValueError(f"unexpected path tag: {tag}")

    def _parse_crate_root(self) -> str:
        _disambiguator, name = self._parse_identifier()
        # we skip displaying disambiguator, as its meaningless for crate root

        return name

    def _parse_inherent_impl(self) -> str:
        self._parse_impl_path()  # "The impl-path usually need not be displayed."
        type_ = self._parse_type()

        return f"<{type_}>"

    def _parse_trait_impl(self) -> str:
        self._parse_impl_path()  # "The impl-path usually need not be displayed."
        type_ = self._parse_type()
        path = self._parse_path()

        return f"<{type_} as {path}>"

    def _parse_impl_path(self) -> tuple[int, str]:
        disambiguator = self._parse_disambiguator_opt()
        path = self._parse_path()

        return disambiguator, path

    def _parse_trait_definition(self) -> str:
        type_ = self._parse_type()
        path = self._parse_path()

        return f"<{type_} as {path}>"

    def _parse_nested_path(self) -> str:
        namespace = self._next()  # namespace tag
        path = self._parse_path()
        disambiguator, name = self._parse_identifier()

        match namespace:
            case "C":
                namespace_ = "closure"
            case "S":
                namespace_ = "shim"
            case _ if namespace.isupper():
                namespace_ = namespace
            case _:
                namespace_ = ""

        if namespace_:
            nested_path = namespace_
            if name:
                nested_path += f":{name}"
            if disambiguator:
                nested_path += f"#{disambiguator}"
            nested_path = f"{path}::{{{nested_path}}}"
        else:
            nested_path = path
            if name:
                nested_path += f"::{name}"

        return nested_path

    def _parse_generic_args(self) -> str:
        path = self._parse_path()

        generic_args = list[str]()
        while not self._eat("E"):
            generic_args.append(self._parse_generic_arg())

        generic_args_ = path
        if generic_args:
            generic_args_ += f"::<{', '.join(generic_args)}>"

        return generic_args_

    def _parse_generic_arg(self) -> str:
        match self._next():
            case "L":
                lifetime = self._parse_lifetime()

                return f"'_{lifetime if lifetime else ""}"
            case "K":
                return self._parse_const()
            case _:
                self._position -= 1
                return self._parse_type()

    def _parse_identifier(self) -> tuple[int, str]:
        disambiguator = self._parse_disambiguator_opt()
        name = self._parse_undisambiguated_identifier()

        return disambiguator, name

    def _parse_undisambiguated_identifier(self) -> str:
        # u_opt (is_punycode)
        self._eat("u")

        # decimal-number
        length = self._parse_decimal_number()

        # _opt
        self._eat("_")

        # bytes
        name = self._symbol[self._position : self._position + length]
        self._position += length

        return name

    def _parse_disambiguator(self) -> int:
        return self._parse_base62_number() + 1

    def _parse_disambiguator_opt(self) -> int:
        if self._eat("s"):
            return self._parse_disambiguator()
        else:
            return 0

    def _parse_lifetime(self) -> int:
        return self._parse_base62_number()

    def _parse_lifetime_opt(self) -> int | None:
        if self._eat("L"):
            return self._parse_lifetime()
        else:
            return None

    def _parse_const(self) -> str:
        match self._next():
            case "p":  # placeholder
                return "_"
            case "B":  # backref
                # offset from _R
                offset = self._parse_base62_number()

                # a bit hacky part
                saved = self._position
                self._position = offset + self._BACKREF_OFFSET
                result = self._parse_const()
                self._position = saved

                return result
            case _:  # type const-data
                self._position -= 1

                type_ = self._parse_type()
                negative = self._eat("n")

                # parse hex digits until _
                hex_str = ""
                while not self._eat("_"):
                    hex_str += self._next()
                value = int(hex_str, 16) if hex_str else 0

                # final value
                if negative:
                    value = -value

                # value representation
                match type_:
                    case "bool":
                        repr_ = "true" if value else "false"
                    case "char":
                        try:
                            repr_ = repr(chr(value))
                        except (ValueError, OverflowError):
                            repr_ = str(value)
                    case _:
                        repr_ = str(value)

                return repr_

    def _parse_type(self) -> str:
        tag = self._next()
        match tag:
            case "a":
                return "i8"
            case "b":
                return "bool"
            case "c":
                return "char"
            case "d":
                return "f64"
            case "e":
                return "str"
            case "f":
                return "f32"
            case "h":
                return "u8"
            case "i":
                return "isize"
            case "j":
                return "usize"
            case "l":
                return "i32"
            case "m":
                return "u32"
            case "n":
                return "i128"
            case "o":
                return "u128"
            case "s":
                return "i16"
            case "t":
                return "u16"
            case "u":
                return "()"
            case "v":
                return "..."
            case "x":
                return "i64"
            case "y":
                return "u64"
            case "z":
                return "!"
            case "p":
                return "_"
            case "A":  # array
                type_ = self._parse_type()
                size = self._parse_const()

                return f"[{type_}; {size}]"
            case "S":  # slice
                type_ = self._parse_type()

                return f"[{type_}]"
            case "T":  # tuple
                types = list[str]()

                while not self._eat("E"):
                    types.append(self._parse_type())

                return f"({', '.join(types)})"
            case "R":  # ref type
                lifetime = self._parse_lifetime_opt()
                type_ = self._parse_type()

                return f"&{f"'_{lifetime} " if lifetime else ""}{type_}"
            case "Q":  # mut ref type
                lifetime = self._parse_lifetime_opt()
                type_ = self._parse_type()

                return f"&{f"'_{lifetime} " if lifetime else ""}mut {type_}"
            case "P":  # const ptr
                type_ = self._parse_type()

                return f"*const {type_}"
            case "O":  # mut ptr
                type_ = self._parse_type()

                return f"*mut {type_}"
            case "F":  # fn type
                return self._parse_fn_sig()
            case "W":  # pattern type
                return self._parse_pattern_kind()
            case "D":  # dyn trait type
                return self._parse_dyn_trait_type()
            case "B":  # backref
                # offset from _R
                offset = self._parse_base62_number()

                # the hacky part
                saved = self._position
                self._position = offset + self._BACKREF_OFFSET
                result = self._parse_type()
                self._position = saved

                return result
            case _:  # named type (path) — unconsume the tag
                self._position -= 1
                return self._parse_path()

    def _parse_fn_sig(self) -> str:
        binder = self._parse_binder_opt()
        is_unsafe = self._eat("U")

        abi: str | None = None
        if self._eat("K"):
            if self._eat("C"):
                abi = "C"
            else:
                abi = self._parse_undisambiguated_identifier().replace("_", "-")

        params = list[str]()
        while not self._eat("E"):
            params.append(self._parse_type())

        return_type = self._parse_type()

        fn_sig = ""
        if binder:
            fn_sig += f"for<{', '.join(f"'_{i + 1}" for i in range(binder))}> "
        if is_unsafe:
            fn_sig += "unsafe "
        if abi:
            fn_sig += f'extern "{abi}" '
        fn_sig += f"fn({', '.join(params)})"
        if return_type != "()":
            fn_sig += f" -> {return_type}"

        return fn_sig

    def _parse_pattern_kind(self) -> str:
        tag = self._next()
        match tag:
            case "R":  # range
                start = self._parse_const()
                end = self._parse_const()

                return f"{start}..={end}"
            case "O":  # or
                patterns = list[str]()
                while not self._eat("E"):
                    patterns.append(self._parse_pattern_kind())

                return " | ".join(patterns)
            case _:
                raise ValueError(f"unexpected pattern kind tag: {tag}")

    def _parse_dyn_trait_type(self) -> str:
        binder = self._parse_binder_opt()

        traits = list[str]()
        while not self._eat("E"):
            trait_path = self._parse_path()

            assoc_bindings = list[str]()
            while self._eat("p"):
                name = self._parse_undisambiguated_identifier()
                type_ = self._parse_type()
                assoc_bindings.append(f"{name} = {type_}")

            if assoc_bindings:
                trait_path += f"<{', '.join(assoc_bindings)}>"
            traits.append(trait_path)

        lifetime = self._parse_lifetime_opt()

        dyn_trait_type = "dyn "
        if binder:
            dyn_trait_type += f"for<{', '.join(f"'_{i + 1}" for i in range(binder))}> "
        dyn_trait_type += " + ".join(traits)
        if lifetime:
            dyn_trait_type += f" + '_{lifetime}"

        return dyn_trait_type

    def _parse_binder(self) -> int:
        return self._parse_base62_number() + 1

    def _parse_binder_opt(self) -> int:
        if self._eat("G"):
            return self._parse_binder()
        else:
            return 0

    def _parse_base62_number(self) -> int:
        if self._eat("_"):
            return 0

        BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        number = 0
        while (char_ := self._next()) != "_":
            number = number * 62 + BASE62_CHARS.index(char_)
        return number + 1

    def _parse_decimal_number(self) -> int:
        position_start = self._position
        while self._position < len(self._symbol) and self._symbol[self._position].isdigit():
            self._position += 1
        return int(self._symbol[position_start : self._position])
