"""Read-only Linux network configuration diagnostics."""

import fcntl
import errno
import ipaddress
import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class NetworkInterface:
    """Address and link state for one Linux network interface."""

    name: str
    state: Optional[str]
    mac_address: Optional[str]
    ipv4_addresses: Tuple[str, ...]
    ipv6_addresses: Tuple[str, ...]


@dataclass(frozen=True)
class NetworkInfo:
    """Collected local network configuration without active probing."""

    interfaces: Tuple[NetworkInterface, ...]
    gateways: Tuple[Tuple[str, str], ...]
    dns_servers: Tuple[str, ...]
    warnings: Tuple[str, ...]


def _read_ipv4_addresses(
    interface_name: str, ioctl_socket: socket.socket, warnings: List[str]
) -> Tuple[str, ...]:
    """Read an interface's IPv4 address through a local kernel ioctl."""
    request = struct.pack("256s", interface_name.encode("utf-8")[:15])
    try:
        response = fcntl.ioctl(ioctl_socket.fileno(), 0x8915, request)
    except OSError as error:
        if error.errno not in (errno.EADDRNOTAVAIL, errno.ENODEV, errno.EAFNOSUPPORT):
            warnings.append(
                "Could not read IPv4 address for {}: {}".format(interface_name, error)
            )
        return ()
    return (socket.inet_ntoa(response[20:24]),)


def _read_ipv6_addresses(
    path: Path, warnings: List[str]
) -> Dict[str, Tuple[str, ...]]:
    """Read interface-indexed IPv6 addresses from procfs."""
    addresses = {}
    try:
        contents = path.read_text(encoding="ascii")
    except FileNotFoundError:
        return {}
    except OSError as error:
        warnings.append("Could not read {}: {}".format(path, error))
        return {}

    for line in contents.splitlines():
        fields = line.split()
        if len(fields) != 6:
            warnings.append("Could not parse IPv6 address entry in {}.".format(path))
            continue
        address_hex, _index, prefix_hex, _scope, _flags, interface_name = fields
        try:
            address = ipaddress.IPv6Address(bytes.fromhex(address_hex))
            prefix_length = int(prefix_hex, 16)
        except (ValueError, ipaddress.AddressValueError) as error:
            warnings.append("Could not parse IPv6 address in {}: {}".format(path, error))
            continue
        addresses.setdefault(interface_name, []).append(
            "{}/{}".format(address, prefix_length)
        )
    return {name: tuple(values) for name, values in addresses.items()}


def _read_gateways(
    ipv4_route_path: Path,
    ipv6_route_path: Path,
    warnings: List[str],
) -> Tuple[Tuple[str, str], ...]:
    """Read default IPv4 and IPv6 gateways from procfs routing tables."""
    gateways = []
    try:
        ipv4_contents = ipv4_route_path.read_text(encoding="ascii")
    except FileNotFoundError:
        ipv4_contents = ""
    except OSError as error:
        warnings.append("Could not read {}: {}".format(ipv4_route_path, error))
        ipv4_contents = ""

    for line in ipv4_contents.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            gateway = socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
        except (OSError, ValueError, struct.error) as error:
            warnings.append("Could not parse IPv4 gateway: {}".format(error))
            continue
        if flags & 1 and gateway != "0.0.0.0":
            gateways.append((fields[0], gateway))

    try:
        ipv6_contents = ipv6_route_path.read_text(encoding="ascii")
    except FileNotFoundError:
        ipv6_contents = ""
    except OSError as error:
        warnings.append("Could not read {}: {}".format(ipv6_route_path, error))
        ipv6_contents = ""

    for line in ipv6_contents.splitlines():
        fields = line.split()
        if len(fields) < 10 or fields[0] != "0" * 32 or fields[1] != "00":
            continue
        try:
            gateway_address = ipaddress.IPv6Address(bytes.fromhex(fields[4]))
            flags = int(fields[8], 16)
        except (ValueError, ipaddress.AddressValueError) as error:
            warnings.append("Could not parse IPv6 gateway: {}".format(error))
            continue
        if flags & 1 and not gateway_address.is_unspecified:
            gateways.append((fields[9], str(gateway_address)))
    return tuple(gateways)


