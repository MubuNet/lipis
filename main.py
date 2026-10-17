"""Command-line entry point for LIPIS."""

import argparse
import locale
import os
import sys
from typing import Dict, Optional, Sequence, Tuple

from modules.os_info import collect_system_info, render_system_info


VERSION = "0.1.0-dev"

TEXT = {
    "en": {
        "description": "Read-only Linux system diagnostics.",
        "language_help": "Display language.",
        "version": "Version",
    },
    "de": {
        "description": "Nur lesende Linux-Systemdiagnose.",
        "language_help": "Sprache der Ausgabe.",
        "version": "Version",
    },
}

BANNER = r"""  _     ___ ____ ___ ____
 | |   |_ _|  _ \_ _/ ___|
 | |    | | | _) | |\___ \
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/"""


def resolve_language(
    requested: Optional[str], environ: Optional[Dict[str, str]] = None
) -> str:
    """Resolve the requested language or infer it from standard locale variables."""
    if requested is not None:
        return requested

    environment = os.environ if environ is None else environ
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = environment.get(variable, "").lower()
        language_code = value.split(".", 1)[0].split("@", 1)[0].split("_", 1)[0]
        if language_code in ("en", "de"):
            return language_code
        if value:
            return "en"

    system_locale = locale.getlocale()[0]
    if system_locale:
        language_code = system_locale.lower().split("_", 1)[0]
        if language_code == "de":
            return "de"
    return "en"


def build_parser(language: str) -> argparse.ArgumentParser:
    text = TEXT[language]
    parser = argparse.ArgumentParser(
        prog="lipis",
        description=text["description"],
    )
    parser.add_argument(
        "--language",
        choices=("en", "de"),
        help=text["language_help"],
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help=(
            "Show version information."
            if language == "en"
            else "Versionsinformationen anzeigen."
        ),
    )
    return parser


def parse_arguments(
    arguments: Optional[Sequence[str]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Tuple[argparse.Namespace, str]:
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--language", choices=("en", "de"))
    selected, _ = selector.parse_known_args(arguments)
    language = resolve_language(selected.language, environ)
    parser = build_parser(language)
    return parser.parse_args(arguments), language


def run_diagnostics(language: str) -> None:
    info = collect_system_info()
    print(BANNER)
    print("LIPIS - Linux PostInstall Script")
    print("{}: {}".format(TEXT[language]["version"], VERSION))
    print()
    print(render_system_info(info, language))


def main(
    arguments: Optional[Sequence[str]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> int:
    args, language = parse_arguments(arguments, environ)
    if args.version:
        print("LIPIS {} {}".format(TEXT[language]["version"], VERSION))
        return 0

    run_diagnostics(language)
    return 0


if __name__ == "__main__":
    sys.exit(main())