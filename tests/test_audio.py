import socket
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.audio import (
    AudioCard,
    AudioInfo,
    AudioStack,
    _detect_audio_stacks,
    _read_alsa_cards,
    _wslg_socket_state,
    collect_audio_info,
    render_audio_info,
)


class AudioCollectionTests(unittest.TestCase):
    def test_reads_alsa_card_identity_and_driver(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cards_path = root / "cards"
            cards_path.write_text(
                " 0 [Generic         ]: HDA-Intel - HD Audio Controller\n",
                encoding="utf-8",
            )
            driver_path = root / "drivers" / "snd_hda_intel"
            driver_path.mkdir(parents=True)
            sound_class = root / "sound"
            card_path = sound_class / "card0"
            (card_path / "device").mkdir(parents=True)
            (card_path / "device" / "driver").symlink_to(
                driver_path, target_is_directory=True
            )

            cards = _read_alsa_cards(cards_path, sound_class, [])

        self.assertEqual(
            cards,
            (AudioCard(0, "HDA-Intel - HD Audio Controller", "snd_hda_intel"),),
        )

    def test_reports_sysfs_read_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            warnings = []
            cards = _read_alsa_cards(
                root / "missing-cards",
                root / "missing-class",
                warnings,
            )

        self.assertEqual(cards, ())
        self.assertEqual(warnings, [])

    def test_detects_pulseaudio_and_pipewire_from_server_info(self):
        def run_command(arguments, **_kwargs):
            if arguments[0] == "/usr/bin/pactl":
                return CompletedProcess(
                    arguments,
                    0,
                    "Server Name: PulseAudio (on PipeWire 1.2)\n"
                    "Default Sink: private-speaker-name\n",
                    "",
                )
            raise AssertionError("pw-cli is not needed when PipeWire is identified")

        with patch(
            "modules.audio.subprocess.run",
            side_effect=run_command,
        ):
            stacks = _detect_audio_stacks(
                "/usr/bin/pactl",
                "/usr/bin/pw-cli",
                [],
            )

        self.assertEqual(
            stacks,
            (
                AudioStack("PipeWire", True),
                AudioStack("PulseAudio", True),
            ),
        )

    def test_detects_pipewire_without_pulseaudio_compatibility(self):
        completed = CompletedProcess(["pw-cli"], 0, "Core info\n", "")
        with patch("modules.audio.subprocess.run", return_value=completed):
            stacks = _detect_audio_stacks(None, "/usr/bin/pw-cli", [])

        self.assertEqual(
            stacks,
            (
                AudioStack("PipeWire", True),
                AudioStack("PulseAudio", None),
            ),
        )

    def test_reports_audio_tool_failure(self):
        completed = CompletedProcess(["pactl"], 1, "", "connection refused")
        warnings = []
        with patch("modules.audio.subprocess.run", return_value=completed):
            stacks = _detect_audio_stacks("/usr/bin/pactl", None, warnings)

        self.assertEqual(
            stacks,
            (
                AudioStack("PipeWire", None),
                AudioStack("PulseAudio", False),
            ),
        )
        self.assertIn("pactl exited with status 1.", warnings)

    def test_checks_wslg_unix_socket(self):
        with TemporaryDirectory() as directory:
            socket_path = Path(directory) / "PulseServer"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(socket_path))
                server.listen(1)
                self.assertTrue(
                    _wslg_socket_state(
                        {"PULSE_SERVER": "unix:{}".format(socket_path)},
                        Path(directory) / "unused",
                    )
                )
            finally:
                server.close()

            self.assertFalse(
                _wslg_socket_state(
                    {"PULSE_SERVER": "unix:{}".format(socket_path)},
                    Path(directory) / "unused",
                )
            )

    def test_collects_wslg_status_and_available_audio_stacks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            socket_path = root / "PulseServer"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(socket_path))
                server.listen(1)
                with patch("modules.audio.shutil.which", return_value=None):
                    info = collect_audio_info(
                        root / "cards",
                        root / "sound",
                        socket_path,
                        {"PULSE_SERVER": "unix:{}".format(socket_path)},
                    )
            finally:
                server.close()

        self.assertFalse(info.cards)
        self.assertTrue(info.wslg_socket)
        self.assertEqual(info.stacks[0], AudioStack("ALSA cards", False))


class AudioPresentationTests(unittest.TestCase):
    def test_renders_wsl_forwarding_without_audio_device_names(self):
        info = AudioInfo(
            cards=(),
            stacks=(
                AudioStack("ALSA cards", False),
                AudioStack("PipeWire", None),
                AudioStack("PulseAudio", None),
            ),
            wslg_socket=False,
            warnings=(),
        )

        english = render_audio_info(info, "en", "WSL 2")
        german = render_audio_info(info, "de", "WSL 2")
        self.assertIn("ALSA-Audiokarten: nicht verfügbar", german)
        self.assertNotIn("ALSA cards:", german)
        self.assertIn("WSLg audio forwarding: socket not reachable", english)
        self.assertIn("do not identify Windows audio devices or models", english)
        self.assertIn("WSLg-Audio-Weiterleitung: Socket nicht erreichbar", german)
        self.assertIn("identifizieren keine Windows-Audiogeräte", german)
        self.assertNotIn("Speaker", english)
        self.assertNotIn("Mikrofon", german)

    def test_does_not_render_names_from_audio_server_output(self):
        info = AudioInfo(
            cards=(AudioCard(0, "HDA-Intel - Audio Controller", "snd_hda_intel"),),
            stacks=(AudioStack("PulseAudio", True),),
            wslg_socket=None,
            warnings=(),
        )
        output = render_audio_info(info, "en", "Linux")
        self.assertIn("HDA-Intel - Audio Controller", output)
        self.assertNotIn("private-speaker-name", output)


if __name__ == "__main__":
    unittest.main()