def _read_dns_servers(path: Path, warnings: List[str]) -> Tuple[str, ...]:
    """Read DNS nameserver addresses from resolv.conf without retaining search domains."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        warnings.append("Could not read {}: {}".format(path, error))
        return ()

    servers = []
    for line in contents.splitlines():
        fields = line.split("#", 1)[0].split()
        if len(fields) < 2 or fields[0] != "nameserver":
            continue
        try:
            address = str(ipaddress.ip_address(fields[1]))
        except ValueError as error:
            warnings.append("Could not parse DNS server in {}: {}".format(path, error))
            continue
        if address not in servers:
            servers.append(address)
    return tuple(servers)


def collect_network_info(
    net_class_path: Path = Path("/sys/class/net"),
    ipv6_addresses_path: Path = Path("/proc/net/if_inet6"),
    ipv4_routes_path: Path = Path("/proc/net/route"),
    ipv6_routes_path: Path = Path("/proc/net/ipv6_route"),
    resolv_conf_path: Path = Path("/etc/resolv.conf"),
) -> NetworkInfo:
    """Collect interface addresses, default gateways, and DNS without probing."""
    warnings: List[str] = []
    try:
        interface_paths = tuple(sorted(net_class_path.iterdir()))
    except OSError as error:
        interface_paths = ()
        warnings.append("Could not list network interfaces in {}: {}".format(
            net_class_path, error
        ))
    ipv6_by_interface = _read_ipv6_addresses(ipv6_addresses_path, warnings)

    interfaces = []
    try:
        ioctl_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError as error:
        ioctl_socket = None
        warnings.append("Could not open a local network control socket: {}".format(error))

    try:
        for interface_path in interface_paths:
            try:
                state = (interface_path / "operstate").read_text(
                    encoding="ascii"
                ).strip()
            except OSError as error:
                state = None
                warnings.append(
                    "Could not read state for {}: {}".format(interface_path.name, error)
                )
            try:
                mac_address = (interface_path / "address").read_text(
                    encoding="ascii"
                ).strip()
            except OSError as error:
                mac_address = None
                warnings.append(
                    "Could not read MAC address for {}: {}".format(
                        interface_path.name, error
                    )
                )
            ipv4_addresses = (
                _read_ipv4_addresses(interface_path.name, ioctl_socket, warnings)
                if ioctl_socket is not None
                else ()
            )
            interfaces.append(
                NetworkInterface(
                    name=interface_path.name,
                    state=state,
                    mac_address=mac_address,
                    ipv4_addresses=ipv4_addresses,
                    ipv6_addresses=ipv6_by_interface.get(interface_path.name, ()),
                )
            )
    finally:
        if ioctl_socket is not None:
            ioctl_socket.close()

    return NetworkInfo(
        interfaces=tuple(interfaces),
        gateways=_read_gateways(ipv4_routes_path, ipv6_routes_path, warnings),
        dns_servers=_read_dns_servers(resolv_conf_path, warnings),
        warnings=tuple(warnings),
    )


def render_network_info(
    info: NetworkInfo,
    language: str,
    environment: str,
) -> str:
    """Render local network details for terminal diagnostics."""
    if language == "de":
        labels = {
            "section": "Netzwerk",
            "no_interfaces": "Keine Netzwerkschnittstelle gefunden.",
            "state": "Status",
            "mac": "MAC-Adresse",
            "ipv4": "IPv4-Adressen",
            "ipv6": "IPv6-Adressen",
            "unavailable": "Nicht verfügbar",
            "gateways": "Standard-Gateways",
            "dns": "DNS-Server",
            "none": "Keine ermittelt",
            "wsl": (
                "Netzwerkangaben beschreiben die virtuelle Linux-Sicht unter WSL "
                "und weisen keine Windows-Adapter aus."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "Network",
            "no_interfaces": "No network interfaces found.",
            "state": "State",
            "mac": "MAC address",
            "ipv4": "IPv4 addresses",
            "ipv6": "IPv6 addresses",
            "unavailable": "Unavailable",
            "gateways": "Default gateways",
            "dns": "DNS servers",
            "none": "None identified",
            "wsl": (
                "Network values describe the virtual Linux view under WSL and "
                "do not identify Windows adapters."
            ),
            "warnings": "Warnings",
        }

    lines = ["=== {} ===".format(labels["section"])]
    if not info.interfaces:
        lines.append(labels["no_interfaces"])
    for interface in info.interfaces:
        lines.append("{}:".format(interface.name))
        lines.append(
            "  {}: {}".format(labels["state"], interface.state or labels["unavailable"])
        )
        lines.append(
            "  {}: {}".format(
                labels["mac"], interface.mac_address or labels["unavailable"]
            )
        )
        lines.append(
            "  {}: {}".format(
                labels["ipv4"],
                ", ".join(interface.ipv4_addresses) or labels["none"],
            )
        )
        lines.append(
            "  {}: {}".format(
                labels["ipv6"],
                ", ".join(interface.ipv6_addresses) or labels["none"],
            )
        )

    lines.append("{}:".format(labels["gateways"]))
    if info.gateways:
        lines.extend("  {}: {}".format(name, address) for name, address in info.gateways)
    else:
        lines.append("  {}".format(labels["none"]))

    lines.append("{}: {}".format(
        labels["dns"], ", ".join(info.dns_servers) or labels["none"]
    ))
    if environment.startswith("WSL"):
        lines.append("WSL: {}".format(labels["wsl"]))
    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
