"""Read-only wireless and Bluetooth diagnostics."""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class WifiInterface:
    """Read-only state for one Linux wireless network interface."""

    name: str
    driver: Optional[str]
    state: Optional[str]
    connected: Optional[bool]
    ssid: Optional[str]


@dataclass(frozen=True)
class BluetoothController:
    """Read-only state for one Linux Bluetooth controller."""

    name: str
    driver: Optional[str]
    powered: Optional[bool]


@dataclass(frozen=True)
class WirelessBluetoothInfo:
    """Collected wireless and Bluetooth details with diagnostic warnings."""

    wifi_interfaces: Tuple[WifiInterface, ...]
    bluetooth_controllers: Tuple[BluetoothController, ...]
    rfkill_states: Tuple[Tuple[str, bool], ...]
    warnings: Tuple[str, ...]


def _clean_display_value(value: str) -> Optional[str]:
    """Remove terminal control characters before displaying external values."""
    cleaned = "".join(character for character in value if character.isprintable())
    cleaned = cleaned.strip()
    return cleaned or None


def _read_text(path: Path, warnings: List[str]) -> Optional[str]:
    """Read a sysfs text value and record any filesystem error."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        warnings.append("Could not read {}: {}".format(path, error))
        return None


def _driver_name(interface_path: Path, warnings: List[str]) -> Optional[str]:
    """Return the bound kernel driver name when sysfs exposes one."""
    try:
        return (interface_path / "device" / "driver").resolve(strict=True).name
    except FileNotFoundError:
        return None
    except OSError as error:
        warnings.append(
            "Could not inspect driver for {}: {}".format(interface_path.name, error)
        )
        return None


def _list_entries(path: Path, warnings: List[str]) -> Tuple[Path, ...]:
    """List sysfs entries, treating a missing device class as no devices."""
    try:
        return tuple(sorted(path.iterdir()))
    except FileNotFoundError:
        return ()
    except OSError as error:
        warnings.append("Could not list {}: {}".format(path, error))
        return ()


def _run_tool(
    tool_path: str,
    arguments: List[str],
    tool_name: str,
    warnings: List[str],
) -> Optional[str]:
    """Run an installed diagnostic tool without a shell or elevated privileges."""
    try:
        result = subprocess.run(
            [tool_path] + arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        warnings.append("Could not run {}: {}".format(tool_name, error))
        return None

    if result.returncode != 0:
        warnings.append(
            "{} exited with status {}.".format(tool_name, result.returncode)
        )
        return None
    return result.stdout


def _parse_iw_link(contents: str) -> Tuple[Optional[bool], Optional[str]]:
    """Parse only connection state and SSID from `iw link` output."""
    if any(line.strip().lower().startswith("not connected") for line in contents.splitlines()):
        return False, None

    connected = False
    ssid = None
    for line in contents.splitlines():
        if re.match(r"^\s*Connected to\b", line, re.IGNORECASE):
            connected = True
        match = re.match(r"^\s*SSID:\s*(.*)$", line)
        if match:
            connected = True
            ssid = _clean_display_value(match.group(1))
    return (True if connected else None), ssid


def _read_nmcli_connection(
    tool_path: str,
    interface_name: str,
    warnings: List[str],
) -> Tuple[Optional[bool], Optional[str]]:
    """Read the active profile's SSID without requesting a Wi-Fi scan."""
    connection_uuid_output = _run_tool(
        tool_path,
        [
            "--get-values",
            "GENERAL.CON-UUID",
            "device",
            "show",
            interface_name,
        ],
        "nmcli",
        warnings,
    )
    if connection_uuid_output is None:
        return None, None

    connection_uuid = connection_uuid_output.strip()
    if not connection_uuid or connection_uuid == "--":
        return False, None

    ssid_output = _run_tool(
        tool_path,
        [
            "--get-values",
            "802-11-wireless.ssid",
            "connection",
            "show",
            "uuid",
            connection_uuid,
        ],
        "nmcli",
        warnings,
    )
    if ssid_output is None:
        return True, None
    return True, _clean_display_value(ssid_output.splitlines()[0]) if ssid_output else None


