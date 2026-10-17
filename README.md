# LIPIS - Linux PostInstall Script

```text
  _     ___ ____ ___ ____  
 | |   |_ _|  _ \_ _/ ___| 
 | |    | | | _) | |\___ \ 
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/ 
LIPIS (Linux PostInstall Script) is a 100% passive, read-only diagnostic tool designed for Ubuntu/Debian newcomers. It scans system health, hardware details, network configuration, and service states to generate a clean, actionable report—without making any system modifications or requiring sudo privileges.

🛡️ Core Principles
100% Read-Only: Zero system modifications, zero package installations, zero APT changes.

Zero Root / sudo Required: Runs completely in user space safely and securely.

Non-Interactive: Execution via python3 main.py runs cleanly without prompting for input.

Local & Private: Generates a clean ./lipis_report.md locally in your current directory.

🚀 Quick Start
Requirements
Python 3.8 or higher

Standard Linux utility environment (Ubuntu/Debian recommended)

Running LIPIS
Clone the repository and run the main entry point:

Bash
git clone [https://github.com/mubunet/lipis.git](https://github.com/mubunet/lipis.git)
cd lipis
python3 main.py
CLI Flags
python3 main.py --report (-r): Generate the Markdown diagnostic report silently (./lipis_report.md).

python3 main.py --version (-v): Output LIPIS version information.

📂 Project Structure
Plaintext
lipis/
├── main.py              # Main CLI entry point
├── README.md            # Project documentation
├── LICENSE              # MIT License
├── modules/             # Diagnostic modules (Read-Only)
│   ├── os_info.py       # OS distribution, kernel & uptime
│   ├── hardware.py      # CPU, RAM, disk usage & metrics
│   ├── network.py       # Interfaces, IP configuration & DNS
│   └── services.py      # Systemd services & active processes
└── outputs/             # Report generators & formatting templates


📄 License
Distributed under the MIT License. Copyright (c) 2026 MubuNet (mubunetofficial@gmail.com).