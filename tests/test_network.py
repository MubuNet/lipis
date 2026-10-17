import errno
import socket
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.network import (
    NetworkInfo,
    NetworkInterface,
    _read_dns_servers,
    _read_gateways,
    _read_ipv6_addresses,
    collect_network_info,
    render_network_info,
)


class NetworkCollectionTests(unittest.TestCase):
    def test_reads_interface_status_mac_and_ipv4_address(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            interface = root / "net" / "eth0"
            interface.mkdir(parents=True)
            (interface / "operstate").write_text("up\n", encoding="ascii")
            (interface / "address").write_text(
                "02:11:22:33:44:55\n", encoding="ascii"
            )
            ipv6_path = root / "if_inet6"
            ipv6_path.write_text("", encoding="ascii")
            routes_path = root / "route"
            routes_path.write_text("Iface Destination Gateway Flags\n", encoding="ascii")
            ipv6_routes_path = root / "ipv6_route"
            ipv6_routes_path.write_text("", encoding="ascii")
            resolv_path = root / "resolv.conf"
            resolv_path.write_text("nameserver 192.0.2.53\n", encoding="ascii")

            def ioctl(_fd, _request, request_data):
                self.assertEqual(request_data[:5], b"eth0\x00")
                return b"\x00" * 20 + socket.inet_aton("192.0.2.10") + b"\x00" * 232

            with patch("modules.network.fcntl.ioctl", side_effect=ioctl):
                info = collect_network_info(
                    root / "net",
                    ipv6_path,
                    routes_path,
                    ipv6_routes_path,
                    resolv_path,
                )

        self.assertEqual(
            info.interfaces,
            (
                NetworkInterface(
                    "eth0",
                    "up",
                    "02:11:22:33:44:55",
                    ("192.0.2.10",),
                    (),
                ),
            ),
        )
        self.assertEqual(info.dns_servers, ("192.0.2.53",))

    def test_skips_interfaces_without_ipv4_addresses(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            interface = root / "net" / "lo"
            interface.mkdir(parents=True)
            (interface / "operstate").write_text("unknown\n", encoding="ascii")
            (interface / "address").write_text("00:00:00:00:00:00\n", encoding="ascii")
            route = root / "route"
            route.write_text("Iface Destination Gateway Flags\n", encoding="ascii")
            (root / "ipv6_route").write_text("", encoding="ascii")
            (root / "resolv.conf").write_text("", encoding="ascii")

            with patch(
                "modules.network.fcntl.ioctl",
                side_effect=OSError(errno.EADDRNOTAVAIL, "no address"),
            ):
                info = collect_network_info(
                    root / "net",
                    root / "if_inet6",
                    route,
                    root / "ipv6_route",
                    root / "resolv.conf",
                )

        self.assertEqual(len(info.interfaces), 1)
        self.assertEqual(info.interfaces[0].ipv4_addresses, ())
        self.assertEqual(info.warnings, ())

    def test_reports_unexpected_ipv4_ioctl_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            interface = root / "net" / "eth0"
            interface.mkdir(parents=True)
            (interface / "operstate").write_text("up\n", encoding="ascii")
            (interface / "address").write_text("02:00:00:00:00:01\n", encoding="ascii")
            route = root / "route"
            route.write_text("Iface Destination Gateway Flags\n", encoding="ascii")
            (root / "ipv6_route").write_text("", encoding="ascii")
            (root / "resolv.conf").write_text("", encoding="ascii")

            with patch(
                "modules.network.fcntl.ioctl",
                side_effect=OSError(errno.EPERM, "denied"),
            ):
                info = collect_network_info(
                    root / "net",
                    root / "if_inet6",
                    route,
                    root / "ipv6_route",
                    root / "resolv.conf",
                )

        self.assertTrue(
            any("Could not read IPv4 address" in item for item in info.warnings)
        )

    def test_reads_ipv6_addresses_by_interface(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "if_inet6"
            path.write_text(
                "20010db8000000000000000000000001 02 40 00 00 eth0\n",
                encoding="ascii",
            )
            addresses = _read_ipv6_addresses(path, [])

        self.assertEqual(addresses, {"eth0": ("2001:db8::1/64",)})

    def test_reads_ipv4_and_ipv6_default_gateways(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ipv4 = root / "route"
            ipv4.write_text(
                "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
                "eth0 00000000 0102A8C0 0003 0 0 100 00000000\n",
                encoding="ascii",
            )
            ipv6 = root / "ipv6_route"
            ipv6.write_text(
                "0" * 32
                + " 00 "
                + "0" * 32
                + " 00 "
                + "fe8000000000000002155dfffe875505"
                + " 00000000 00000000 00000000 00000001 eth0\n",
                encoding="ascii",
            )
            gateways = _read_gateways(ipv4, ipv6, [])

        self.assertEqual(
            gateways,
            (
                ("eth0", "192.168.2.1"),
                ("eth0", "fe80::215:5dff:fe87:5505"),
            ),
        )

    def test_reads_only_dns_nameserver_addresses(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resolv.conf"
            path.write_text(
                "# generated config\n"
                "search private.example\n"
                "nameserver 10.0.0.1\n"
                "nameserver 2001:db8::53\n"
                "nameserver 10.0.0.1 # duplicate\n",
                encoding="ascii",
            )
            servers = _read_dns_servers(path, [])

        self.assertEqual(servers, ("10.0.0.1", "2001:db8::53"))

    def test_reports_invalid_dns_server(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resolv.conf"
            path.write_text("nameserver invalid-address\n", encoding="ascii")
            warnings = []
            servers = _read_dns_servers(path, warnings)

        self.assertEqual(servers, ())
        self.assertTrue(any("Could not parse DNS server" in item for item in warnings))


class NetworkPresentationTests(unittest.TestCase):
    def test_renders_wsl_network_values_in_both_languages(self):
        info = NetworkInfo(
            interfaces=(
                NetworkInterface(
                    "eth0",
                    "up",
                    "02:11:22:33:44:55",
                    ("172.20.232.132/20",),
                    ("fe80::215:5dff:fe87:5505/64",),
                ),
            ),
            gateways=(("eth0", "172.20.224.1"),),
            dns_servers=("10.255.255.254",),
            warnings=(),
        )

        english = render_network_info(info, "en", "WSL 2")
        german = render_network_info(info, "de", "WSL 2")
        self.assertIn("MAC address: 02:11:22:33:44:55", english)
        self.assertIn("172.20.232.132/20", english)
        self.assertIn("172.20.224.1", english)
        self.assertIn("10.255.255.254", english)
        self.assertIn("do not identify Windows adapters", english)
        self.assertIn("MAC-Adresse: 02:11:22:33:44:55", german)
        self.assertIn("weisen keine Windows-Adapter aus", german)

    def test_reports_no_network_interface(self):
        output = render_network_info(NetworkInfo((), (), (), ()), "en", "Linux")
        self.assertIn("No network interfaces found.", output)
        self.assertIn("Default gateways:", output)
        self.assertIn("DNS servers: None identified", output)


if __name__ == "__main__":
    unittest.main()