def _read_wifi_interfaces(
    net_class_path: Path,
    iw_path: Optional[str],
    nmcli_path: Optional[str],
    warnings: List[str],
) -> Tuple[WifiInterface, ...]:
    """Collect Wi-Fi state from sysfs and optional preinstalled utilities."""
    interfaces = []
    for interface_path in _list_entries(net_class_path, warnings):
        try:
            (interface_path / "wireless").stat()
        except FileNotFoundError:
            continue
        except OSError as error:
            warnings.append(
                "Could not inspect wireless interface {}: {}".format(
                    interface_path.name, error
                )
            )
            continue

        state = _read_text(interface_path / "operstate", warnings)
        connected = None
        ssid = None
        if iw_path:
            output = _run_tool(
                iw_path,
                ["dev", interface_path.name, "link"],
                "iw",
                warnings,
            )
            if output is not None:
                connected, ssid = _parse_iw_link(output)
        if connected is None and nmcli_path:
            connected, ssid = _read_nmcli_connection(
                nmcli_path, interface_path.name, warnings
            )

        interfaces.append(
            WifiInterface(
                name=interface_path.name,
                driver=_driver_name(interface_path, warnings),
                state=state,
                connected=connected,
                ssid=ssid,
            )
        )
    return tuple(interfaces)


def _parse_rfkill_output(contents: str) -> Tuple[Tuple[str, bool], ...]:
    """Parse rfkill JSON into aggregate Wi-Fi and Bluetooth block states."""
    data = json.loads(contents)
    if not isinstance(data, dict):
        raise ValueError("rfkill JSON must contain an object")
    devices = data.get("rfkilldevices")
    if not isinstance(devices, list):
        raise ValueError("rfkill JSON does not contain a device list")

    blocked_by_type: Dict[str, List[bool]] = {"wifi": [], "bluetooth": []}
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_type = str(device.get("type", "")).lower()
        if device_type in ("wlan", "wifi", "wireless lan"):
            kind = "wifi"
        elif device_type == "bluetooth":
            kind = "bluetooth"
        else:
            continue
        soft = device.get("soft")
        hard = device.get("hard")
        if not isinstance(soft, bool) or not isinstance(hard, bool):
            raise ValueError("rfkill JSON contains invalid block state")
        blocked_by_type[kind].append(soft or hard)

    return tuple(
        (kind, any(states))
        for kind, states in blocked_by_type.items()
        if states
    )


def _read_bluetooth_controllers(
    bluetooth_class_path: Path,
    bluetoothctl_path: Optional[str],
    warnings: List[str],
) -> Tuple[BluetoothController, ...]:
    """Collect controller names, bound drivers, and power state without scanning."""
    controllers = []
    for controller_path in _list_entries(bluetooth_class_path, warnings):
        if not controller_path.name.startswith("hci"):
            continue

        address = _read_text(controller_path / "address", warnings)
        powered = None
        if bluetoothctl_path and address:
            output = _run_tool(
                bluetoothctl_path,
                ["show", address],
                "bluetoothctl",
                warnings,
            )
            if output is not None:
                for line in output.splitlines():
                    match = re.match(r"^\s*Powered:\s*(yes|no)\s*$", line, re.IGNORECASE)
                    if match:
                        powered = match.group(1).lower() == "yes"
                        break
                if powered is None:
                    warnings.append(
                        "Could not determine power state for {}.".format(
                            controller_path.name
                        )
                    )

        controllers.append(
            BluetoothController(
                name=controller_path.name,
                driver=_driver_name(controller_path, warnings),
                powered=powered,
            )
        )
    return tuple(controllers)


def collect_wireless_bluetooth_info(
    net_class_path: Path = Path("/sys/class/net"),
    bluetooth_class_path: Path = Path("/sys/class/bluetooth"),
) -> WirelessBluetoothInfo:
    """Collect current Wi-Fi and Bluetooth status without scanning for devices."""
    warnings: List[str] = []
    iw_path = shutil.which("iw")
    nmcli_path = shutil.which("nmcli")
    bluetoothctl_path = shutil.which("bluetoothctl")
    rfkill_path = shutil.which("rfkill")

    wifi_interfaces = _read_wifi_interfaces(
        net_class_path, iw_path, nmcli_path, warnings
    )
    bluetooth_controllers = _read_bluetooth_controllers(
        bluetooth_class_path, bluetoothctl_path, warnings
    )

    rfkill_states: Tuple[Tuple[str, bool], ...] = ()
    if rfkill_path:
        output = _run_tool(rfkill_path, ["--json"], "rfkill", warnings)
        if output is not None:
            try:
                rfkill_states = _parse_rfkill_output(output)
            except (TypeError, ValueError) as error:
                warnings.append("Could not parse rfkill output: {}".format(error))

    return WirelessBluetoothInfo(
        wifi_interfaces=wifi_interfaces,
        bluetooth_controllers=bluetooth_controllers,
        rfkill_states=rfkill_states,
        warnings=tuple(warnings),
    )


