import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.security import (
    FirewallCheck,
    ProtectionCheck,
    SecurityInfo,
    _check_apparmor,
    _check_aslr,
    _check_kernel_lockdown,
    _check_secure_boot,
    _check_selinux,
    _collect_firewall_checks,
    _collect_security_updates,
    collect_security_info,
    render_security_info,
)


class SecurityUpdateTests(unittest.TestCase):
    def test_finds_security_updates_in_apt_simulation_only(self):
        completed = CompletedProcess(
            args=["apt-get"],
            returncode=0,
            stdout=(
                "Inst openssl [3.0.0] (3.0.1 Ubuntu:24.04-security [amd64])\n"
                "Inst bash [5.2] (5.3 Ubuntu:24.04-updates [amd64])\n"
                "Inst linux-image [1] (2 security.ubuntu.com [amd64])\n"
                "Inst libsecurity-agent [1] (2 Ubuntu:24.04-updates [amd64])\n"
            ),
            stderr="",
        )
        warnings = []
        with patch("modules.security.subprocess.run", return_value=completed) as run:
            packages = _collect_security_updates("/usr/bin/apt-get", warnings)

        self.assertEqual(packages, ("openssl", "linux-image"))
        self.assertEqual(warnings, [])
        arguments = run.call_args.args[0]
        self.assertIn("-s", arguments)
        self.assertNotIn("update", arguments)
        self.assertNotIn("sudo", arguments)

    def test_reports_empty_cached_security_update_list(self):
        completed = CompletedProcess(
            args=["apt-get"], returncode=0, stdout="0 upgraded.\n", stderr=""
        )
        with patch("modules.security.subprocess.run", return_value=completed):
            packages = _collect_security_updates("/usr/bin/apt-get", [])
        self.assertEqual(packages, ())

    def test_reports_update_simulation_failure(self):
        completed = CompletedProcess(
            args=["apt-get"], returncode=100, stdout="", stderr="permission denied"
        )
        warnings = []
        with patch("modules.security.subprocess.run", return_value=completed):
            packages = _collect_security_updates("/usr/bin/apt-get", warnings)
        self.assertIsNone(packages)
        self.assertTrue(any("status 100" in item for item in warnings))


