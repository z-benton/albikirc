"""Shared speech choices and menu construction for Preferences and the menu bar."""

import sys

import wx
import wx.adv

from ..mac_speech import MacSpeechBackend


SPEECH_EVENTS = (
    ("mention", "Mentions (your nick in channel)"),
    ("channel_message", "Channel messages"),
    ("private_message", "Private messages"),
    ("notice", "Notices"),
)
MIN_SPEECH_RATE = 60
MAX_SPEECH_RATE = 600


class SpeechChoicesMixin:
    def _tts_get_voices(self) -> list[str]:
        try:
            # 1) Prefer wx.TextToSpeech enumeration
            TTS = getattr(wx, "TextToSpeech", None) or getattr(wx.adv, "TextToSpeech", None)
            if TTS is not None:
                try:
                    tts = TTS()
                    if hasattr(tts, "GetVoices"):
                        vs = tts.GetVoices()
                        names = []
                        try:
                            for v in vs:
                                name = None
                                for attr in ("GetName", "GetDescription", "Name"):
                                    if hasattr(v, attr):
                                        val = getattr(v, attr)
                                        name = val() if callable(val) else val
                                        break
                                if not name and isinstance(v, (list, tuple)) and v:
                                    name = str(v[0])
                                names.append(str(name or "Voice"))
                        except Exception:
                            pass
                        if names:
                            # Deduplicate while preserving order
                            seen = set()
                            out = []
                            for n in names:
                                if n not in seen:
                                    seen.add(n)
                                    out.append(n)
                            return out
                except Exception:
                    pass
            # 2) OS-level enumeration fallbacks
            import subprocess

            # Windows: PowerShell System.Speech voices
            if sys.platform.startswith("win"):
                try:
                    ps = (
                        "Add-Type -AssemblyName System.Speech;"
                        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
                    )
                    p = subprocess.Popen(
                        ["powershell", "-NoProfile", "-Command", ps],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    out, _ = p.communicate(timeout=3)
                    names = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
                    if names:
                        return names
                except Exception:
                    pass
            # Linux: espeak --voices
            try:
                p = subprocess.Popen(
                    ["espeak", "--voices"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                out, _ = p.communicate(timeout=3)
                names = []
                for line in (out or "").splitlines():
                    if not line or line.lower().startswith("pty ") or line.lower().startswith("\n"):
                        continue
                    parts = line.split()
                    if len(parts) >= 5:
                        # Voice name is usually the last column
                        names.append(parts[-1])
                if names:
                    # Remove header lines and dups
                    names = [n for n in names if n.lower() != "voice"]
                    seen = set()
                    out = []
                    for n in names:
                        if n not in seen:
                            seen.add(n)
                            out.append(n)
                    return out
            except Exception:
                pass
        except Exception:
            pass
        return ["Default"]

    def _tts_list_voices_detailed(self) -> list[dict]:
        out = []
        try:
            import sys
            import subprocess

            if sys.platform == "darwin" and MacSpeechBackend.is_available():
                for voice in MacSpeechBackend().available_voices():
                    nm = str(voice.get("name") or "Voice")
                    out.append(
                        {
                            "name": nm,
                            "lang": str(voice.get("lang") or ""),
                            "desc": str(voice.get("desc") or ""),
                            "eloquence": nm.lower()
                            in {
                                "eddy",
                                "flo",
                                "grandma",
                                "grandpa",
                                "reed",
                                "rocko",
                                "sandy",
                                "shelley",
                                "shelly",
                                "glen",
                                "glenn",
                            },
                        }
                    )
            elif sys.platform == "darwin":
                p = subprocess.Popen(
                    ["say", "-v", "?"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                txt, _ = p.communicate(timeout=3)
                for ln in (txt or "").splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    parts = ln.split()
                    if not parts:
                        continue
                    name = parts[0]
                    lang = ""
                    desc = ""
                    try:
                        if "#" in ln:
                            before, after = ln.split("#", 1)
                            desc = after.strip()
                            tokens = before.split()
                            if len(tokens) >= 2:
                                lang = tokens[1].strip()
                        elif len(parts) >= 2:
                            lang = parts[1].strip()
                    except Exception:
                        pass
                    nm = str(name)
                    elo = ("eloquence" in desc.lower()) or nm.lower() in {
                        "eddy",
                        "flo",
                        "grandma",
                        "grandpa",
                        "reed",
                        "rocko",
                        "sandy",
                        "shelley",
                        "shelly",
                        "glen",
                        "glenn",
                    }
                    if elo and (not lang or lang.lower() in ("en", "english")):
                        inferred = self._infer_lang_from_text(ln + " " + desc)
                        if inferred:
                            lang = inferred
                    out.append({"name": nm, "lang": lang, "desc": desc, "eloquence": elo})
            else:
                # Fallback to simple names via existing helper
                names = self._tts_get_voices() or []
                for nm in names:
                    elo = nm.lower() in {
                        "eddy",
                        "flo",
                        "grandma",
                        "grandpa",
                        "reed",
                        "rocko",
                        "sandy",
                        "shelley",
                        "shelly",
                        "glen",
                        "glenn",
                    }
                    out.append({"name": nm, "lang": "", "desc": "", "eloquence": elo})
        except Exception:
            pass
        # Dedup by (name, lang)
        seen = set()
        dedup = []
        for v in out:
            key = (v.get("name"), v.get("lang") or "")
            if key in seen:
                continue
            seen.add(key)
            dedup.append(v)
        return dedup

    def _friendly_lang_label(self, code: str) -> str:
        try:
            c = (code or "").strip()
            if not c:
                return "All Languages"
            c_norm = c.replace("-", "_")
            parts = c_norm.split("_", 1)
            lang = parts[0].lower()
            region = parts[1].upper() if len(parts) > 1 else ""
            lang_names = {
                "en": "English",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "it": "Italian",
                "pt": "Portuguese",
                "nl": "Dutch",
                "sv": "Swedish",
                "no": "Norwegian",
                "da": "Danish",
                "fi": "Finnish",
                "is": "Icelandic",
                "pl": "Polish",
                "cs": "Czech",
                "sk": "Slovak",
                "hu": "Hungarian",
                "ro": "Romanian",
                "bg": "Bulgarian",
                "ru": "Russian",
                "uk": "Ukrainian",
                "tr": "Turkish",
                "el": "Greek",
                "he": "Hebrew",
                "ar": "Arabic",
                "hi": "Hindi",
                "th": "Thai",
                "vi": "Vietnamese",
                "id": "Indonesian",
                "ms": "Malay",
                "zh": "Chinese",
                "ja": "Japanese",
                "ko": "Korean",
            }
            region_names = {
                "US": "US",
                "GB": "UK",
                "AU": "Australia",
                "CA": "Canada",
                "IN": "India",
                "ZA": "South Africa",
                "ES": "Spain",
                "MX": "Mexico",
                "BR": "Brazil",
                "PT": "Portugal",
                "FR": "France",
                "DE": "Germany",
                "IT": "Italy",
                "NL": "Netherlands",
                "SE": "Sweden",
                "NO": "Norway",
                "DK": "Denmark",
                "FI": "Finland",
                "IS": "Iceland",
                "PL": "Poland",
                "CZ": "Czechia",
                "SK": "Slovakia",
                "HU": "Hungary",
                "RO": "Romania",
                "BG": "Bulgaria",
                "RU": "Russia",
                "UA": "Ukraine",
                "TR": "Turkey",
                "GR": "Greece",
                "IL": "Israel",
                "SA": "Saudi Arabia",
                "TH": "Thailand",
                "VN": "Vietnam",
                "ID": "Indonesia",
                "MY": "Malaysia",
                "CN": "China",
                "TW": "Taiwan",
                "HK": "Hong Kong",
                "JP": "Japan",
                "KR": "Korea",
            }
            lang_label = lang_names.get(lang, c.upper())
            if region:
                reg_label = region_names.get(region, region)
                return f"{lang_label} ({reg_label})"
            return lang_label
        except Exception:
            return code or "All Languages"

    def _infer_lang_from_text(self, text: str) -> str | None:
        try:
            t = (text or "").lower()
            if "en_us" in t or "en-us" in t or "enus" in t:
                return "en_US"
            if "en_gb" in t or "en-gb" in t or "engb" in t or "uk english" in t:
                return "en_GB"
        except Exception:
            pass
        return None

    def _populate_speech_voices(self, menu, cfg, select):
        """Build identical choices; check items reflect one selection across submenus."""
        voice = str(cfg.get("voice", "Default"))
        language = str(cfg.get("language", "") or "")

        def add(target, name, lang=None):
            item = target.Append(wx.ID_ANY, name.replace("&", "&&"), kind=wx.ITEM_CHECK)
            checked = voice == name and (lang is None or language == lang)
            item.Check(checked)
            target.Bind(wx.EVT_MENU, lambda evt: select(name, lang), id=item.GetId())

        add(menu, "Default")
        voices = self._tts_list_voices_detailed()
        groups = {}
        for entry in voices:
            if entry.get("eloquence"):
                groups.setdefault(entry.get("lang") or "", []).append(entry)
        if groups:
            eloquence = wx.Menu()
            for lang in sorted(
                groups,
                key=lambda code: (
                    0 if code.lower() == "en_us" else 1 if code.lower() == "en_gb" else 2,
                    code,
                ),
            ):
                submenu = wx.Menu()
                for entry in groups[lang]:
                    add(submenu, entry["name"], lang)
                eloquence.AppendSubMenu(
                    submenu, self._friendly_lang_label(lang) if lang else "Other"
                )
            menu.AppendSubMenu(eloquence, "Eloquence")
        for entry in voices:
            if entry.get("eloquence") or entry["name"] == "Default":
                continue
            lang = entry.get("lang") or ""
            if language and lang.lower() != language.lower():
                continue
            add(menu, entry["name"], lang or None)

    def _speech_languages(self):
        return [""] + sorted(
            {entry["lang"] for entry in self._tts_list_voices_detailed() if entry.get("lang")}
        )

    def _populate_speech_languages(self, menu, cfg, select):
        for code in self._speech_languages():
            item = menu.Append(wx.ID_ANY, self._friendly_lang_label(code), kind=wx.ITEM_RADIO)
            item.Check(code == cfg.get("language", ""))
            menu.Bind(wx.EVT_MENU, lambda evt, lang=code: select(lang), id=item.GetId())
