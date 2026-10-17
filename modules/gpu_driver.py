"""Read-only GPU and active driver diagnostics."""

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


PCI_VENDOR_NAMES = {
    "0x10de": "NVIDIA",
    "0x1002": "AMD",
    "0x1022": "AMD",
    "0x8086": "Intel",
}


@dataclass(frozen=True)
class GpuDevice:
    """Information about one detected graphics device."""

    name: str
    vendor: str
    pci_id: Optional[str]
    driver: Optional[str]
    driver_version: Optional[str]


@dataclass(frozen=True)
class GpuInfo:
    """Detected graphics devices and GPU diagnostic warnings."""

    devices: Tuple[GpuDevice, ...]
    wsl_gpu_interface: bool
    warnings: Tuple[str, ...]


def parse_lspci_output(contents: str) -> Tuple[GpuDevice, ...]:
    """Parse display controllers and their active kernel drivers from lspci text."""
    devices: List[GpuDevice] = []
    current_device = None
    for line in contents.splitlines():
        if not line.startswith(("\t", " ")):
            if current_device is not None:
                devices.append(current_device)
            current_device = None
            if not re.search(
                r"\b(?:VGA compatible controller|3D controller|Display controller)\b",
                line,
                re.IGNORECASE,
            ):
                continue

            pci_match = re.search(r"\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\]", line)
            if pci_match is None:
                continue
            pci_id = pci_match.group(1).lower()
            vendor_id = pci_id.split(":", 1)[0]
            vendor = PCI_VENDOR_NAMES.get("0x" + vendor_id, "Unknown")
            name_match = re.search(
                r"\[[0-9a-fA-F]{4}\]:\s*(.*)$",
                line,
            )
            name = name_match.group(1).strip() if name_match else ""
            name = re.sub(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\]", "", name)
            name = re.sub(r"\s*\(rev [^)]+\)$", "", name).strip()
            current_device = GpuDevice(
                name=name or "{} GPU".format(vendor),
                vendor=vendor,
                pci_id=pci_id,
                driver=None,
                driver_version=None,
            )
        elif current_device is not None:
            driver_match = re.match(r"\s*Kernel driver in use:\s*(\S+)", line)
            if driver_match:
                current_device = GpuDevice(
                    name=current_device.name,
                    vendor=current_device.vendor,
                    pci_id=current_device.pci_id,
                    driver=driver_match.group(1),
                    driver_version=current_device.driver_version,
                )

    if current_device is not None:
        devices.append(current_device)
    return tuple(devices)


def read_sysfs_gpus(
    pci_devices_path: Path, warnings: Optional[List[str]] = None
) -> Tuple[GpuDevice, ...]:
    """Read graphics class, vendor, device, and bound driver from PCI sysfs."""
    devices: List[GpuDevice] = []
    try:
        entries = sorted(pci_devices_path.iterdir())
    except OSError as error:
        if warnings is None:
            raise
        warnings.append(
            "Could not read PCI devices from {}: {}".format(
                pci_devices_path, error
            )
        )
        return ()

    for entry in entries:
        try:
            device_class = (entry / "class").read_text(encoding="ascii").strip()
            if not device_class.lower().startswith("0x03"):
                continue
            vendor_id = (entry / "vendor").read_text(encoding="ascii").strip().lower()
            device_id = (entry / "device").read_text(encoding="ascii").strip().lower()
        except OSError as error:
            if warnings is None:
                raise
            warnings.append(
                "Could not read PCI device {}: {}".format(entry.name, error)
            )
            continue

        vendor = PCI_VENDOR_NAMES.get(vendor_id, "Unknown")
        driver_path = entry / "driver"
        try:
            driver = driver_path.resolve(strict=True).name
        except OSError:
            driver = None
        vendor_number = vendor_id[2:] if vendor_id.startswith("0x") else vendor_id
        device_number = device_id[2:] if device_id.startswith("0x") else device_id
        devices.append(
            GpuDevice(
                name="{} GPU [{}:{}]".format(
                    vendor, vendor_number, device_number
                ),
                vendor=vendor,
                pci_id="{}:{}".format(
                    vendor_number, device_number
                ),
                driver=driver,
                driver_version=None,
            )
        )
    return tuple(devices)


def parse_nvidia_smi_output(contents: str) -> Tuple[Tuple[str, str], ...]:
    """Parse NVIDIA model and driver-version rows from query CSV output."""
    devices = []
    for line in contents.splitlines():
        fields = [field.strip() for field in line.split(",", 1)]
        if len(fields) != 2 or not all(fields):
            continue
        if fields[0].lower() == "name" and fields[1].lower() == "driver_version":
            continue
        devices.append((fields[0], fields[1]))
    return tuple(devices)


