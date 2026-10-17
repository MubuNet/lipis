[English](README.md) | **Deutsch**

# LIPIS - Linux PostInstall Script

```text
  _     ___ ____ ___ ____
 | |   |_ _|  _ \_ _/ ___|
 | |    | | | _) | |\___ \
 | |___ | | | __/| | ___) |
 |_____|___|_|  |___|____/
```

**LIPIS** (Linux PostInstall Script) ist ein Read-Only-Diagnosewerkzeug für Linux-Einsteiger unter Ubuntu und Debian, das sich in Entwicklung befindet.

> **Projektstatus — `0.1.0-dev`:** Der Kommandozeilen-Einstiegspunkt sowie die Basisdiagnosen für Betriebssystem/Kernel, Hardware und GPU/Treiber sind implementiert. Die übrigen Diagnosemodule und der Report-Generator sind noch geplant.

## Bereits verfügbar

- Liest Distributionsinformationen aus `/etc/os-release` und die Laufzeit aus `/proc/uptime`.
- Zeigt Kernel, Architektur und Laufzeit an und erkennt WSL bzw. WSL 2.
- Zeigt CPU-Modell und Anzahl logischer CPUs, verfügbaren/gesamten Arbeitsspeicher sowie belegten/freien Speicherplatz für Linux-Root (`/`) und das Dateisystem des aktuellen Arbeitsordners an.
- Kennzeichnet Hardware- und Dateisystemwerte in WSL als Angaben der WSL-Umgebung. Bei einem Start aus `/mnt/c` wird das eingebundene Windows-Laufwerk `C:` getrennt vom Linux-Root-Dateisystem angezeigt.
- Erkennt NVIDIA-, AMD- und Intel-Grafikgeräte anhand von PCI-Systeminformationen und zeigt den aktiven Kernel-Treiber an, sofern er ermittelbar ist. `nvidia-smi` wird nur verwendet, wenn es bereits installiert ist.
- Kennzeichnet GPU-Angaben unter WSL deutlich und leitet aus der WSL-GPU-Schnittstelle allein kein Host-GPU-Modell ab.
- Wählt Deutsch oder Englisch anhand der Systemsprache automatisch aus. Mit `--language de` oder `--language en` lässt sich die Auswahl überschreiben. Andere Sprachen verwenden Englisch.
- Verwendet ausschließlich die Python-Standardbibliothek. Root-Rechte und System-Paketinstallationen sind nicht erforderlich.

## LIPIS starten

Voraussetzung: Python 3.8 oder höher unter Linux (Ubuntu/Debian empfohlen).

```bash
git clone https://github.com/mubunet/lipis.git
cd lipis
python3 main.py
```

`python3 main.py --help` zeigt die verfügbaren Optionen an.

`python3 main.py --version` (oder `-v`) zeigt die Entwicklungsversion an.

## Geplante Funktionen

- Noch geplante Diagnosebereiche: WLAN und Bluetooth, Audio, Netzwerk sowie Sicherheit.
- Eine Live-Terminalanzeige mit dem MubuNet-Banner.
- Ein optionaler Markdown-Bericht namens `lipis_report.md`, gespeichert im Ordner, aus dem LIPIS gestartet wurde. Hostname, Benutzername und lokale IP-Adressen werden standardmäßig nicht in den Bericht aufgenommen.
- Optionale Abhängigkeiten für die Darstellung mit Rückfall auf die Python-Standardbibliothek.
- Spätere betriebssystemspezifische Profile, darunter klar getrennte Kali-spezifische Diagnosen.

## Projektstruktur

```text
lipis/
├── main.py              # Kommandozeilen-Einstiegspunkt
├── README.md            # Englische Dokumentation
├── README.de.md         # Deutsche Dokumentation
├── modules/
│   ├── os_info.py       # Diagnose von OS, Kernel und Laufzeit
│   ├── hardware.py      # Diagnose von CPU, Arbeitsspeicher und Dateisystemen
│   └── gpu_driver.py    # Diagnose von GPU und aktivem Treiber
└── outputs/             # Geplante Berichterstellung
```

## Lizenz

Veröffentlicht unter der **MIT-Lizenz**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
