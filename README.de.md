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

> **Projektstatus — `0.1.0`:** Erste Version, getestet unter WSL 2 und nativem Xubuntu. Der Kommandozeilen-Einstiegspunkt, alle sieben Diagnosebereiche und der optionale datenschutzgefilterte Markdown-Bericht sind implementiert.

## Bereits verfügbar

- Liest Distributionsinformationen aus `/etc/os-release` und die Laufzeit aus `/proc/uptime`.
- Zeigt Kernel, Architektur und Laufzeit an und erkennt WSL bzw. WSL 2.
- Zeigt CPU-Modell und Anzahl logischer CPUs, verfügbaren/gesamten Arbeitsspeicher sowie belegten/freien Speicherplatz für Linux-Root (`/`) und das Dateisystem des aktuellen Arbeitsordners an.
- Kennzeichnet Hardware- und Dateisystemwerte in WSL als Angaben der WSL-Umgebung. Bei einem Start aus `/mnt/c` wird das eingebundene Windows-Laufwerk `C:` getrennt vom Linux-Root-Dateisystem angezeigt.
- Erkennt NVIDIA-, AMD- und Intel-Grafikgeräte anhand von PCI-Systeminformationen und zeigt den aktiven Kernel-Treiber an, sofern er ermittelbar ist. `nvidia-smi` wird nur verwendet, wenn es bereits installiert ist.
- Kennzeichnet GPU-Angaben unter WSL deutlich und leitet aus der WSL-GPU-Schnittstelle allein kein Host-GPU-Modell ab.
- Zeigt WLAN-Schnittstellen, Treiber, Schnittstellen-/Verbindungsstatus und nur die SSID der aktuellen Verbindung an. Eine Suche nach benachbarten WLANs findet nicht statt.
- Zeigt Bluetooth-Controller, Treiber und Einschaltstatus an, ohne nach Geräten zu suchen oder gekoppelte Geräte aufzulisten.
- Verwendet sysfs und optionale, bereits installierte Werkzeuge (`iw`, `nmcli`, `rfkill` und `bluetoothctl`) für Funkdiagnosen. Es werden keine Pakete installiert und keine Root-Rechte benötigt. WSL-Einschränkungen werden klar gekennzeichnet.
- Zeigt ALSA-Audiokarten und Treiber an und prüft optionale PulseAudio-/PipeWire-Clients, ohne Lautsprecher-, Mikrofon- oder Headset-Namen auszugeben. Die WSLg-Audio-Weiterleitung wird getrennt angezeigt und nicht als Erkennung von Windows-Audiogeräten ausgegeben.
- Zeigt Status, MAC- und IP-Adressen von Linux-Netzwerkschnittstellen sowie Standard-Gateways und DNS-Server ausschließlich aus lokaler Systemkonfiguration an; aktive Verbindungstests finden nicht statt. Diese Werte erscheinen im Terminal, werden aber aus dem Markdown-Bericht ausgeschlossen.
- Kennzeichnet Netzwerkangaben unter WSL als virtuelle Linux-Sicht und leitet daraus keine Windows-Netzwerkadapter ab.
- Zeigt laut lokalem APT-Cache verfügbare Sicherheitsupdates, den Status vorhandener Firewalls sowie AppArmor/SELinux, ASLR, Secure Boot und Kernel-Lockdown an, sofern diese Werte ermittelbar sind. Der Paket-Cache kann veraltet sein; LIPIS aktualisiert keine Paketlisten, benötigt keine Root-Rechte, installiert keine Pakete und ändert keine Systemeinstellungen. Unbekannte oder unzugängliche Werte gelten nicht als Sicherheitsfehler.
- Kennzeichnet Sicherheitswerte unter WSL als Linux-/WSL-Status und leitet keine Schutzmechanismen des Windows-Hosts ab. Detaillierte Sicherheitsbefunde sind im Bericht enthalten; Netzwerkkennungen und -konfiguration bleiben darin ausgeschlossen.
- Schreibt `lipis_report.md` nur mit der Option `--report` in den aktuellen Arbeitsordner; eine vorhandene Datei wird ersetzt. Der Bericht enthält detaillierte Sicherheitsbefunde, lässt aber Netzwerkkonfiguration, lokale IP-/MAC-Adressen, DNS-Server, Gateways, WLAN-SSIDs, Hostname, Benutzername und den Pfad des aktuellen Ordners aus.
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

`python3 main.py --version` (oder `-v`) zeigt die aktuelle Version an.

Mit `python3 main.py --report` wird zusätzlich `lipis_report.md` im aktuellen Arbeitsordner geschrieben. Eine vorhandene Datei gleichen Namens wird ersetzt.

## Geplante Funktionen

- Eine Live-Terminalanzeige mit dem MubuNet-Banner.
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
│   ├── gpu_driver.py    # Diagnose von GPU und aktivem Treiber
│   ├── wireless_bluetooth.py # WLAN- und Bluetooth-Diagnose
│   ├── audio.py         # Diagnose von Audiohardware und Audiostacks
│   ├── network.py       # Diagnose lokaler Netzwerkkonfiguration
│   ├── security.py      # Read-Only-Sicherheitsdiagnose
│   └── report.py        # Datenschutzgefilterte Markdown-Berichte
```

## Lizenz

Veröffentlicht unter der **MIT-Lizenz**. Copyright (c) 2026 **MubuNet** (`mubunetofficial@gmail.com`).
