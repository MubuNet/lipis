"""Read-only Linux security status diagnostics."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class FirewallCheck:
    """Read-only status for one locally available firewall frontend."""

    tool: str
    status: str


@dataclass(frozen=True)
class ProtectionCheck:
    """Status of one kernel or mandatory-access-control protection."""

    name: str
    status: str


@dataclass(frozen=True)
class SecurityInfo:
    """Collected cached update hints, firewall checks, and protections."""

    security_update_packages: Optional[Tuple[str, ...]]
    firewall_checks: Tuple[FirewallCheck, ...]
    protections: Tuple[ProtectionCheck, ...]
    warnings: Tuple[str, ...]


def _run_command(
    tool_path: str,
    arguments: List[str],
    tool_name: str,
    warnings: List[str],
    timeout: int = 5,
) -> Optional[subprocess.CompletedProcess]:
    """Run a local status command without a shell, root, or network refresh."""
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        return subprocess.run(
            [tool_path] + arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        warnings.append("Could not run {}: {}".format(tool_name, error))
        return None


def _read_optional_text(path: Path, warnings: List[str]) -> Optional[str]:
    """Read a local status file while distinguishing missing from unreadable."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        warnings.append("Could not read {}: {}".format(path, error))
        return None


def _collect_security_updates(
    apt_get_path: Optional[str],
    warnings: List[str],
) -> Optional[Tuple[str, ...]]:
    """Find security-pocket upgrades from a simulation using cached APT data."""
    if apt_get_path is None:
        warnings.append("APT is unavailable; cached security updates were not checked.")
        return None

    result = _run_command(
        apt_get_path,
        ["-s", "-o", "Debug::NoLocking=1", "upgrade"],
        "apt-get",
        warnings,
        timeout=20,
    )
    if result is None:
        return None
    if result.returncode != 0:
        warnings.append(
            "apt-get upgrade simulation exited with status {}.".format(
                result.returncode
            )
        )
        return None

    packages = []
    for line in result.stdout.splitlines():
        match = re.match(r"^Inst\s+(\S+)\b", line)
        candidate_source = line.partition("(")[2].rsplit(")", 1)[0]
        if match and re.search(
            r"(?:-security\b|\bsecurity\b)", candidate_source, re.IGNORECASE
        ):
            package_name = match.group(1)
            if package_name not in packages:
                packages.append(package_name)
    return tuple(packages)


def _collect_firewall_checks(
    ufw_path: Optional[str],
    firewall_cmd_path: Optional[str],
    nft_path: Optional[str],
    warnings: List[str],
) -> Tuple[FirewallCheck, ...]:
    """Read status from installed firewall tools without exposing rule contents."""
    checks = []

    if ufw_path:
        result = _run_command(ufw_path, ["status"], "ufw", warnings)
        status = "unknown"
        if result is not None:
            if result.returncode == 0:
                match = re.search(
                    r"^\s*Status:\s*(active|inactive)\s*$",
                    result.stdout,
                    re.IGNORECASE | re.MULTILINE,
                )
                if match:
                    status = match.group(1).lower()
                else:
                    warnings.append("Could not parse UFW status output.")
            else:
                warnings.append(
                    "Could not determine UFW status without sufficient access "
                    "(exit status {}).".format(result.returncode)
                )
        checks.append(FirewallCheck("UFW", status))

    if firewall_cmd_path:
        result = _run_command(
            firewall_cmd_path, ["--state"], "firewall-cmd", warnings
        )
        status = "unknown"
        if result is not None:
            output = result.stdout.strip().lower()
            if result.returncode == 0 and output == "running":
                status = "active"
            elif output == "not running":
                status = "inactive"
            else:
                warnings.append("Could not determine firewalld status.")
        checks.append(FirewallCheck("firewalld", status))

    if nft_path:
        result = _run_command(nft_path, ["list", "ruleset"], "nft", warnings)
        status = "unknown"
        if result is not None:
            if result.returncode == 0:
                status = (
                    "ruleset present"
                    if result.stdout.strip()
                    else "no rules listed"
                )
            else:
                warnings.append(
                    "Could not read nftables status without sufficient access "
                    "(exit status {}).".format(result.returncode)
                )
        checks.append(FirewallCheck("nftables", status))

    return tuple(checks)


