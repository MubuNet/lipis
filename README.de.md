[English](README.md) | **Deutsch**

# LIPIS - Linux PostInstall Script

```text
  _     ___ ____ ___ ____
 | |   |_ _|  _ \_ _/ ___|
 | |    | | | _) | |\___ \
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/
```

**LIPIS** (Linux PostInstall Script) ist als **vollständig passives, nur lesendes Diagnosewerkzeug** für Linux-Einsteiger unter Ubuntu/Debian geplant. Es soll den Systemzustand, Hardwareinformationen, Netzwerkkonfiguration und Dienste prüfen und daraus einen übersichtlichen, hilfreichen Bericht erstellen – ohne Änderungen am System und ohne `sudo`-Rechte.

> **Projektstatus:** LIPIS befindet sich noch in der Planungsphase. Das Script und die unten beschriebenen Dateien gibt es noch nicht; die Beispielbefehle sind daher derzeit noch nicht nutzbar.

## 🛡️ Geplante Grundsätze

- **Vollständig nur lesend:** Keine Änderungen am System, keine Paketinstallationen und keine APT-Änderungen.
- **Kein Root / kein `sudo` erforderlich:** Das Werkzeug soll sicher mit normalen Benutzerrechten laufen.
- **Nicht interaktiv:** Die geplante Kommandozeile soll ohne Rückfragen ausgeführt werden können.
- **Lokal und privat:** Der geplante Bericht soll im aktuellen Verzeichnis als `./lipis_report.md` gespeichert werden.

## 🚀 Geplanter Schnellstart

### Voraussetzungen

- Python 3.8 oder höher
- Eine übliche Linux-Systemumgebung (Ubuntu/Debian empfohlen)

### Vorgesehene Verwendung

Nach der Implementierung soll der geplante Einstiegspunkt voraussichtlich so verwendet werden:

```bash
git clone https://github.com/mubunet/lipis.git
cd lipis
python3 main.py
```

### Geplante Kommandozeilenoptionen

- `python3 main.py --report` (`-r`): Den Diagnosebericht im Markdown-Format unter `./lipis_report.md` erstellen.
- `python3 main.py --version` (`-v`): Versionsinformationen zu LIPIS anzeigen.

## 📂 Geplante Projektstruktur

```text
lipis/
├── main.py              # Geplanter Kommandozeilen-Einstiegspunkt
├── README.md            # Projektdokumentation
├── LICENSE              # MIT-Lizenz
├── modules/             # Geplante, nur lesende Diagnosemodule
│   ├── os_info.py       # Distribution, Kernel und Laufzeit
│   ├── hardware.py      # CPU, RAM, Speicherplatz und Kennzahlen
│   ├── network.py       # Schnittstellen, IP-Konfiguration und DNS
│   └── services.py      # Systemd-Dienste und aktive Prozesse
└── outputs/             # Geplante Berichterstellung und Formatierung
```

## 📄 Lizenz

Veröffentlicht unter der **MIT-Lizenz**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
