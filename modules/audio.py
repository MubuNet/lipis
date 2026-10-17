"""Read-only Linux audio hardware and audio-server diagnostics."""

import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class AudioCard:
    """Technical identity and kernel driver for one ALSA sound card."""

    index: int
    name: str
    driver: Optional[str]


@dataclass(frozen=True)
class AudioStack:
    """Availability state for one audio server or compatibility interface."""

    name: str
    available: Optional[bool]


@dataclass(frozen=True)
class AudioInfo:
    """Collected audio hardware, audio-server, and WSL forwarding details."""

    cards: Tuple[AudioCard, ...]
    stacks: Tuple[AudioStack, ...]
    wslg_socket: Optional[bool]
    warnings: Tuple[str, ...]


def _read_alsa_cards(
    cards_path: Path,
    sound_class_path: Path,
    warnings: List[str],
) -> Tuple[AudioCard, ...]:
    """Read ALSA card identities from procfs and drivers from sysfs."""
    names: Dict[int, str] = {}
    try:
        contents = cards_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        contents = ""
    except OSError as error:
        warnings.append("Could not read {}: {}".format(cards_path, error))
        contents = ""

    for line in contents.splitlines():
        match = re.match(r"^\s*(\d+)\s+\[([^\]]+)\]\s*:\s*(.*)$", line)
        if match:
            index = int(match.group(1))
            card_id = match.group(2).strip()
            description = match.group(3).strip()
            names[index] = description or card_id

    try:
        sound_entries = tuple(sorted(sound_class_path.iterdir()))
    except FileNotFoundError:
        sound_entries = ()
    except OSError as error:
        warnings.append("Could not list {}: {}".format(sound_class_path, error))
        sound_entries = ()

    for entry in sound_entries:
        match = re.match(r"^card(\d+)$", entry.name)
        if match:
            names.setdefault(int(match.group(1)), entry.name)

    cards = []
    for index, name in sorted(names.items()):
        driver = None
        driver_link = sound_class_path / "card{}".format(index) / "device" / "driver"
        try:
            driver = driver_link.resolve(strict=True).name
        except FileNotFoundError:
            pass
        except OSError as error:
            warnings.append(
                "Could not inspect audio driver for card{}: {}".format(index, error)
            )
        cards.append(AudioCard(index=index, name=name, driver=driver))
    return tuple(cards)


