import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import main
from main import build_parser, parse_arguments
from modules.report import (
    REPORT_FILENAME,
    render_markdown_report,
    write_markdown_report,
)


class ReportRenderingTests(unittest.TestCase):
    def test_renders_localized_markdown_and_includes_security_findings(self):
        timestamp = datetime(2026, 10, 17, 14, 30, tzinfo=timezone.utc)
        report = render_markdown_report(
            (
                "=== System ===\nDistribution: Ubuntu\nWarnings:\n- hidden path",
                "=== Security ===\nAppArmor: disabled\nSicherheitsupdates: 0",
            ),
            "en",
            timestamp,
        )

        self.assertIn("# LIPIS Diagnostic Report", report)
        self.assertIn("Generated: 2026-10-17T14:30:00+00:00", report)
        self.assertIn("## System", report)
        self.assertIn("## Security", report)
        self.assertIn("AppArmor: disabled", report)
        self.assertNotIn("hidden path", report)

    def test_omits_network_section_ssid_path_and_personal_warning_details(self):
        report = render_markdown_report(
            (
                "=== Hardware ===\n"
                "Filesystem of current directory: /home/private-user/lipis\n"
                "  Free: 12.0 GiB\n"
                "Warnings:\n"
                "- Could not inspect /home/private-user/lipis\n",
                "=== Wi-Fi ===\n"
                "wlan0:\n"
                "  Connection: connected\n"
                "  Current SSID: PrivateNetworkName\n"
                "=== Bluetooth ===\n"
                "No Bluetooth controller found.",
                "=== Network ===\n"
                "MAC address: 02:11:22:33:44:55\n"
                "IPv4 addresses: 192.0.2.7\n"
                "Default gateways:\n"
                "DNS servers: 192.0.2.1",
            ),
            "en",
            datetime(2026, 10, 17, tzinfo=timezone.utc),
        )

        self.assertIn("Filesystem of current directory: [path omitted]", report)
        self.assertIn("Connection: connected", report)
        self.assertIn("No Bluetooth controller found.", report)
        for private_value in (
            "/home/private-user/lipis",
            "private-user",
            "PrivateNetworkName",
            "02:11:22:33:44:55",
            "192.0.2.7",
            "192.0.2.1",
        ):
            self.assertNotIn(private_value, report)

    def test_removes_german_ssids_and_current_directory_path(self):
        report = render_markdown_report(
            (
                "=== Hardware ===\n"
                "Dateisystem des aktuellen Ordners: /home/mubu/lipis\n",
                "=== WLAN ===\n"
                "  Aktuelle SSID: MeinWLAN\n",
            ),
            "de",
            datetime(2026, 10, 17, tzinfo=timezone.utc),
        )

        self.assertIn(
            "Dateisystem des aktuellen Ordners: [path omitted]", report
        )
        self.assertNotIn("/home/mubu/lipis", report)
        self.assertNotIn("MeinWLAN", report)
        self.assertIn("# LIPIS-Diagnosebericht", report)


class ReportWritingTests(unittest.TestCase):
    def test_writes_report_in_selected_working_directory_and_replaces_existing(self):
        with TemporaryDirectory() as directory:
            report_path = Path(directory) / REPORT_FILENAME
            report_path.write_text("old report", encoding="utf-8")

            written_path = write_markdown_report(
                ("=== System ===\nDistribution: Xubuntu",),
                "en",
                Path(directory),
                datetime(2026, 10, 17, tzinfo=timezone.utc),
            )

            contents = report_path.read_text(encoding="utf-8")

        self.assertEqual(written_path, report_path)
        self.assertIn("Distribution: Xubuntu", contents)
        self.assertNotIn("old report", contents)


class ReportCliTests(unittest.TestCase):
    def test_report_is_opt_in_and_has_localized_help(self):
        default_args, _ = parse_arguments([], {"LANG": "en_US.UTF-8"})
        report_args, _ = parse_arguments(["--report"], {"LANG": "en_US.UTF-8"})

        self.assertFalse(default_args.report)
        self.assertTrue(report_args.report)
        self.assertIn(
            "Write a privacy-filtered Markdown report.",
            build_parser("en").format_help(),
        )
        self.assertIn(
            "Einen datenschutzgefilterten Markdown-Bericht schreiben.",
            build_parser("de").format_help(),
        )
        help_output = StringIO()
        with redirect_stdout(help_output), self.assertRaises(SystemExit) as raised:
            parse_arguments(["--help"], {"LANG": "en_US.UTF-8"})
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--report", help_output.getvalue())

    def test_report_reuses_rendered_diagnostics_and_omits_network(self):
        collector_names = (
            "collect_system_info",
            "collect_hardware_info",
            "collect_gpu_info",
            "collect_wireless_bluetooth_info",
            "collect_audio_info",
            "collect_network_info",
            "collect_security_info",
        )
        renderer_names = (
            "render_system_info",
            "render_hardware_info",
            "render_gpu_info",
            "render_wireless_bluetooth_info",
            "render_audio_info",
            "render_network_info",
            "render_security_info",
        )
        output = StringIO()
        with ExitStack() as patches:
            collectors = [
                patches.enter_context(
                    patch(
                        "main.{}".format(name),
                        return_value=SimpleNamespace(environment="Linux"),
                    )
                )
                for name in collector_names
            ]
            renderers = [
                patches.enter_context(
                    patch("main.{}".format(name), return_value=section)
                )
                for name, section in zip(
                    renderer_names,
                    (
                        "=== System ===\nsystem",
                        "=== Hardware ===\nhardware",
                        "=== GPU and Driver ===\ngpu",
                        "=== Wi-Fi ===\nwifi",
                        "=== Audio ===\naudio",
                        "=== Network ===\nprivate network",
                        "=== Security ===\nsecurity",
                    ),
                )
            ]
            report_writer = patches.enter_context(
                patch("main.write_markdown_report")
            )
            with redirect_stdout(output):
                self.assertTrue(main.run_diagnostics("en", create_report=True))

        for collector in collectors:
            collector.assert_called_once_with()
        for renderer in renderers:
            self.assertEqual(renderer.call_count, 1)
        report_sections = report_writer.call_args.args[0]
        self.assertNotIn("=== Network ===\nprivate network", report_sections)
        self.assertIn("=== Security ===\nsecurity", report_sections)
        self.assertIn("Report saved as {}".format(REPORT_FILENAME), output.getvalue())

    def test_report_write_error_is_reported_and_returns_failure(self):
        collector_names = (
            "collect_system_info",
            "collect_hardware_info",
            "collect_gpu_info",
            "collect_wireless_bluetooth_info",
            "collect_audio_info",
            "collect_network_info",
            "collect_security_info",
        )
        renderer_names = (
            "render_system_info",
            "render_hardware_info",
            "render_gpu_info",
            "render_wireless_bluetooth_info",
            "render_audio_info",
            "render_network_info",
            "render_security_info",
        )
        error_output = StringIO()
        with ExitStack() as patches:
            for name in collector_names:
                patches.enter_context(
                    patch(
                        "main.{}".format(name),
                        return_value=SimpleNamespace(environment="Linux"),
                    )
                )
            for name in renderer_names:
                patches.enter_context(patch("main.{}".format(name), return_value=""))
            patches.enter_context(
                patch(
                    "main.write_markdown_report",
                    side_effect=PermissionError("permission denied"),
                )
            )
            with redirect_stderr(error_output):
                self.assertFalse(main.run_diagnostics("en", create_report=True))

        self.assertIn("Could not write report: permission denied", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
