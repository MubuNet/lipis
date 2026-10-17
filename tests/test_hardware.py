import unittest
from collections import namedtuple
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.hardware import (
    HardwareInfo,
    collect_hardware_info,
    format_size,
    parse_cpu_info,
    parse_memory_info,
    render_hardware_info,
)


DiskUsage = namedtuple("DiskUsage", "total used free")


class HardwareCollectionTests(unittest.TestCase):
    def test_parses_x86_cpu_model_and_logical_cpu_count(self):
        cpu_model, logical_cpus = parse_cpu_info(
            "processor : 0\nmodel name : Example CPU\n\n"
            "processor : 1\nmodel name : Example CPU\n"
        )
        self.assertEqual(cpu_model, "Example CPU")
        self.assertEqual(logical_cpus, 2)

    def test_parses_arm_cpu_information(self):
        cpu_model, logical_cpus = parse_cpu_info(
            "Processor : ARMv8 Processor rev 1\nprocessor : 0\nprocessor : 1\n"
        )
        self.assertEqual(cpu_model, "ARMv8 Processor rev 1")
        self.assertEqual(logical_cpus, 2)

    def test_parses_memory_values_in_kibibytes(self):
        memory = parse_memory_info(
            "MemTotal:       16384 kB\nMemAvailable:    8192 kB\n"
        )
        self.assertEqual(memory["MemTotal"], 16 * 1024 * 1024)
        self.assertEqual(memory["MemAvailable"], 8 * 1024 * 1024)

    def test_collects_cpu_memory_and_disk_information(self):
        with TemporaryDirectory() as directory:
            cpu_info_path = Path(directory) / "cpuinfo"
            memory_info_path = Path(directory) / "meminfo"
            cpu_info_path.write_text(
                "processor : 0\nmodel name : Example CPU\nprocessor : 1\n",
                encoding="utf-8",
            )
            memory_info_path.write_text(
                "MemTotal: 16384 kB\nMemAvailable: 8192 kB\n",
                encoding="ascii",
            )
            with patch(
                "modules.hardware.shutil.disk_usage",
                return_value=DiskUsage(1000, 400, 600),
            ):
                info = collect_hardware_info(
                    cpu_info_path,
                    memory_info_path,
                    Path(directory),
                )

        self.assertEqual(info.cpu_model, "Example CPU")
        self.assertEqual(info.logical_cpus, 2)
        self.assertEqual(info.memory_total_bytes, 16 * 1024 * 1024)
        self.assertEqual(info.memory_available_bytes, 8 * 1024 * 1024)
        self.assertEqual(info.disk_total_bytes, 1000)
        self.assertEqual(info.disk_used_bytes, 400)
        self.assertEqual(info.disk_free_bytes, 600)
        self.assertEqual(info.warnings, ())

    def test_reports_unavailable_sources_without_failing(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with patch(
                "modules.hardware.shutil.disk_usage",
                side_effect=OSError("denied"),
            ):
                info = collect_hardware_info(missing, missing, missing)

        self.assertIsNone(info.cpu_model)
        self.assertIsNone(info.memory_total_bytes)
        self.assertIsNone(info.disk_total_bytes)
        self.assertEqual(len(info.warnings), 3)
        self.assertTrue(any("Could not read" in warning for warning in info.warnings))

    def test_formats_sizes_as_gibibytes(self):
        self.assertEqual(format_size(1024 ** 3), "1.0 GiB")

    def test_wsl_rendering_explains_virtualized_values(self):
        info = HardwareInfo(
            cpu_model="Example CPU",
            logical_cpus=4,
            memory_total_bytes=8 * 1024 ** 3,
            memory_available_bytes=4 * 1024 ** 3,
            disk_total_bytes=16 * 1024 ** 3,
            disk_used_bytes=8 * 1024 ** 3,
            disk_free_bytes=8 * 1024 ** 3,
            warnings=(),
        )
        output = render_hardware_info(info, "de", "WSL 2")
        self.assertIn("CPU-Modell: Example CPU", output)
        self.assertIn("Werte beziehen sich auf die WSL-Umgebung", output)


if __name__ == "__main__":
    unittest.main()
