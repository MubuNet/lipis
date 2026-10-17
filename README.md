**English** | [Deutsch](README.de.md)

# LIPIS - Linux PostInstall Script

```text
  _     ___ ____ ___ ____
 | |   |_ _|  _ \_ _/ ___|
 | |    | | | _) | |\___ \
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/
```

**LIPIS** (Linux PostInstall Script) is planned as a **100% passive, read-only diagnostic tool** for Ubuntu/Debian newcomers. Its intended purpose is to check system health, hardware details, network configuration, and service states, then generate a clear, actionable report—without modifying the system or requiring `sudo` privileges.

> **Project status:** LIPIS is still being planned. The script and the files described below do not exist yet, so the example commands are not usable at this time.

## 🛡️ Planned Core Principles

- **100% Read-Only:** No system modifications, package installations, or APT changes.
- **No Root / `sudo` Required:** Designed to run safely in user space.
- **Non-Interactive:** The planned command-line interface will run without prompting for input.
- **Local & Private:** The planned report will be written to `./lipis_report.md` in the current directory.

## 🚀 Planned Quick Start

### Requirements

- Python 3.8 or higher
- A standard Linux utility environment (Ubuntu/Debian recommended)

### Intended Usage

Once implemented, the planned entry point and report options are intended to work like this:

```bash
git clone https://github.com/mubunet/lipis.git
cd lipis
python3 main.py
```

### Planned CLI Flags

- `python3 main.py --report` (`-r`): Generate the Markdown diagnostic report at `./lipis_report.md`.
- `python3 main.py --version` (`-v`): Display LIPIS version information.

## 📂 Planned Project Structure

```text
lipis/
├── main.py              # Planned command-line entry point
├── README.md            # Project documentation
├── LICENSE              # MIT License
├── modules/             # Planned read-only diagnostic modules
│   ├── os_info.py       # OS distribution, kernel, and uptime
│   ├── hardware.py      # CPU, RAM, disk usage, and metrics
│   ├── network.py       # Interfaces, IP configuration, and DNS
│   └── services.py      # Systemd services and active processes
└── outputs/             # Planned report generation and formatting
```

## 📄 License

Distributed under the **MIT License**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