def _check_apparmor(
    enabled_path: Path,
    aa_status_path: Optional[str],
    warnings: List[str],
) -> str:
    """Determine AppArmor enabled state without listing profile names."""
    value = _read_optional_text(enabled_path, warnings)
    if value is not None:
        if value.upper() == "Y":
            return "enabled"
        if value.upper() == "N":
            return "disabled"
        warnings.append("Could not interpret AppArmor enabled state.")
        return "unknown"

    if aa_status_path is None:
        return "unknown"
    result = _run_command(
        aa_status_path, ["--enabled"], "aa-status", warnings
    )
    if result is None:
        return "unknown"
    if result.returncode == 0:
        return "enabled"
    if result.returncode == 1 and not result.stderr.strip():
        return "disabled"
    warnings.append(
        "Could not determine AppArmor status without sufficient access."
    )
    return "unknown"


def _check_selinux(
    enforce_path: Path,
    getenforce_path: Optional[str],
    warnings: List[str],
) -> str:
    """Determine SELinux enforcing state from sysfs or getenforce."""
    value = _read_optional_text(enforce_path, warnings)
    if value is not None:
        if value == "1":
            return "enforcing"
        if value == "0":
            return "permissive"
        warnings.append("Could not interpret SELinux enforcing state.")
        return "unknown"

    if getenforce_path is None:
        return "unknown"
    result = _run_command(getenforce_path, [], "getenforce", warnings)
    if result is None:
        return "unknown"
    if result.returncode == 0:
        value = result.stdout.strip().lower()
        if value in ("enforcing", "permissive", "disabled"):
            return value
    warnings.append("Could not determine SELinux status.")
    return "unknown"


def _check_aslr(path: Path, warnings: List[str]) -> str:
    """Read kernel address-space randomization mode."""
    value = _read_optional_text(path, warnings)
    if value == "0":
        return "disabled"
    if value == "1":
        return "partial"
    if value == "2":
        return "full"
    if value is not None:
        warnings.append("Could not interpret kernel ASLR value.")
    return "unknown"


def _check_secure_boot(
    mokutil_path: Optional[str],
    warnings: List[str],
) -> str:
    """Read Secure Boot state from mokutil when available."""
    if mokutil_path is None:
        return "unknown"
    result = _run_command(
        mokutil_path, ["--sb-state"], "mokutil", warnings
    )
    if result is None:
        return "unknown"
    if result.returncode == 0:
        output = result.stdout.lower()
        if re.search(r"\bsecureboot\s+enabled\b", output):
            return "enabled"
        if re.search(r"\bsecureboot\s+disabled\b", output):
            return "disabled"
    warnings.append("Could not determine Secure Boot state.")
    return "unknown"


def _check_kernel_lockdown(path: Path, warnings: List[str]) -> str:
    """Read the active kernel lockdown mode from the securityfs status file."""
    value = _read_optional_text(path, warnings)
    if value is None:
        return "unknown"
    match = re.search(r"\[([^\]]+)\]", value)
    if match:
        return match.group(1).lower()
    warnings.append("Could not parse kernel lockdown status.")
    return "unknown"


def collect_security_info(
    apparmor_enabled_path: Path = Path("/sys/module/apparmor/parameters/enabled"),
    selinux_enforce_path: Path = Path("/sys/fs/selinux/enforce"),
    aslr_path: Path = Path("/proc/sys/kernel/randomize_va_space"),
    lockdown_path: Path = Path("/sys/kernel/security/lockdown"),
) -> SecurityInfo:
    """Collect cached APT, firewall, and Linux protection status without root."""
    warnings: List[str] = []
    apt_get_path = shutil.which("apt-get")
    security_update_packages = _collect_security_updates(apt_get_path, warnings)
    firewall_checks = _collect_firewall_checks(
        shutil.which("ufw"),
        shutil.which("firewall-cmd"),
        shutil.which("nft"),
        warnings,
    )

    protections = (
        ProtectionCheck(
            "AppArmor",
            _check_apparmor(apparmor_enabled_path, shutil.which("aa-status"), warnings),
        ),
        ProtectionCheck(
            "SELinux",
            _check_selinux(selinux_enforce_path, shutil.which("getenforce"), warnings),
        ),
        ProtectionCheck("Kernel ASLR", _check_aslr(aslr_path, warnings)),
        ProtectionCheck(
            "Secure Boot",
            _check_secure_boot(shutil.which("mokutil"), warnings),
        ),
        ProtectionCheck(
            "Kernel lockdown",
            _check_kernel_lockdown(lockdown_path, warnings),
        ),
    )
    return SecurityInfo(
        security_update_packages=security_update_packages,
        firewall_checks=firewall_checks,
        protections=protections,
        warnings=tuple(warnings),
    )


