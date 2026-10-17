import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.gpu_driver import (
    GpuDevice,
    GpuInfo,
    collect_gpu_info,
    parse_lspci_output,
    parse_nvidia_smi_output,
    read_sysfs_gpus,
    render_gpu_info,
)


class GpuParsingTests(unittest.TestCase):
    def test_parses_multiple_vendors_and_active_drivers_from_lspci(self):
        output = (
            "0000:00:02.0 VGA compatible controller [0300]: "
            "Intel Corporation UHD Graphics 630 [8086:3e92] (rev 02)\n"
            "\tSubsystem: Example Device\n"
            "\tKernel driver in use: i915\n"
            "0000:01:00.0 3D controller [0302]: "
            "NVIDIA Corporation Example GPU [10de:2684] (rev a1)\n"
            "\tKernel modules: nouveau, nvidia_drm, nvidia\n"
            "0000:02:00.0 Display controller [0380]: "
            "Advanced Micro Devices, Inc. Example GPU [1002:73bf]\n"
            "\tKernel driver in use: amdgpu\n"
            "0000:03:00.0 Network controller [0280]: Example Wi-Fi [1234:5678]\n"
        )

        devices = parse_lspci_output(output)

        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0].name, "Intel Corporation UHD Graphics 630")
        self.assertEqual(devices[0].vendor, "Intel")
        self.assertEqual(devices[0].driver, "i915")
        self.assertEqual(devices[1].vendor, "NVIDIA")
        self.assertIsNone(devices[1].driver)
        self.assertEqual(devices[2].vendor, "AMD")
        self.assertEqual(devices[2].driver, "amdgpu")

    def test_parses_nvidia_model_and_driver_version(self):
        devices = parse_nvidia_smi_output(
            "GeForce RTX Example, 555.42.02\n"
            "Example GPU, 555.42.02\n"
        )
        self.assertEqual(
            devices,
            (
                ("GeForce RTX Example", "555.42.02"),
                ("Example GPU", "555.42.02"),
            ),
        )

    def test_reads_gpu_identity_and_driver_from_sysfs(self):
        with TemporaryDirectory() as directory:
            pci_path = Path(directory) / "0000:00:02.0"
            pci_path.mkdir()
            (pci_path / "class").write_text("0x030000\n", encoding="ascii")
            (pci_path / "vendor").write_text("0x8086\n", encoding="ascii")
            (pci_path / "device").write_text("0x1234\n", encoding="ascii")
            with patch(
                "modules.gpu_driver.Path.resolve",
                return_value=Path("/sys/bus/pci/drivers/i915"),
            ):
                devices = read_sysfs_gpus(Path(directory))

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].vendor, "Intel")
        self.assertEqual(devices[0].pci_id, "8086:1234")
        self.assertEqual(devices[0].driver, "i915")

    def test_skips_non_graphics_pci_devices(self):
        with TemporaryDirectory() as directory:
            pci_path = Path(directory) / "0000:00:01.0"
            pci_path.mkdir()
            (pci_path / "class").write_text("0x020000\n", encoding="ascii")
            (pci_path / "vendor").write_text("0x8086\n", encoding="ascii")
            (pci_path / "device").write_text("0x1234\n", encoding="ascii")

            devices = read_sysfs_gpus(Path(directory))

        self.assertEqual(devices, ())


class GpuCollectionTests(unittest.TestCase):
    def test_uses_nvidia_smi_only_when_available_and_records_version(self):
        completed = CompletedProcess(
            args=["nvidia-smi"],
            returncode=0,
            stdout="GeForce RTX Example, 555.42.02\n",
            stderr="",
        )
        with TemporaryDirectory() as directory:
            with patch(
                "modules.gpu_driver.shutil.which",
                side_effect=lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None,
            ), patch("modules.gpu_driver.subprocess.run", return_value=completed) as run:
                info = collect_gpu_info(
                    Path(directory),
                    Path("/path/without/dxg"),
                )

        self.assertEqual(
            info.devices,
            (
                GpuDevice(
                    "GeForce RTX Example",
                    "NVIDIA",
                    None,
                    "nvidia",
                    "555.42.02",
                ),
            ),
        )
        run.assert_called_once()
        self.assertEqual(info.warnings, ())

    def test_reports_optional_tool_failure(self):
        completed = CompletedProcess(
            args=["lspci"],
            returncode=1,
            stdout="",
            stderr="permission issue",
        )
        with patch(
            "modules.gpu_driver.shutil.which",
            side_effect=lambda name: "/usr/bin/lspci" if name == "lspci" else None,
        ), patch("modules.gpu_driver.subprocess.run", return_value=completed):
            info = collect_gpu_info(
                Path("/path/without/pci/devices"),
                Path("/path/without/dxg"),
            )

        self.assertTrue(any("lspci exited with status 1" in item for item in info.warnings))

    def test_reports_sysfs_access_failure(self):
        with TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing-pci"
            with patch("modules.gpu_driver.shutil.which", return_value=None):
                info = collect_gpu_info(missing_path, Path("/path/without/dxg"))

        self.assertTrue(
            any("Could not read PCI devices" in warning for warning in info.warnings)
        )
        with self.assertRaises(OSError):
            read_sysfs_gpus(missing_path)

    def test_detects_wsl_gpu_interface_without_claiming_host_model(self):
        with TemporaryDirectory() as directory:
            dxg_path = Path(directory) / "dxg"
            dxg_path.touch()
            with patch("modules.gpu_driver.shutil.which", return_value=None):
                info = collect_gpu_info(Path(directory) / "missing-pci", dxg_path)

        self.assertTrue(info.wsl_gpu_interface)
        self.assertEqual(info.devices, ())
        output = render_gpu_info(info, "en", "WSL 2")
        self.assertIn("WSL GPU interface is available", output)
        self.assertIn("does not confirm the exact host GPU model", output)

    def test_renders_each_gpu_and_active_driver_in_german(self):
        info = GpuInfo(
            devices=(
                GpuDevice("Example GPU", "AMD", "1002:73bf", "amdgpu", None),
            ),
            wsl_gpu_interface=False,
            warnings=(),
        )
        output = render_gpu_info(info, "de", "Linux")

        self.assertIn("GPU und Treiber", output)
        self.assertIn("Aktiver Treiber: amdgpu", output)
        self.assertNotIn("Treiberversion", output)


if __name__ == "__main__":
    unittest.main()