def collect_gpu_info(
    pci_devices_path: Path = Path("/sys/bus/pci/devices"),
    wsl_dxg_path: Path = Path("/dev/dxg"),
) -> GpuInfo:
    """Collect GPU details from sysfs and optional installed read-only tools."""
    warnings: List[str] = []
    devices = list(read_sysfs_gpus(pci_devices_path, warnings))
    lspci_path = shutil.which("lspci")
    if lspci_path:
        try:
            result = subprocess.run(
                [lspci_path, "-Dnnk"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            warnings.append("Could not run lspci: {}".format(error))
        else:
            if result.returncode == 0:
                lspci_devices = parse_lspci_output(result.stdout)
                merged_devices = []
                for device in devices:
                    match = next(
                        (
                            candidate
                            for candidate in lspci_devices
                            if candidate.pci_id == device.pci_id
                        ),
                        None,
                    )
                    merged_devices.append(
                        GpuDevice(
                            name=match.name if match else device.name,
                            vendor=match.vendor if match else device.vendor,
                            pci_id=device.pci_id,
                            driver=(
                                match.driver
                                if match and match.driver
                                else device.driver
                            ),
                            driver_version=None,
                        )
                    )
                known_ids = {device.pci_id for device in devices}
                merged_devices.extend(
                    device
                    for device in lspci_devices
                    if device.pci_id not in known_ids
                )
                devices = merged_devices
            else:
                warnings.append(
                    "lspci exited with status {}.".format(result.returncode)
                )

    nvidia_smi_path = shutil.which("nvidia-smi")
    if nvidia_smi_path:
        try:
            result = subprocess.run(
                [
                    nvidia_smi_path,
                    "--query-gpu=name,driver_version",
                    "--format=csv,noheader",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            warnings.append("Could not run nvidia-smi: {}".format(error))
        else:
            if result.returncode == 0:
                nvidia_devices = parse_nvidia_smi_output(result.stdout)
                for name, version in nvidia_devices:
                    index = next(
                        (
                            position
                            for position, device in enumerate(devices)
                            if device.vendor == "NVIDIA"
                            and device.driver_version is None
                        ),
                        None,
                    )
                    if index is None:
                        devices.append(
                            GpuDevice(
                                name=name,
                                vendor="NVIDIA",
                                pci_id=None,
                                driver="nvidia",
                                driver_version=version,
                            )
                        )
                    else:
                        device = devices[index]
                        devices[index] = GpuDevice(
                            name=name,
                            vendor=device.vendor,
                            pci_id=device.pci_id,
                            driver=device.driver or "nvidia",
                            driver_version=version,
                        )
            else:
                warnings.append(
                    "nvidia-smi exited with status {}.".format(result.returncode)
                )

    try:
        wsl_gpu_interface = wsl_dxg_path.exists()
    except OSError as error:
        wsl_gpu_interface = False
        warnings.append("Could not inspect {}: {}".format(wsl_dxg_path, error))

    return GpuInfo(
        devices=tuple(devices),
        wsl_gpu_interface=wsl_gpu_interface,
        warnings=tuple(warnings),
    )


def render_gpu_info(info: GpuInfo, language: str, environment: str) -> str:
    """Render detected GPU devices and clearly label WSL limitations."""
    if language == "de":
        labels = {
            "section": "GPU und Treiber",
            "none": "Kein Grafikgerät eindeutig ermittelt.",
            "driver": "Aktiver Treiber",
            "driver_unknown": "Nicht eindeutig ermittelt",
            "version": "Treiberversion",
            "wsl": "WSL-Hinweis",
            "wsl_interface": (
                "Die WSL-GPU-Schnittstelle ist verfügbar. Sie belegt allein "
                "nicht das genaue Host-GPU-Modell oder den Host-Treiber."
            ),
            "wsl_limited": (
                "GPU-Angaben können durch WSL virtualisiert oder eingeschränkt sein."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "GPU and Driver",
            "none": "No graphics device could be identified reliably.",
            "driver": "Active driver",
            "driver_unknown": "Not identified reliably",
            "version": "Driver version",
            "wsl": "WSL note",
            "wsl_interface": (
                "The WSL GPU interface is available. This alone does not confirm "
                "the exact host GPU model or host driver."
            ),
            "wsl_limited": (
                "GPU information may be virtualized or limited by WSL."
            ),
            "warnings": "Warnings",
        }

    lines = ["=== {} ===".format(labels["section"])]
    if not info.devices:
        lines.append(labels["none"])
    for index, device in enumerate(info.devices, 1):
        lines.append(
            "{}. {} ({})".format(index, device.name, device.vendor)
        )
        if device.pci_id:
            lines.append("   PCI ID: {}".format(device.pci_id))
        lines.append(
            "   {}: {}".format(
                labels["driver"], device.driver or labels["driver_unknown"]
            )
        )
        if device.driver_version:
            lines.append("   {}: {}".format(labels["version"], device.driver_version))

    if environment.startswith("WSL"):
        lines.append("{}: {}".format(labels["wsl"], labels["wsl_limited"]))
        if info.wsl_gpu_interface:
            lines.append(labels["wsl_interface"])
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
