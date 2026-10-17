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

> **Project status — `0.1.0-dev`:** The command-line entry point and the first OS/kernel diagnostic are implemented. The remaining diagnostic modules and report generator are still planned.

## Current Features

- Reads distribution details from `/etc/os-release` and uptime from `/proc/uptime`.
- Displays the kernel, architecture, uptime, and detects WSL/WSL 2.
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

- Seven read-only diagnostic areas: OS and kernel, hardware, GPU and drivers, wireless and Bluetooth, audio, network, and security.
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
│   └── os_info.py       # Implemented OS, kernel, and uptime diagnostics
└── outputs/             # Planned report generation
```

## License

Distributed under the **MIT License**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