class SecurityStatusTests(unittest.TestCase):
    def test_reads_apparmor_enabled_and_disabled_states(self):
        with TemporaryDirectory() as directory:
            enabled_path = Path(directory) / "enabled"
            enabled_path.write_text("Y\n", encoding="ascii")
            disabled_path = Path(directory) / "disabled"
            disabled_path.write_text("N\n", encoding="ascii")
            self.assertEqual(_check_apparmor(enabled_path, None, []), "enabled")
            self.assertEqual(_check_apparmor(disabled_path, None, []), "disabled")

    def test_uses_aa_status_fallback(self):
        completed = CompletedProcess(["aa-status"], 0, "", "")
        with TemporaryDirectory() as directory:
            with patch("modules.security.subprocess.run", return_value=completed):
                status = _check_apparmor(
                    Path(directory) / "missing", "/usr/sbin/aa-status", []
                )
        self.assertEqual(status, "enabled")

    def test_reads_selinux_enforcing_and_permissive_states(self):
        with TemporaryDirectory() as directory:
            enforce_path = Path(directory) / "enforce"
            enforce_path.write_text("1\n", encoding="ascii")
            self.assertEqual(_check_selinux(enforce_path, None, []), "enforcing")
            enforce_path.write_text("0\n", encoding="ascii")
            self.assertEqual(_check_selinux(enforce_path, None, []), "permissive")

    def test_reads_aslr_and_kernel_lockdown_modes(self):
        with TemporaryDirectory() as directory:
            aslr_path = Path(directory) / "aslr"
            aslr_path.write_text("2\n", encoding="ascii")
            lockdown_path = Path(directory) / "lockdown"
            lockdown_path.write_text("none [integrity] confidentiality\n", encoding="ascii")
            self.assertEqual(_check_aslr(aslr_path, []), "full")
            self.assertEqual(_check_kernel_lockdown(lockdown_path, []), "integrity")

    def test_reads_secure_boot_state_from_mokutil(self):
        completed = CompletedProcess(
            ["mokutil"], 0, "SecureBoot enabled\n", ""
        )
        with patch("modules.security.subprocess.run", return_value=completed):
            status = _check_secure_boot("/usr/bin/mokutil", [])
        self.assertEqual(status, "enabled")

    def test_parses_firewall_status_without_rendering_rules(self):
        outputs = (
            CompletedProcess(
                ["ufw"], 0, "Status: active\n22/tcp ALLOW Anywhere\n", ""
            ),
            CompletedProcess(["firewall-cmd"], 0, "running\n", ""),
            CompletedProcess(["nft"], 0, "table inet filter {\n}\n", ""),
        )
        warnings = []
        with patch("modules.security.subprocess.run", side_effect=outputs):
            checks = _collect_firewall_checks(
                "/usr/sbin/ufw",
                "/usr/bin/firewall-cmd",
                "/usr/sbin/nft",
                warnings,
            )

        self.assertEqual(
            checks,
            (
                FirewallCheck("UFW", "active"),
                FirewallCheck("firewalld", "active"),
                FirewallCheck("nftables", "ruleset present"),
            ),
        )
        self.assertEqual(warnings, [])
        info = SecurityInfo((), checks, (), ())
        rendered = render_security_info(info, "en", "Linux")
        self.assertNotIn("22/tcp", rendered)

    def test_marks_firewall_status_unknown_on_privilege_errors(self):
        failed = CompletedProcess(["nft"], 1, "", "Operation not permitted")
        warnings = []
        with patch("modules.security.subprocess.run", return_value=failed):
            checks = _collect_firewall_checks(None, None, "/usr/sbin/nft", warnings)
        self.assertEqual(checks, (FirewallCheck("nftables", "unknown"),))
        self.assertTrue(any("sufficient access" in item for item in warnings))

    def test_collects_local_security_values_without_tools_or_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apparmor").write_text("N\n", encoding="ascii")
            (root / "selinux").write_text("1\n", encoding="ascii")
            (root / "aslr").write_text("2\n", encoding="ascii")
            (root / "lockdown").write_text("[none] integrity confidentiality\n", encoding="ascii")
            with patch(
                "modules.security.shutil.which",
                side_effect=lambda name: (
                    "/usr/bin/apt-get" if name == "apt-get" else None
                ),
            ), patch(
                "modules.security.subprocess.run",
                return_value=CompletedProcess(
                    ["apt-get"], 0, "0 upgraded.\n", ""
                ),
            ):
                info = collect_security_info(
                    root / "apparmor",
                    root / "selinux",
                    root / "aslr",
                    root / "lockdown",
                )

        self.assertEqual(info.security_update_packages, ())
        self.assertEqual(info.firewall_checks, ())
        self.assertEqual(
            info.protections,
            (
                ProtectionCheck("AppArmor", "disabled"),
                ProtectionCheck("SELinux", "enforcing"),
                ProtectionCheck("Kernel ASLR", "full"),
                ProtectionCheck("Secure Boot", "unknown"),
                ProtectionCheck("Kernel lockdown", "none"),
            ),
        )
        output = render_security_info(info, "en", "Linux")
        self.assertIn("APT metadata may be stale", output)


class SecurityPresentationTests(unittest.TestCase):
    def test_renders_security_details_and_wsl_limitation_in_both_languages(self):
        info = SecurityInfo(
            security_update_packages=("openssl",),
            firewall_checks=(FirewallCheck("UFW", "unknown"),),
            protections=(
                ProtectionCheck("AppArmor", "disabled"),
                ProtectionCheck("Kernel ASLR", "full"),
                ProtectionCheck("Secure Boot", "unknown"),
            ),
            warnings=("APT package metadata may be stale.",),
        )
        english = render_security_info(info, "en", "WSL 2")
        german = render_security_info(info, "de", "WSL 2")

        self.assertIn("Security updates in local APT cache: 1", english)
        self.assertIn("Packages: openssl", english)
        self.assertIn("UFW: not determined", english)
        self.assertIn("Windows host security status is not inferred", english)
        self.assertIn("Sicherheitsupdates laut lokalem APT-Cache: 1", german)
        self.assertIn("Pakete: openssl", german)
        self.assertIn("Windows-Hosts wird nicht abgeleitet", german)


if __name__ == "__main__":
    unittest.main()
