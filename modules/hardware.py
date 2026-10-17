"""Read-only CPU, memory, and filesystem diagnostics."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FilesystemInfo:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


@dataclass(frozen=True)
class HardwareInfo:
    cpu_model: Optional[str]
    logical_cpus: Optional[int]
    memory_total_bytes: Optional[int]
    memory_available_bytes: Optional[int]
    root_filesystem: Optional[FilesystemInfo]
    current_filesystem: Optional[FilesystemInfo]
    warnings: Tuple[str, ...]


def parse_cpu_info(contents: str) -> Tuple[Optional[str], Optional[int]]:
    cpu_model = None
    logical_cpus = 0

    for line in contents.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        normalized_key = key.lower()
        if normalized_key == "processor" and value.isdigit():
            logical_cpus += 1
        elif normalized_key in ("model name", "hardware", "processor") and value:
            if cpu_model is None:
                cpu_model = value

    if logical_cpus == 0:
        logical_cpus = os.cpu_count() or 0
    return cpu_model, logical_cpus or None


def parse_memory_info(contents: str) -> Dict[str, int]:
    memory: Dict[str, int] = {}
    for line in contents.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        fields = raw_value.split()
        if not fields:
            continue
        try:
            value = int(fields[0])
        except ValueError:
            continue
        if len(fields) > 1 and fields[1].lower() == "kb":
            value *= 1024
        memory[key] = value
    return memory


def collect_hardware_info(
    cpu_info_path: Path = Path("/proc/cpuinfo"),
    memory_info_path: Path = Path("/proc/meminfo"),
    disk_path: Path = Path("/"),
    current_directory_path: Optional[Path] = None,
) -> HardwareInfo:
    warnings: List[str] = []

    cpu_model: Optional[str] = None
    logical_cpus: Optional[int] = None
    try:
        cpu_model, logical_cpus = parse_cpu_info(
            cpu_info_path.read_text(encoding="utf-8")
        )
    except OSError as error:
        warnings.append("Could not read {}: {}".format(cpu_info_path, error))
        logical_cpus = os.cpu_count()

    memory_total_bytes: Optional[int] = None
    memory_available_bytes: Optional[int] = None
    try:
        memory = parse_memory_info(memory_info_path.read_text(encoding="ascii"))
        memory_total_bytes = memory.get("MemTotal")
        memory_available_bytes = memory.get("MemAvailable")
        if memory_total_bytes is None:
            warnings.append("Total memory information is unavailable.")
        if memory_available_bytes is None:
            warnings.append("Available memory information is unavailable.")
    except OSError as error:
        warnings.append("Could not read {}: {}".format(memory_info_path, error))

    if current_directory_path is None:
        current_directory_path = Path.cwd()

    def filesystem_info(path: Path) -> Optional[FilesystemInfo]:
        try:
            usage = shutil.disk_usage(path)
        except OSError as error:
            warnings.append("Could not inspect filesystem {}: {}".format(path, error))
            return None
        return FilesystemInfo(
            path=str(path),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
        )

    root_filesystem = filesystem_info(disk_path)
    current_filesystem = filesystem_info(current_directory_path)

    return HardwareInfo(
        cpu_model=cpu_model,
        logical_cpus=logical_cpus,
        memory_total_bytes=memory_total_bytes,
        memory_available_bytes=memory_available_bytes,
        root_filesystem=root_filesystem,
        current_filesystem=current_filesystem,
        warnings=tuple(warnings),
    )


def format_size(byte_count: int) -> str:
    gibibytes = byte_count / (1024 ** 3)
    return "{:.1f} GiB".format(gibibytes)


def render_hardware_info(
    info: HardwareInfo,
    language: str,
    environment: str,
) -> str:
    if language == "de":
        labels = {
            "section": "Hardware",
            "cpu": "CPU-Modell",
            "logical_cpus": "Logische CPUs",
            "memory_total": "Arbeitsspeicher gesamt",
            "memory_available": "Arbeitsspeicher verfügbar",
            "root_filesystem": "Linux-Root-Dateisystem (/)",
            "current_filesystem": "Dateisystem des aktuellen Ordners",
            "filesystem_total": "  Gesamt",
            "filesystem_used": "  Belegt",
            "filesystem_free": "  Frei",
            "unavailable": "Nicht verfügbar",
            "wsl_note": (
                "Werte beziehen sich auf die WSL-Umgebung; Hardware und "
                "Speicherplatz können virtualisiert sein."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "Hardware",
            "cpu": "CPU model",
            "logical_cpus": "Logical CPUs",
            "memory_total": "Total memory",
            "memory_available": "Available memory",
            "root_filesystem": "Linux root filesystem (/)",
            "current_filesystem": "Filesystem of current directory",
            "filesystem_total": "  Total",
            "filesystem_used": "  Used",
            "filesystem_free": "  Free",
            "unavailable": "Unavailable",
            "wsl_note": (
                "Values describe the WSL environment; hardware and storage "
                "may be virtualized."
            ),
            "warnings": "Warnings",
        }

    def memory_value(value: Optional[int]) -> str:
        if value is None:
            return labels["unavailable"]
        return format_size(value)

    lines = [
        "=== {} ===".format(labels["section"]),
        "{}: {}".format(labels["cpu"], info.cpu_model or labels["unavailable"]),
        "{}: {}".format(
            labels["logical_cpus"],
            info.logical_cpus if info.logical_cpus is not None else labels["unavailable"],
        ),
        "{}: {}".format(
            labels["memory_total"], memory_value(info.memory_total_bytes)
        ),
        "{}: {}".format(
            labels["memory_available"],
            memory_value(info.memory_available_bytes),
        ),
    ]

    filesystems = (
        (labels["root_filesystem"], info.root_filesystem),
        (labels["current_filesystem"], info.current_filesystem),
    )
    for heading, filesystem in filesystems:
        if filesystem is None:
            lines.append("{}: {}".format(heading, labels["unavailable"]))
            continue
        lines.extend(
            (
                "{}: {}".format(heading, filesystem.path),
                "{}: {}".format(
                    labels["filesystem_total"], format_size(filesystem.total_bytes)
                ),
                "{}: {}".format(
                    labels["filesystem_used"], format_size(filesystem.used_bytes)
                ),
                "{}: {}".format(
                    labels["filesystem_free"], format_size(filesystem.free_bytes)
                ),
            )
        )
    if environment.startswith("WSL"):
        lines.append(labels["wsl_note"])
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
