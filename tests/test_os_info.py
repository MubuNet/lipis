import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from main import build_parser, parse_arguments, resolve_language
from modules.os_info import (
    SystemInfo,
    collect_system_info,
    detect_environment,
    format_uptime,
    parse_os_release,
    render_system_info,
)


class OsReleaseTests(unittest.TestCase):
    def test_parses_quoted_distribution_name(self):
        values = parse_os_release(
            'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.3 LTS"\nID=ubuntu\n'
        )
        self.assertEqual(values["PRETTY_NAME"], "Ubuntu 24.04.3 LTS")
        self.assertEqual(values["ID"], "ubuntu")

    def test_does_not_execute_shell_content(self):
        values = parse_os_release('NAME="$(touch /tmp/lipis-test)"\n')
        self.assertEqual(values["NAME"], "$(touch /tmp/lipis-test)")

    def test_malformed_os_release_is_reported(self):
        with TemporaryDirectory() as directory:
            os_release_path = Path(directory) / "os-release"
            uptime_path = Path(directory) / "uptime"
            os_release_path.write_text('NAME="unterminated\n', encoding="utf-8")
            uptime_path.write_text("60.0 0.0\n", encoding="ascii")

            info = collect_system_info(os_release_path, uptime_path, {})

        self.assertEqual(info.distribution, "Unknown")
        self.assertTrue(any("Could not parse" in warning for warning in info.warnings))

    def test_unavailable_uptime_is_reported(self):
        with TemporaryDirectory() as directory:
            os_release_path = Path(directory) / "os-release"
            uptime_path = Path(directory) / "missing-uptime"
            os_release_path.write_text('PRETTY_NAME="Ubuntu Test"\n', encoding="utf-8")

            info = collect_system_info(os_release_path, uptime_path, {})

        self.assertIsNone(info.uptime_seconds)
        self.assertTrue(any("Could not read" in warning for warning in info.warnings))


class LanguageTests(unittest.TestCase):
    def test_detects_german_system_locale(self):
        self.assertEqual(resolve_language(None, {"LANG": "de_DE.UTF-8"}), "de")

    def test_uses_english_for_unsupported_locale(self):
        self.assertEqual(resolve_language(None, {"LANG": "fr_FR.UTF-8"}), "en")

    def test_explicit_language_overrides_system_locale(self):
        self.assertEqual(resolve_language("de", {"LANG": "en_US.UTF-8"}), "de")

    def test_language_flag_is_available(self):
        arguments, language = parse_arguments(
            ["--language", "de"], {"LANG": "en_US.UTF-8"}
        )
        self.assertEqual(arguments.language, "de")
        self.assertEqual(language, "de")

    def test_german_help_translates_argparse_labels(self):
        help_text = build_parser("de").format_help()
        self.assertIn("Verwendung:", help_text)
        self.assertIn("Optionen:", help_text)
        self.assertIn("Diese Hilfe anzeigen und beenden.", help_text)

    def test_invalid_language_error_is_localized(self):
        error_output = StringIO()
        with redirect_stderr(error_output):
            with self.assertRaises(SystemExit) as raised:
                parse_arguments(["--language", "fr"], {"LANG": "de_DE.UTF-8"})
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Argument --language", error_output.getvalue())
        self.assertIn("ungültige Auswahl", error_output.getvalue())

    def test_short_version_flag_is_available(self):
        arguments, _ = parse_arguments(["-v"], {"LANG": "en_US.UTF-8"})
        self.assertTrue(arguments.version)


class SystemInfoPresentationTests(unittest.TestCase):
    def test_detects_wsl2(self):
        self.assertEqual(
            detect_environment("6.18.1-microsoft-standard-WSL2", {}),
            "WSL 2",
        )

    def test_does_not_misidentify_regular_linux(self):
        self.assertEqual(detect_environment("6.8.0-generic", {}), "Linux")

    def test_formats_uptime_in_both_languages(self):
        self.assertEqual(format_uptime(90061, "en"), "1 day, 1 hour, 1 minute")
        self.assertEqual(format_uptime(90061, "de"), "1 Tag, 1 Stunde, 1 Minute")

    def test_renders_german_labels_and_warnings(self):
        info = SystemInfo(
            distribution="Ubuntu 24.04 LTS",
            kernel="6.8.0",
            architecture="x86_64",
            environment="WSL 2",
            uptime_seconds=None,
            warnings=("Could not read /proc/uptime",),
        )
        output = render_system_info(info, "de")
        self.assertIn("Architektur: x86_64", output)
        self.assertIn("Umgebung: WSL 2", output)
        self.assertIn("Laufzeit: Nicht verfügbar", output)
        self.assertIn("Hinweise:", output)


if __name__ == "__main__":
    unittest.main()
