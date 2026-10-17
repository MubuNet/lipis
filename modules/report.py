"""Privacy-conscious Markdown report generation."""

from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple


REPORT_FILENAME = "lipis_report.md"


def _privacy_filter(section: str, language: str) -> Tuple[str, ...]:
    """Remove private network identifiers, local paths, and raw warnings."""
    lines = []
    in_warnings = False
    in_network_section = False
    in_current_filesystem = False
    ssid_label = "Aktuelle SSID:" if language == "de" else "Current SSID:"

    for line in section.splitlines():
        stripped = line.strip()
        if stripped in ("=== Network ===", "=== Netzwerk ==="):
            in_network_section = True
            continue
        if in_network_section:
            continue
        if stripped in ("Warnings:", "Hinweise:"):
            in_warnings = True
            continue
        if in_warnings:
            continue
        if any(
            stripped.startswith(label)
            for label in (
                "Dateisystem des aktuellen Ordners:",
                "Filesystem of current directory:",
            )
        ):
            in_current_filesystem = True
            continue
        if in_current_filesystem:
            if line.startswith("  "):
                continue
            in_current_filesystem = False
        if stripped.startswith(ssid_label):
            continue
        lines.append(line)
    return tuple(lines)


def render_markdown_report(
    sections: Sequence[str],
    language: str,
    generated_at: Optional[datetime] = None,
) -> str:
    """Render localized diagnostic sections as Markdown with privacy filtering."""
    if language == "de":
        title = "LIPIS-Diagnosebericht"
        generated_label = "Erstellt"
        privacy_note = (
            "Netzwerkkonfiguration, lokale IP-/MAC-Adressen, DNS-Server, "
            "Gateways, WLAN-SSIDs sowie Hostname und Benutzername werden "
            "nicht in diesen Bericht aufgenommen."
        )
    else:
        title = "LIPIS Diagnostic Report"
        generated_label = "Generated"
        privacy_note = (
            "Network configuration, local IP/MAC addresses, DNS servers, "
            "gateways, Wi-Fi SSIDs, hostname, and username are excluded "
            "from this report."
        )

    timestamp = generated_at or datetime.now().astimezone()
    lines = [
        "# {}".format(title),
        "",
        "{}: {}".format(generated_label, timestamp.isoformat(timespec="seconds")),
        "",
        "> {}".format(privacy_note),
        "",
    ]
    for section in sections:
        for line in _privacy_filter(section, language):
            stripped = line.strip()
            if not stripped:
                lines.append("")
            elif stripped.startswith("===") and stripped.endswith("==="):
                heading = stripped.strip("= ").strip()
                lines.extend(("## {}".format(heading), ""))
            elif line.startswith("  "):
                lines.append("  - {}".format(stripped))
            else:
                lines.append("- {}".format(stripped))
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(
    sections: Sequence[str],
    language: str,
    output_directory: Optional[Path] = None,
    generated_at: Optional[datetime] = None,
) -> Path:
    """Write or replace the report in the selected current working directory."""
    directory = Path.cwd() if output_directory is None else output_directory
    report_path = directory / REPORT_FILENAME
    with report_path.open("w", encoding="utf-8", newline="\n") as report_file:
        report_file.write(render_markdown_report(sections, language, generated_at))
    return report_path
