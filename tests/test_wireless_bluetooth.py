import json
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.wireless_bluetooth import (
    BluetoothController,
    WifiInterface,
    WirelessBluetoothInfo,
    _parse_iw_link,
    _parse_rfkill_output,
    collect_wireless_bluetooth_info,
    render_wireless_bluetooth_info,
)


class WirelessBluetoothParsingTests(unittest.TestCase):
    def test_parses_current_iw_connection_without_retaining_bssid(self):
        connected, ssid = _parse_iw_link(
            "Connected to 00:11:22:33:44:55 (on wlan0)\n"
            "\tSSID: Example Wi-Fi\n"
            "\tfreq: 5180\n"
        )
        self.assertTrue(connected)
        self.assertEqual(ssid, "Example Wi-Fi")

    def test_reports_disconnected_iw_interface(self):
        self.assertEqual(_parse_iw_link("Not connected.\n"), (False, None))

    def test_removes_terminal_control_characters_from_ssid(self):
        connected, ssid = _parse_iw_link(
            "Connected to 00:11:22:33:44:55 (on wlan0)\n"
            "\tSSID: Cafe\x1b[31m\n"
        )
        self.assertTrue(connected)
        self.assertEqual(ssid, "Cafe[31m")

    def test_parses_rfkill_block_state_by_radio_type(self):
        output = json.dumps(
            {
                "rfkilldevices": [
                    {"type": "wlan", "soft": False, "hard": False},
                    {"type": "bluetooth", "soft": True, "hard": False},
                    {"type": "wlan", "soft": False, "hard": True},
                ]
            }
        )
        self.assertEqual(
            _parse_rfkill_output(output),
            (("wifi", True), ("bluetooth", True)),
        )

    def test_rejects_malformed_rfkill_state(self):
        with self.assertRaises(ValueError):
            _parse_rfkill_output('{"rfkilldevices":[{"type":"wlan","soft":"no"}]}')
        with self.assertRaises(ValueError):
            _parse_rfkill_output("[]")


