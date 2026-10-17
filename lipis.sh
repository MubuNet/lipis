#!/usr/bin/env bash
# LIPIS - Linux-Postinstall-Script
# 100% read-only: gibt nur Informationen aus, ändert nichts am System.
# Verwendung: ./lipis.sh [-h]

set -u
export LC_ALL=C.UTF-8 2>/dev/null || true

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "LIPIS - zeigt Systeminformationen an (nur lesend, keine Änderungen)."
  echo "Verwendung: $0 [-h]"
  exit 0
fi

have() { command -v "$1" >/dev/null 2>&1; }
section() { printf '\n=== %s ===\n' "$1"; }
hint() { printf '  Hinweis: %s\n' "$1"; }
# Führt einen Lesebefehl aus; Fehler brechen das Script nicht ab.
run() { "$@" 2>/dev/null || echo "  (nicht verfügbar: $1)"; }

echo "LIPIS - Linux-Postinstall-Script (nur Lesezugriff)"

section "System"
if [ -r /etc/os-release ]; then
  ( . /etc/os-release; echo "Distribution: ${PRETTY_NAME:-unbekannt}" )
fi
echo "Kernel:       $(uname -sr)"
echo "Architektur:  $(uname -m)"
echo "Hostname:     $(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null)"
have uptime && echo "Laufzeit:     $(uptime -p 2>/dev/null)"

section "Benutzer"
echo "Angemeldet als: $(id -un) (Gruppen: $(id -Gn))"
if [ "$(id -u)" -eq 0 ]; then
  hint "Du arbeitest als root. Für den Alltag besser einen normalen Benutzer nutzen."
elif have sudo && id -nG | tr ' ' '\n' | grep -qxE 'sudo|wheel|admin'; then
  echo "sudo-Rechte:    ja (Gruppenmitglied)"
else
  echo "sudo-Rechte:    nicht erkennbar"
fi

section "CPU und Arbeitsspeicher"
have lscpu && run lscpu | grep -E 'Model name|^CPU\(s\)' | sed 's/  */ /g'
have free && run free -h
if have swapon; then
  [ -n "$(swapon --noheadings 2>/dev/null)" ] || hint "Kein Swap aktiv."
fi

section "Festplatten und Speicherplatz"
have lsblk && run lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
run df -hT -x tmpfs -x devtmpfs -x squashfs
df --output=pcent / 2>/dev/null | tail -n1 | tr -d ' %' | {
  read -r p; [ -n "${p:-}" ] && [ "$p" -ge 90 ] && hint "Root-Partition zu ${p}% voll!"; true; }

section "Netzwerk"
if have ip; then
  run ip -brief address
  echo "Standardroute: $(ip route show default 2>/dev/null | head -n1)"
fi
[ -r /etc/resolv.conf ] && grep -E '^nameserver' /etc/resolv.conf

section "Firewall"
if have ufw; then
  echo "ufw installiert. Status per 'sudo ufw status' prüfbar (erfordert root)."
else
  hint "ufw nicht installiert. Eine einfache Firewall: 'sudo apt install ufw'."
fi

section "Pakete und Updates"
if have apt; then
  echo "Installierte Pakete: $(dpkg-query -f '.\n' -W 2>/dev/null | wc -l)"
  n=$(apt list --upgradable 2>/dev/null | grep -c upgradable)
  echo "Verfügbare Updates (laut lokalem Cache): $n"
  hint "Updates einspielen: 'sudo apt update && sudo apt upgrade' (macht dieses Script nicht)."
elif have dnf; then echo "Paketmanager: dnf"
elif have pacman; then echo "Paketmanager: pacman"
else echo "Kein bekannter Paketmanager gefunden."
fi

section "Dienste"
if have systemctl; then
  echo "Fehlgeschlagene Dienste:"
  run systemctl --failed --no-legend --no-pager
  for s in ssh sshd; do
    systemctl is-active --quiet "$s" 2>/dev/null && echo "SSH-Server läuft ($s)."
  done
fi

section "Lokal/Sprache und Zeit"
echo "LANG: ${LANG:-nicht gesetzt}"
have timedatectl && run timedatectl | grep -E 'Time zone|synchronized'

section "Grafik"
echo "Sitzungstyp: ${XDG_SESSION_TYPE:-keine grafische Sitzung}"
have lspci && run lspci | grep -iE 'vga|3d|display'

echo
echo "Fertig. Es wurde nichts verändert."
