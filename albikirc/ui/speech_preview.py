"""Speech preview shared by Preferences and the Speech menu."""

import sys

import wx
import wx.adv

from ..mac_speech import MacSpeechBackend


class SpeechPreview:
    def __init__(self):
        self._config = {}
        self._process = None
        self._tts = None
        self._tts_av_test_backend = None

    def stop(self):
        if self._tts_av_test_backend is not None:
            self._tts_av_test_backend.stop()
        if self._tts is not None and hasattr(self._tts, "Stop"):
            self._tts.Stop()
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass  # The preview finished between poll and terminate.
        self._process = None

    def _tts_map_rate(self, wpm: int) -> int:
        try:
            wpm = int(wpm)
        except Exception:
            wpm = 180
        baseline = 180.0
        # Map 60..600 wpm to roughly -10..10, clamp
        rel = (wpm - baseline) / (600.0 - 60.0)
        rate = int(round(rel * 20))
        if rate < -10:
            rate = -10
        if rate > 10:
            rate = 10
        return rate

    def speak(self, config):
        self.stop()
        self._config = config
        try:
            sample = "This is a test of text to speech."
            voiceover_requested = sys.platform == "darwin" and self._config.get(
                "use_voiceover", False
            )
            if voiceover_requested and self._tts_test_via_voiceover(sample):
                return
            if sys.platform == "darwin" and MacSpeechBackend.is_available():
                backend = getattr(self, "_tts_av_test_backend", None)
                if backend is None:
                    backend = MacSpeechBackend()
                    self._tts_av_test_backend = backend
                backend.stop()
                if backend.speak(
                    sample,
                    voice_name=str(self._config.get("voice") or "Default").strip(),
                    language=str(self._config.get("language", "")),
                    rate_wpm=int(self._config.get("rate_wpm", 180)),
                ):
                    return
            if self._tts_prefer_process_backend():
                cmd = self._tts_build_process_command(sample)
                if cmd:
                    try:
                        import subprocess

                        self._process = subprocess.Popen(cmd)
                        return
                    except Exception:
                        pass
            TTS = getattr(wx, "TextToSpeech", None) or getattr(wx.adv, "TextToSpeech", None)
            if TTS is not None:
                tts = TTS()
                self._tts = tts
                # Apply voice
                try:
                    want = str(self._config.get("voice") or "Default").strip()
                    if hasattr(tts, "GetVoices") and hasattr(tts, "SetVoice"):
                        voices = tts.GetVoices()
                        chosen = None
                        for v in voices:
                            name = None
                            for attr in ("GetName", "GetDescription", "Name"):
                                if hasattr(v, attr):
                                    val = getattr(v, attr)
                                    name = val() if callable(val) else val
                                    break
                            if not name and isinstance(v, (list, tuple)) and v:
                                name = str(v[0])
                            if str(name or "").strip() == want:
                                chosen = v
                                break
                        if chosen is not None:
                            try:
                                tts.SetVoice(chosen)
                            except Exception:
                                pass
                except Exception:
                    pass
                # Apply rate
                try:
                    rate_param = self._tts_map_rate(int(self._config.get("rate_wpm", 180)))
                    if hasattr(tts, "SetRate"):
                        tts.SetRate(rate_param)
                except Exception:
                    pass
                # Speak sample
                try:
                    if hasattr(tts, "Speak"):
                        tts.Speak(sample)
                        return
                except Exception:
                    pass
            # Fallback if wx TTS unavailable or failed
            try:
                import subprocess

                cmd = self._tts_build_process_command(sample)
                if cmd:
                    self._process = subprocess.Popen(cmd)
                    return
                self._process = subprocess.Popen(["spd-say", sample])
                return
            except Exception:
                pass
            wx.MessageBox("Text-to-speech engine not available.", "Speech", wx.OK | wx.ICON_WARNING)
        except Exception as e:
            wx.MessageBox(f"Speech error: {e}", "Speech", wx.OK | wx.ICON_ERROR)

    def _tts_test_via_voiceover(self, text: str) -> bool:
        try:
            import subprocess

            safe = (
                (text or "")
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\r", " ")
                .replace("\n", " ")
            )
            script = (
                'var vo = Application("/System/Library/CoreServices/VoiceOver.app");\n'
                f'vo.output("{safe}");\n'
            )
            proc = subprocess.run(
                ["osascript", "-l", "JavaScript", "-"],
                input=script,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _tts_prefer_process_backend(self) -> bool:
        try:
            import sys

            voice = str(self._config.get("voice") or "Default").strip()
            language = str(self._config.get("language", "") or "").strip()
            if sys.platform == "darwin":
                return True
            return voice.lower() != "default" or bool(language)
        except Exception:
            return False

    def _tts_build_process_command(self, text: str) -> list[str] | None:
        try:
            import sys

            voice = str(self._config.get("voice") or "Default").strip()
            wpm = int(self._config.get("rate_wpm", 180))
            if sys.platform == "darwin":
                cmd = ["say"]
                if voice and voice.lower() != "default":
                    cmd += ["-v", voice]
                cmd += ["-r", str(max(80, min(600, wpm))), text]
                return cmd
            if sys.platform.startswith("win"):
                rate = self._tts_map_rate(wpm)
                ps = (
                    "$t='" + text.replace("'", "''") + "';"
                    "Add-Type -AssemblyName System.Speech;"
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                    f"$s.Rate={rate};"
                )
                if voice and voice.lower() != "default":
                    ps += f"try{{$s.SelectVoice('{voice}')}}catch{{}};"
                ps += "$s.Speak($t);"
                return ["powershell", "-NoProfile", "-Command", ps]
            cmd = ["espeak", f"-s{max(80, min(600, wpm))}"]
            if voice and voice.lower() != "default":
                cmd += ["-v", voice]
            cmd.append(text)
            return cmd
        except Exception:
            return None
