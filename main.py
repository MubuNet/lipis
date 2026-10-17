"""Command-line entry point for LIPIS."""

import argparse
import locale
import os
import sys
from typing import Dict, Optional, Sequence, Tuple

from modules.hardware import collect_hardware_info, render_hardware_info
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


class LocalizedHelpFormatter(argparse.HelpFormatter):
    """Format command-line help with localized usage labels."""

    def __init__(self, *args, language: str, **kwargs):
        """Initialize the formatter for the selected language."""
        self.language = language
        super().__init__(*args, **kwargs)

    def _format_usage(self, usage, actions, groups, prefix):
        """Return the usage line with a translated prefix when needed."""
        result = super()._format_usage(usage, actions, groups, prefix)
        if self.language == "de":
            return result.replace("usage:", "Verwendung:", 1)
        return result


class LocalizedArgumentParser(argparse.ArgumentParser):
    """Parse CLI arguments and localize help and validation errors."""

    def __init__(self, language: str, **kwargs):
        """Initialize a parser configured for English or German."""
        self.language = language
        formatter_class = lambda **options: LocalizedHelpFormatter(
            language=language, **options
        )
        super().__init__(formatter_class=formatter_class, add_help=False, **kwargs)
        if language == "de":
            self._optionals.title = "Optionen"

    def error(self, message: str) -> None:
        """Print a localized argument error and exit with argparse's error code."""
        if self.language == "de":
            translations = (
                ("argument ", "Argument "),
                ("invalid choice:", "ungültige Auswahl:"),
                (" (choose from ", " (zulässige Werte: "),
                ("unrecognized arguments:", "unbekannte Argumente:"),
                ("expected one argument", "ein Argument wird erwartet"),
                (
                    "the following arguments are required:",
                    "folgende Argumente sind erforderlich:",
                ),
            )
            for source, translated in translations:
                message = message.replace(source, translated)
            self.print_usage(sys.stderr)
            self.exit(2, "{}: Fehler: {}\n".format(self.prog, message))
        super().error(message)


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
    """Build the command-line parser for the selected display language."""
    text = TEXT[language]
    parser = LocalizedArgumentParser(
        language=language,
        prog="lipis",
        description=text["description"],
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help=(
            "Show this help message and exit."
            if language == "en"
            else "Diese Hilfe anzeigen und beenden."
        ),
    )
    parser.add_argument(
        "--language",
        choices=("en", "de"),
        help=text["language_help"],
    )
    parser.add_argument(
        "-v",
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
    """Parse CLI arguments, selecting explicit language before system locale."""
    provided_arguments = list(sys.argv[1:] if arguments is None else arguments)
    requested_language = None
    for index, argument in enumerate(provided_arguments):
        if argument == "--language" and index + 1 < len(provided_arguments):
            candidate = provided_arguments[index + 1]
        elif argument.startswith("--language="):
            candidate = argument.split("=", 1)[1]
        else:
            continue
        if candidate in ("en", "de"):
            requested_language = candidate

    language = resolve_language(requested_language, environ)
    parser = build_parser(language)
    return parser.parse_args(provided_arguments), language


def run_diagnostics(language: str) -> None:
    """Collect and print the implemented system and hardware diagnostics."""
    system_info = collect_system_info()
    hardware_info = collect_hardware_info()
    print(BANNER)
    print("LIPIS - Linux PostInstall Script")
    print("{}: {}".format(TEXT[language]["version"], VERSION))
    print()
    print(render_system_info(system_info, language))
    print()
    print(render_hardware_info(hardware_info, language, system_info.environment))


def main(
    arguments: Optional[Sequence[str]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> int:
    """Run the CLI and return its process exit status."""
    args, language = parse_arguments(arguments, environ)
    if args.version:
        print("LIPIS {} {}".format(TEXT[language]["version"], VERSION))
        return 0

    run_diagnostics(language)
    return 0


if __name__ == "__main__":
    sys.exit(main())