def render_security_info(
    info: SecurityInfo,
    language: str,
    environment: str,
) -> str:
    """Render security findings with explicit unknown and stale-cache states."""
    if language == "de":
        labels = {
            "section": "Sicherheit",
            "updates": "Sicherheitsupdates laut lokalem APT-Cache",
            "updates_unknown": "Nicht ermittelbar",
            "none": "Keine",
            "packages": "Pakete",
            "cache_note": (
                "Der lokale APT-Cache kann veraltet sein; es wurde keine "
                "Netzwerkaktualisierung ausgeführt."
            ),
            "firewall": "Firewall-Status",
            "no_firewall_tools": "Kein unterstütztes Firewall-Statuswerkzeug gefunden.",
            "active": "aktiv",
            "inactive": "inaktiv",
            "ruleset_present": "Regelsatz vorhanden",
            "no_rules_listed": "Keine Regeln aufgeführt",
            "unknown": "nicht ermittelbar",
            "protections": "Lokale Schutzmechanismen",
            "enabled": "aktiviert",
            "disabled": "deaktiviert",
            "enforcing": "erzwingend",
            "permissive": "permissiv",
            "partial": "teilweise",
            "full": "vollständig",
            "none_mode": "kein Modus",
            "integrity": "Integritätsmodus",
            "confidentiality": "Vertraulichkeitsmodus",
            "wsl": (
                "Angaben beziehen sich auf Linux/WSL; der Sicherheitsstatus des "
                "Windows-Hosts wird nicht abgeleitet."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "Security",
            "updates": "Security updates in local APT cache",
            "updates_unknown": "Not determined",
            "none": "None",
            "packages": "Packages",
            "cache_note": (
                "Local APT metadata may be stale; no network refresh was performed."
            ),
            "firewall": "Firewall status",
            "no_firewall_tools": "No supported firewall status tool found.",
            "active": "active",
            "inactive": "inactive",
            "ruleset_present": "ruleset present",
            "no_rules_listed": "no rules listed",
            "unknown": "not determined",
            "protections": "Local protection mechanisms",
            "enabled": "enabled",
            "disabled": "disabled",
            "enforcing": "enforcing",
            "permissive": "permissive",
            "partial": "partial",
            "full": "full",
            "none_mode": "none",
            "integrity": "integrity",
            "confidentiality": "confidentiality",
            "wsl": (
                "Values describe the Linux/WSL environment; Windows host security "
                "status is not inferred."
            ),
            "warnings": "Warnings",
        }

    status_labels = {
        "active": labels["active"],
        "inactive": labels["inactive"],
        "enabled": labels["enabled"],
        "disabled": labels["disabled"],
        "enforcing": labels["enforcing"],
        "permissive": labels["permissive"],
        "partial": labels["partial"],
        "full": labels["full"],
        "none": labels["none_mode"],
        "integrity": labels["integrity"],
        "confidentiality": labels["confidentiality"],
        "ruleset present": labels["ruleset_present"],
        "no rules listed": labels["no_rules_listed"],
        "unknown": labels["unknown"],
    }
    lines = ["=== {} ===".format(labels["section"])]
    if info.security_update_packages is None:
        lines.append("{}: {}".format(labels["updates"], labels["updates_unknown"]))
    else:
        lines.append(
            "{}: {}".format(labels["updates"], len(info.security_update_packages))
        )
        if info.security_update_packages:
            lines.append(
                "  {}: {}".format(
                    labels["packages"], ", ".join(info.security_update_packages)
                )
            )
        lines.append(labels["cache_note"])

    lines.append("{}:".format(labels["firewall"]))
    if info.firewall_checks:
        for check in info.firewall_checks:
            lines.append(
                "  {}: {}".format(
                    check.tool, status_labels.get(check.status, labels["unknown"])
                )
            )
    else:
        lines.append("  {}".format(labels["no_firewall_tools"]))

    lines.append("{}:".format(labels["protections"]))
    for protection in info.protections:
        lines.append(
            "  {}: {}".format(
                protection.name,
                status_labels.get(protection.status, labels["unknown"]),
            )
        )
    if environment.startswith("WSL"):
        lines.append("WSL: {}".format(labels["wsl"]))
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