class WirelessBluetoothCollectionTests(unittest.TestCase):
    def _make_wifi_interface(self, net_path):
        interface_path = net_path / "wlan0"
        (interface_path / "wireless").mkdir(parents=True)
        (interface_path / "operstate").write_text("up\n", encoding="ascii")
        (interface_path / "device").mkdir()
        return interface_path

    def test_reads_wifi_interface_and_driver_from_sysfs(self):
        with TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            self._make_wifi_interface(net_path)
            with patch("modules.wireless_bluetooth.shutil.which", return_value=None), patch(
                "modules.wireless_bluetooth.Path.resolve",
                return_value=Path("/sys/bus/pci/drivers/iwlwifi"),
            ):
                info = collect_wireless_bluetooth_info(net_path, Path(directory) / "bt")

        self.assertEqual(
            info.wifi_interfaces,
            (WifiInterface("wlan0", "iwlwifi", "up", None, None),),
        )
        self.assertEqual(info.bluetooth_controllers, ())
        self.assertEqual(info.warnings, ())

    def test_reads_only_the_active_ssid_using_iw(self):
        with TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            self._make_wifi_interface(net_path)
            completed = CompletedProcess(
                args=["iw"],
                returncode=0,
                stdout=(
                    "Connected to 00:11:22:33:44:55 (on wlan0)\n"
                    "\tSSID: Current Network\n"
                    "\tfreq: 2412\n"
                ),
                stderr="",
            )
            with patch(
                "modules.wireless_bluetooth.shutil.which",
                side_effect=lambda name: "/usr/bin/iw" if name == "iw" else None,
            ), patch(
                "modules.wireless_bluetooth.subprocess.run",
                return_value=completed,
            ) as run:
                info = collect_wireless_bluetooth_info(
                    net_path, Path(directory) / "bt"
                )

        self.assertTrue(info.wifi_interfaces[0].connected)
        self.assertEqual(info.wifi_interfaces[0].ssid, "Current Network")
        run.assert_called_once_with(
            ["/usr/bin/iw", "dev", "wlan0", "link"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        rendered = render_wireless_bluetooth_info(info, "en", "Linux")
        self.assertIn("Current SSID: Current Network", rendered)
        self.assertNotIn("00:11:22:33:44:55", rendered)

    def test_uses_nmcli_profile_without_scanning_when_iw_is_missing(self):
        with TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            self._make_wifi_interface(net_path)

            def run_command(arguments, **_kwargs):
                if "GENERAL.CON-UUID" in arguments:
                    return CompletedProcess(arguments, 0, "profile-uuid\n", "")
                return CompletedProcess(arguments, 0, "Current Network\n", "")

            with patch(
                "modules.wireless_bluetooth.shutil.which",
                side_effect=lambda name: "/usr/bin/nmcli" if name == "nmcli" else None,
            ), patch(
                "modules.wireless_bluetooth.subprocess.run",
                side_effect=run_command,
            ) as run:
                info = collect_wireless_bluetooth_info(
                    net_path, Path(directory) / "bt"
                )

        self.assertTrue(info.wifi_interfaces[0].connected)
        self.assertEqual(info.wifi_interfaces[0].ssid, "Current Network")
        self.assertEqual(run.call_count, 2)
        self.assertTrue(
            all(
                "scan" not in " ".join(invocation.args[0]).lower()
                for invocation in run.call_args_list
            )
        )

    def test_reports_iw_command_failure(self):
        with TemporaryDirectory() as directory:
            net_path = Path(directory) / "net"
            self._make_wifi_interface(net_path)
            completed = CompletedProcess(["iw"], 1, "", "")
            with patch(
                "modules.wireless_bluetooth.shutil.which",
                side_effect=lambda name: "/usr/bin/iw" if name == "iw" else None,
            ), patch(
                "modules.wireless_bluetooth.subprocess.run",
                return_value=completed,
            ):
                info = collect_wireless_bluetooth_info(
                    net_path, Path(directory) / "bt"
                )

        self.assertTrue(any("iw exited with status 1" in item for item in info.warnings))

    def test_reads_bluetooth_power_state_without_exposing_names_or_addresses(self):
        with TemporaryDirectory() as directory:
            bluetooth_path = Path(directory) / "bluetooth"
            controller_path = bluetooth_path / "hci0"
            controller_path.mkdir(parents=True)
            (controller_path / "address").write_text(
                "00:11:22:33:44:55\n", encoding="ascii"
            )
            completed = CompletedProcess(
                args=["bluetoothctl"],
                returncode=0,
                stdout=(
                    "Controller 00:11:22:33:44:55 Local Adapter [default]\n"
                    "\tName: Local Adapter\n"
                    "\tPowered: yes\n"
                ),
                stderr="",
            )
            with patch(
                "modules.wireless_bluetooth.shutil.which",
                side_effect=lambda name: (
                    "/usr/bin/bluetoothctl" if name == "bluetoothctl" else None
                ),
            ), patch(
                "modules.wireless_bluetooth.subprocess.run",
                return_value=completed,
            ) as run:
                info = collect_wireless_bluetooth_info(
                    Path(directory) / "net", bluetooth_path
                )

        self.assertEqual(
            info.bluetooth_controllers,
            (BluetoothController("hci0", None, True),),
        )
        self.assertEqual(run.call_args.args[0][-2:], ["show", "00:11:22:33:44:55"])
        rendered = render_wireless_bluetooth_info(info, "en", "Linux")
        self.assertIn("hci0", rendered)
        self.assertNotIn("Local Adapter", rendered)
        self.assertNotIn("00:11:22:33:44:55", rendered)

    def test_reports_rfkill_errors(self):
        completed = CompletedProcess(["rfkill"], 1, "", "")
        with patch(
            "modules.wireless_bluetooth.shutil.which",
            side_effect=lambda name: "/usr/bin/rfkill" if name == "rfkill" else None,
        ), patch(
            "modules.wireless_bluetooth.subprocess.run",
            return_value=completed,
        ):
            info = collect_wireless_bluetooth_info(
                Path("/sys/class/net"), Path("/sys/class/bluetooth")
            )

        self.assertTrue(
            any("rfkill exited with status 1" in item for item in info.warnings)
        )


class WirelessBluetoothPresentationTests(unittest.TestCase):
    def test_renders_wsl_limitations_in_both_languages(self):
        info = WirelessBluetoothInfo((), (), (), ())
        english = render_wireless_bluetooth_info(info, "en", "WSL 2")
        german = render_wireless_bluetooth_info(info, "de", "WSL 2")
        self.assertIn("do not confirm Windows Wi-Fi or Bluetooth hardware", english)
        self.assertIn(
            "keine Windows-WLAN- oder Bluetooth-Hardware", german
        )

    def test_renders_interface_status_and_wifi_radio_block(self):
        info = WirelessBluetoothInfo(
            wifi_interfaces=(
                WifiInterface("wlan0", "iwlwifi", "up", False, None),
            ),
            bluetooth_controllers=(
                BluetoothController("hci0", "btusb", False),
            ),
            rfkill_states=(("wifi", True),),
            warnings=(),
        )
        output = render_wireless_bluetooth_info(info, "de", "Linux")
        self.assertIn("Verbindung: nicht verbunden", output)
        self.assertIn("Treiber: btusb", output)
        self.assertIn("Stromversorgung: ausgeschaltet", output)
        self.assertIn("Mindestens ein Gerät blockiert", output)


if __name__ == "__main__":
    unittest.main()
