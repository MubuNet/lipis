**English** | [Deutsch](README.de.md)

# LIPIS - Linux PostInstall Script

```text
  _     ___ ____ ___ ____
 | |   |_ _|  _ \_ _/ ___|
 | |    | | | _) | |\___ \
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/
```

**LIPIS** (Linux PostInstall Script) is a read-only diagnostic tool in development for Ubuntu and Debian newcomers.

> **Project status — `0.1.0-dev`:** The command-line entry point and the OS/kernel, basic hardware, GPU/driver, and Wi-Fi/Bluetooth diagnostics are implemented. The remaining diagnostic modules and report generator are still planned.

## Current Features

- Reads distribution details from `/etc/os-release` and uptime from `/proc/uptime`.
- Displays the kernel, architecture, uptime, and detects WSL/WSL 2.
- Reports CPU model and logical CPU count, available/total memory, and used/free space for both Linux root (`/`) and the filesystem containing the current working directory.
- Labels WSL hardware and filesystem figures as values reported by the WSL environment. When run from `/mnt/c`, the current-directory filesystem shows the mounted Windows `C:` volume separately from WSL's Linux root filesystem.
- Detects NVIDIA, AMD, and Intel graphics devices from PCI system information, reports the active kernel driver when identifiable, and uses `nvidia-smi` only when already installed.
- Clearly labels WSL GPU information and does not infer the host GPU model from the WSL GPU interface alone.
- Reports Wi-Fi interfaces, driver, interface/connection status, and only the SSID of the current connection. It does not scan for nearby networks.
- Reports Bluetooth controllers, drivers, and power status without scanning for or listing paired devices.
- Uses sysfs and optional preinstalled tools (`iw`, `nmcli`, `rfkill`, and `bluetoothctl`) for wireless diagnostics; it does not install software or require root access. WSL limitations are clearly identified.
- Automatically selects English or German from the system locale; use `--language en` or `--language de` to override it. Other locales fall back to English.
- Uses only the Python standard library. No root privileges or system package installations are required.

## Run LIPIS

Requirements: Python 3.8 or higher on Linux (Ubuntu/Debian recommended).

```bash
git clone https://github.com/mubunet/lipis.git
cd lipis
python3 main.py
```

Use `python3 main.py --help` to see the available options.

`python3 main.py --version` (or `-v`) displays the development version.

## Planned Features

- Remaining read-only diagnostic areas: audio, network, and security.
- A live terminal display with the MubuNet banner.
- An optional Markdown report named `lipis_report.md`, saved in the directory from which LIPIS is started. Hostname, username, and local IP addresses will be omitted from the report by default.
- Optional presentation dependencies with a standard-library fallback.
- Later OS-specific profiles, including clearly separated Kali-only diagnostics.

## Project Structure

```text
lipis/
├── main.py              # CLI entry point
├── README.md            # English documentation
├── README.de.md         # German documentation
├── modules/
│   ├── os_info.py       # OS, kernel, and uptime diagnostics
│   ├── hardware.py      # CPU, memory, and filesystem diagnostics
│   ├── gpu_driver.py    # GPU and active driver diagnostics
│   └── wireless_bluetooth.py # Wi-Fi and Bluetooth diagnostics
└── outputs/             # Planned report generation
```

## License

Distributed under the **MIT License**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
