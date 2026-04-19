from __future__ import annotations

import sys
from typing import Any


def _read_attr(obj: Any, *names: str) -> Any:
    for name in names:
        if not hasattr(obj, name):
            continue
        value = getattr(obj, name)
        try:
            return value() if callable(value) else value
        except Exception:
            continue
    return None


try:
    if sys.platform == "darwin":
        from AVFoundation import (  # type: ignore
            AVSpeechBoundaryImmediate,
            AVSpeechSynthesisVoice,
            AVSpeechSynthesizer,
            AVSpeechUtterance,
            AVSpeechUtteranceDefaultSpeechRate,
            AVSpeechUtteranceMaximumSpeechRate,
            AVSpeechUtteranceMinimumSpeechRate,
        )
    else:
        raise ImportError("macOS only backend")
except Exception:
    AVSpeechBoundaryImmediate = None
    AVSpeechSynthesisVoice = None
    AVSpeechSynthesizer = None
    AVSpeechUtterance = None
    AVSpeechUtteranceDefaultSpeechRate = 0.5
    AVSpeechUtteranceMaximumSpeechRate = 0.6
    AVSpeechUtteranceMinimumSpeechRate = 0.2


class MacSpeechBackend:
    def __init__(self):
        if not self.is_available():
            raise RuntimeError("AVFoundation speech backend is unavailable")
        self._synth = AVSpeechSynthesizer.alloc().init()

    @classmethod
    def is_available(cls) -> bool:
        return AVSpeechSynthesizer is not None

    def available_voices(self) -> list[dict[str, str]]:
        if not self.is_available():
            return []
        out: list[dict[str, str]] = []
        for voice in AVSpeechSynthesisVoice.speechVoices():
            name = str(_read_attr(voice, "name", "Name") or "Voice")
            identifier = str(_read_attr(voice, "identifier") or name)
            language = str(_read_attr(voice, "language") or "")
            quality = _read_attr(voice, "quality")
            desc_parts = []
            if language:
                desc_parts.append(language)
            if quality is not None:
                desc_parts.append(f"quality={quality}")
            out.append(
                {
                    "name": name,
                    "identifier": identifier,
                    "lang": language,
                    "desc": ", ".join(desc_parts),
                }
            )
        return out

    def _find_voice(self, name: str, language: str = ""):
        want = (name or "").strip()
        want_lang = (language or "").strip().lower()
        all_voices = AVSpeechSynthesisVoice.speechVoices()
        if want and want.lower() != "default":
            for voice in all_voices:
                voice_name = str(_read_attr(voice, "name", "Name") or "")
                voice_id = str(_read_attr(voice, "identifier") or "")
                voice_lang = str(_read_attr(voice, "language") or "").lower()
                if voice_name == want or voice_id == want:
                    if not want_lang or voice_lang == want_lang:
                        return voice
        if want_lang:
            voice = AVSpeechSynthesisVoice.voiceWithLanguage_(language)
            if voice is not None:
                return voice
        return None

    def _map_rate(self, wpm: int) -> float:
        try:
            wpm = int(wpm)
        except Exception:
            wpm = 180
        wpm = max(60, min(600, wpm))
        lo = float(AVSpeechUtteranceMinimumSpeechRate)
        hi = float(AVSpeechUtteranceMaximumSpeechRate)
        default = float(AVSpeechUtteranceDefaultSpeechRate)
        if wpm <= 180:
            ratio = (wpm - 60) / 120.0
            return lo + (default - lo) * ratio
        ratio = (wpm - 180) / 420.0
        return default + (hi - default) * ratio

    def speak(self, text: str, *, voice_name: str = "Default", language: str = "", rate_wpm: int = 180) -> bool:
        if not self.is_available() or not text:
            return False
        utterance = AVSpeechUtterance.alloc().initWithString_(text)
        voice = self._find_voice(voice_name, language)
        if voice is not None:
            utterance.setVoice_(voice)
        utterance.setRate_(self._map_rate(rate_wpm))
        self._synth.speakUtterance_(utterance)
        return True

    def stop(self):
        if not self.is_available():
            return
        self._synth.stopSpeakingAtBoundary_(AVSpeechBoundaryImmediate)

    def is_speaking(self) -> bool:
        if not self.is_available():
            return False
        return bool(_read_attr(self._synth, "isSpeaking", "speaking"))