def _run_audio_tool(
    tool_path: str,
    arguments: List[str],
    tool_name: str,
    warnings: List[str],
) -> Optional[str]:
    """Run an installed audio status tool without shell or elevated privileges."""
    try:
        result = subprocess.run(
            [tool_path] + arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        warnings.append("Could not run {}: {}".format(tool_name, error))
        return None

    if result.returncode != 0:
        warnings.append(
            "{} exited with status {}.".format(tool_name, result.returncode)
        )
        return None
    return result.stdout


def _detect_audio_stacks(
    pactl_path: Optional[str],
    pw_cli_path: Optional[str],
    warnings: List[str],
) -> Tuple[AudioStack, ...]:
    """Check PipeWire/PulseAudio availability without returning device names."""
    pulse_available: Optional[bool] = None
    pipewire_available: Optional[bool] = None
    if pactl_path:
        output = _run_audio_tool(pactl_path, ["info"], "pactl", warnings)
        if output is not None:
            pulse_available = True
            server_name = next(
                (
                    line.split(":", 1)[1].strip().lower()
                    for line in output.splitlines()
                    if line.lower().startswith("server name:")
                ),
                "",
            )
            if "pipewire" in server_name:
                pipewire_available = True
            else:
                pipewire_available = False
        else:
            pulse_available = False

    if pw_cli_path and pipewire_available is not True:
        output = _run_audio_tool(pw_cli_path, ["info", "0"], "pw-cli", warnings)
        if output is not None:
            pipewire_available = True
        elif pipewire_available is None:
            pipewire_available = False

    return (
        AudioStack("PipeWire", pipewire_available),
        AudioStack("PulseAudio", pulse_available),
    )


def _wslg_socket_state(
    environment: Mapping[str, str],
    wslg_socket_path: Path,
) -> Optional[bool]:
    """Check whether a configured WSLg PulseAudio Unix socket is present."""
    pulse_server = environment.get("PULSE_SERVER", "")
    if pulse_server.startswith("unix:"):
        socket_path = pulse_server[len("unix:") :]
    elif wslg_socket_path.exists():
        socket_path = str(wslg_socket_path)
    else:
        return None

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(1)
        client.connect(socket_path)
        return True
    except OSError:
        return False
    finally:
        client.close()


def collect_audio_info(
    cards_path: Path = Path("/proc/asound/cards"),
    sound_class_path: Path = Path("/sys/class/sound"),
    wslg_socket_path: Path = Path("/mnt/wslg/PulseServer"),
    environ: Optional[Mapping[str, str]] = None,
) -> AudioInfo:
    """Collect read-only ALSA hardware and audio-server availability."""
    warnings: List[str] = []
    environment = os.environ if environ is None else environ
    cards = _read_alsa_cards(cards_path, sound_class_path, warnings)
    stacks = _detect_audio_stacks(
        shutil.which("pactl"),
        shutil.which("pw-cli"),
        warnings,
    )
    stacks = (
        AudioStack("ALSA cards", bool(cards)),
    ) + stacks
    return AudioInfo(
        cards=cards,
        stacks=stacks,
        wslg_socket=_wslg_socket_state(environment, wslg_socket_path),
        warnings=tuple(warnings),
    )


def render_audio_info(
    info: AudioInfo,
    language: str,
    environment: str,
) -> str:
    """Render audio details without showing output/input device names."""
    if language == "de":
        labels = {
            "section": "Audio",
            "no_cards": "Keine ALSA-Audiokarte erkannt.",
            "card": "Audiokarte",
            "driver": "Treiber",
            "unavailable": "Nicht verfügbar",
            "available": "verfügbar",
            "not_available": "nicht verfügbar",
            "unknown": "nicht ermittelt",
            "wslg": "WSLg-Audio-Weiterleitung",
            "socket_available": "Socket erreichbar",
            "socket_missing": "Socket nicht erreichbar",
            "wsl_note": (
                "Audiowerte beziehen sich auf Linux/WSLg und identifizieren "
                "keine Windows-Audiogeräte oder -Modelle."
            ),
            "warnings": "Hinweise",
        }
    else:
        labels = {
            "section": "Audio",
            "no_cards": "No ALSA audio card detected.",
            "card": "Audio card",
            "driver": "Driver",
            "unavailable": "Unavailable",
            "available": "available",
            "not_available": "not available",
            "unknown": "not determined",
            "wslg": "WSLg audio forwarding",
            "socket_available": "socket reachable",
            "socket_missing": "socket not reachable",
            "wsl_note": (
                "Audio values describe Linux/WSLg and do not identify Windows "
                "audio devices or models."
            ),
            "warnings": "Warnings",
        }

    lines = ["=== {} ===".format(labels["section"])]
    if not info.cards:
        lines.append(labels["no_cards"])
    for card in info.cards:
        lines.append("{} {}: {}".format(labels["card"], card.index, card.name))
        lines.append(
            "  {}: {}".format(labels["driver"], card.driver or labels["unavailable"])
        )

    for stack in info.stacks:
        status = (
            labels["available"]
            if stack.available is True
            else labels["not_available"]
            if stack.available is False
            else labels["unknown"]
        )
        lines.append("{}: {}".format(stack.name, status))

    if environment.startswith("WSL"):
        if info.wslg_socket is not None:
            socket_state = (
                labels["socket_available"]
                if info.wslg_socket
                else labels["socket_missing"]
            )
            lines.append("{}: {}".format(labels["wslg"], socket_state))
        lines.append("WSL: {}".format(labels["wsl_note"]))

    if info.warnings:
        lines.append("{}:".format(labels["warnings"]))
        lines.extend("- {}".format(warning) for warning in info.warnings)
    return "\n".join(lines)