def render_wireless_bluetooth_info(
    info: WirelessBluetoothInfo,
    language: str,
    environment: str,
) -> str:
    """Render wireless and Bluetooth values without exposing device addresses."""
    if language == "de":
        labels = {
            "wifi_section": "WLAN",
            "bluetooth_section": "Bluetooth",
            "no_wifi": "Keine WLAN-Schnittstelle gefunden.",
            "no_bluetooth": "Kein Bluetooth-Controller gefunden.",
            "driver": "Treiber",
            "state": "Schnittstellenstatus",
            "connected": "Verbindung",
            "connected_yes": "verbunden",
            "connected_no": "nicht verbunden",
            "unavailable": "Nicht verfügbar",
            "ssid": "Aktuelle SSID",
            "powered": "Stromversorgung",
            "powered_on": "eingeschaltet",
            "powered_off": "ausgeschaltet",
            "rfkill": "Funkblockierung",
            "blocked": "Mindestens ein Gerät blockiert",
            "unblocked": "Kein aufgeführtes Gerät blockiert",
            "wsl": (
                "WSL stellt Netzwerkgeräte möglicherweise nur virtuell bereit; "
                "diese Werte belegen keine Windows-WLAN- oder Bluetooth-Hardware."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "wifi_section": "Wi-Fi",
            "bluetooth_section": "Bluetooth",
            "no_wifi": "No Wi-Fi interface found.",
            "no_bluetooth": "No Bluetooth controller found.",
            "driver": "Driver",
            "state": "Interface state",
            "connected": "Connection",
            "connected_yes": "connected",
            "connected_no": "not connected",
            "unavailable": "Unavailable",
            "ssid": "Current SSID",
            "powered": "Power",
            "powered_on": "on",
            "powered_off": "off",
            "rfkill": "Radio block",
            "blocked": "At least one listed device is blocked",
            "unblocked": "No listed device is blocked",
            "wsl": (
                "WSL may expose network devices virtually; these values do not "
                "confirm Windows Wi-Fi or Bluetooth hardware."
            ),
            "warnings": "Warnings",
        }

    lines = ["=== {} ===".format(labels["wifi_section"])]
    if not info.wifi_interfaces:
        lines.append(labels["no_wifi"])
    for interface in info.wifi_interfaces:
        lines.append("{}:".format(interface.name))
        lines.append(
            "  {}: {}".format(
                labels["driver"], interface.driver or labels["unavailable"]
            )
        )
        lines.append(
            "  {}: {}".format(
                labels["state"], interface.state or labels["unavailable"]
            )
        )
        connection = (
            labels["connected_yes"]
            if interface.connected is True
            else labels["connected_no"]
            if interface.connected is False
            else labels["unavailable"]
        )
        lines.append("  {}: {}".format(labels["connected"], connection))
        if interface.connected is True:
            lines.append(
                "  {}: {}".format(
                    labels["ssid"], interface.ssid or labels["unavailable"]
                )
            )

    lines.append("=== {} ===".format(labels["bluetooth_section"]))
    if not info.bluetooth_controllers:
        lines.append(labels["no_bluetooth"])
    for controller in info.bluetooth_controllers:
        lines.append("{}:".format(controller.name))
        lines.append(
            "  {}: {}".format(
                labels["driver"], controller.driver or labels["unavailable"]
            )
        )
        powered = (
            labels["powered_on"]
            if controller.powered is True
            else labels["powered_off"]
            if controller.powered is False
            else labels["unavailable"]
        )
        lines.append("  {}: {}".format(labels["powered"], powered))

    for kind, blocked in info.rfkill_states:
        radio_name = (
            labels["wifi_section"]
            if kind == "wifi"
            else labels["bluetooth_section"]
        )
        block_state = labels["blocked"] if blocked else labels["unblocked"]
        lines.append("{} (rfkill): {}".format(radio_name, block_state))
    if environment.startswith("WSL"):
        lines.append("WSL: {}".format(labels["wsl"]))
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
