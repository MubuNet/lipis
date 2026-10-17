"""Read-only operating-system and kernel diagnostics."""

import math
import os
import platform
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class SystemInfo:
    distribution: str
    kernel: str
    architecture: str
    environment: str
    uptime_seconds: Optional[int]
    warnings: Tuple[str, ...]


def parse_os_release(contents: str) -> Dict[str, str]:
    """Parse os-release key/value lines without executing shell content."""
    values: Dict[str, str] = {}
    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        parsed = shlex.split(raw_value, comments=False, posix=True)
        values[key] = parsed[0] if parsed else ""
    return values


def format_uptime(seconds: int, language: str) -> str:
    if seconds < 60:
        return "<1 minute" if language == "en" else "<1 Minute"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts = []
    units = {
        "en": ("day", "hour", "minute"),
        "de": ("Tag", "Stunde", "Minute"),
    }[language]

    for value, unit in zip((days, hours, minutes), units):
        if value:
            if language == "en":
                suffix = unit if value == 1 else unit + "s"
                parts.append("{} {}".format(value, suffix))
            else:
                suffix = "" if value == 1 else "n"
                parts.append("{} {}{}".format(value, unit, suffix))

    return ", ".join(parts)


def detect_environment(
    kernel: str, environ: Optional[Mapping[str, str]] = None
) -> str:
    environment = os.environ if environ is None else environ
    lowered_kernel = kernel.lower()
    is_wsl = (
        "microsoft" in lowered_kernel
        or "wsl" in lowered_kernel
        or "WSL_DISTRO_NAME" in environment
        or "WSL_INTEROP" in environment
    )
    if not is_wsl:
        return "Linux"
    if "wsl2" in lowered_kernel:
        return "WSL 2"
    return "WSL"


def collect_system_info(
    os_release_path: Path = Path("/etc/os-release"),
    uptime_path: Path = Path("/proc/uptime"),
    environ: Optional[Mapping[str, str]] = None,
) -> SystemInfo:
    warnings: List[str] = []
    release_values: Dict[str, str] = {}
    try:
        os_release_contents = os_release_path.read_text(encoding="utf-8")
    except OSError as error:
        warnings.append("Could not read {}: {}".format(os_release_path, error))
    else:
        try:
            release_values = parse_os_release(os_release_contents)
        except ValueError as error:
            warnings.append("Could not parse {}: {}".format(os_release_path, error))

    distribution = (
        release_values.get("PRETTY_NAME")
        or release_values.get("NAME")
        or "Unknown"
    )
    if distribution == "Unknown":
        warnings.append("Distribution information is unavailable.")

    kernel = platform.release()
    try:
        uptime_contents = uptime_path.read_text(encoding="ascii")
        uptime_value = float(uptime_contents.split()[0])
        if not math.isfinite(uptime_value) or uptime_value < 0:
            raise ValueError("uptime must be a non-negative finite number")
        uptime_seconds = int(uptime_value)
    except OSError as error:
        uptime_seconds = None
        warnings.append("Could not read {}: {}".format(uptime_path, error))
    except (IndexError, OverflowError, ValueError) as error:
        uptime_seconds = None
        warnings.append("Could not parse {}: {}".format(uptime_path, error))

    return SystemInfo(
        distribution=distribution,
        kernel=kernel,
        architecture=platform.machine(),
        environment=detect_environment(kernel, environ),
        uptime_seconds=uptime_seconds,
        warnings=tuple(warnings),
    )


def render_system_info(info: SystemInfo, language: str) -> str:
    if language == "de":
        labels = {
            "section": "System",
            "distribution": "Distribution",
            "kernel": "Kernel",
            "architecture": "Architektur",
            "environment": "Umgebung",
            "uptime": "Laufzeit",
            "unavailable": "Nicht verfügbar",
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "System",
            "distribution": "Distribution",
            "kernel": "Kernel",
            "architecture": "Architecture",
            "environment": "Environment",
            "uptime": "Uptime",
            "unavailable": "Unavailable",
            "warnings": "Warnings",
        }

    uptime = (
        labels["unavailable"]
        if info.uptime_seconds is None
        else format_uptime(info.uptime_seconds, language)
    )
    lines = [
        "=== {} ===".format(labels["section"]),
        "{}: {}".format(labels["distribution"], info.distribution),
        "{}: {}".format(labels["kernel"], info.kernel),
        "{}: {}".format(labels["architecture"], info.architecture),
        "{}: {}".format(labels["environment"], info.environment),
        "{}: {}".format(labels["uptime"], uptime),
    ]
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
