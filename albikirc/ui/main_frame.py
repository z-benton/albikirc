import time
from collections import deque

import wx
import wx.adv

from .chat_panel import ChatPanel
from ..irc_client import IRCClient
from ..config import save, _default_sound_path
from .connect_dialog import ConnectDialog
from .preferences_dialog import PreferencesDialog
from .saved_servers_dialog import SavedServersDialog
from .help_dialog import HelpDialog
from ..event_bus import event_bus


class MainFrame(wx.Frame):
    def __init__(self, *args, settings=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.SetName("albikirc main window")

        self.settings = settings or {}
        self.irc = IRCClient()
        # Apply CTCP prefs to irc client
        ctcp = self.settings.get('ctcp', {})
        self.irc.respond_to_ctcp_version = ctcp.get('respond_to_ctcp_version', True)
        self.irc.ignore_ctcp = ctcp.get('ignore_ctcp', False)
        self.irc.version_string = ctcp.get('version_string', self.irc.version_string)
        # Appearance
        app_cfg = self.settings.get('appearance', {})
        self._theme = (app_cfg.get('theme') or 'system').lower()
        self._timestamps = bool(app_cfg.get('timestamps', True))

        # Experimental beeps
        self._beeps_enabled = bool(self.settings.get('beeps', {}).get('enabled', False))
        self._tts_proc = None
        self._tts_queue = deque()
        self._tts_busy = False
        self._tts_last_active = 0.0
        self._tts_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tts_timer, self._tts_timer)

        # Notifications prefs
        notif = self.settings.get('notifications', {})
        self.irc.show_join_part_notices = bool(notif.get('show_join_part_notices', True))
        self.irc.show_quit_nick_notices = bool(notif.get('show_quit_nick_notices', True))
        self.irc.activity_summaries = bool(notif.get('activity_summaries', True))
        self.irc.activity_window_seconds = int(notif.get('activity_window_seconds', 10))
        self.irc.route_notices_inline = bool(notif.get('notices_inline', True))
        # Connection prefs
        conn = self.settings.get('connection', {})
        self.irc.enable_tcp_keepalive = bool(conn.get('tcp_keepalive_enabled', True))
        try:
            self.irc.tcp_keepalive_idle = int(conn.get('tcp_keepalive_idle', self.irc.tcp_keepalive_idle))
            self.irc.tcp_keepalive_interval = int(conn.get('tcp_keepalive_interval', self.irc.tcp_keepalive_interval))
            self.irc.tcp_keepalive_count = int(conn.get('tcp_keepalive_count', self.irc.tcp_keepalive_count))
        except Exception:
            pass
        # Note: receive beeps are handled on each incoming message in _on_irc_message

        self._bind_events()

        self._make_menu()
        self._make_body()
        self.CreateStatusBar()
        self.SetStatusText("Ready")
        try:
            sb = self.GetStatusBar()
            if sb:
                sb.SetName("Status bar")
                sb.SetToolTip("Application status messages")
        except Exception:
            pass

        self._make_accelerators()
        # Initialize Text-to-Speech (if configured and available)
        self._tts_init()

    # UI construction
    def _make_body(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)
        self.notebook.SetName("Conversation tabs")
        self.notebook.SetToolTip("Conversation tabs; each tab is a channel or private message")

        # Start with a default tab (e.g., console)
        self._target_tabs: dict[str, int] = {}
        self._add_chat_tab("Console")

        # Restore tabs and window geometry
        try:
            win = self.settings.get('window', {})
            size = win.get('size'); pos = win.get('position')
            if isinstance(size, list) and len(size) == 2:
                self.SetSize((int(size[0]), int(size[1])))
            if isinstance(pos, list) and len(pos) == 2:
                self.SetPosition((int(pos[0]), int(pos[1])))
        except Exception:
            pass
        try:
            tabs = list(self.settings.get('open_tabs', []))
            if tabs:
                # Skip restoring tabs until autoconnect is implemented; keep only Console.
                self.settings['open_tabs'] = []
                save(self.settings)
        except Exception:
            pass

        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 0)
        panel.SetSizer(sizer)

        self.SetSize((920, 600))

    def _add_chat_tab(self, title: str):
        chat = ChatPanel(self.notebook, on_send=self._on_send_message)
        # Apply appearance
        chat.set_show_timestamps(self._timestamps)
        chat.apply_theme(self._theme)
        # Bind user list interactions (double-click or Enter to PM)
        try:
            chat.user_list.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt, t=title: self._on_user_list_dclick(evt, t))
            chat.user_list.Bind(wx.EVT_CHAR_HOOK, lambda evt, t=title: self._on_user_list_key(evt, t))
        except Exception:
            pass
        idx = self.notebook.GetPageCount()
        self.notebook.AddPage(chat, title, select=True)
        self._rebuild_tab_index_map()
        return idx

    def _current_chat(self) -> ChatPanel | None:
        idx = self.notebook.GetSelection()
        if idx == wx.NOT_FOUND:
            return None
        return self.notebook.GetPage(idx)

    def _chat_for_target(self, target: str, create: bool = True) -> ChatPanel:
        key = target.lower()
        if key in self._target_tabs:
            return self.notebook.GetPage(self._target_tabs[key])
        if not create:
            return self._current_chat()
        idx = self._add_chat_tab(target)
        return self.notebook.GetPage(idx)

    def _rebuild_tab_index_map(self):
        self._target_tabs = {
            self.notebook.GetPageText(i).lower(): i for i in range(self.notebook.GetPageCount())
        }

    # Menus and shortcuts
    def _make_menu(self):
        menubar = wx.MenuBar()

        self.ID_CONNECT = wx.NewIdRef()
        self.ID_CONNECT_SAVED = wx.NewIdRef()
        self.ID_EXPORT_SERVERS = wx.NewIdRef()
        self.ID_IMPORT_SERVERS = wx.NewIdRef()
        self.ID_JOIN = wx.NewIdRef()
        self.ID_CLOSE_TAB = wx.NewIdRef()
        self.ID_PREFERENCES = wx.NewIdRef()
        self.ID_FOCUS_INPUT = wx.NewIdRef()
        self.ID_ABOUT = wx.ID_ABOUT
        self.ID_HELP_SHORTCUTS = wx.NewIdRef()
        self.ID_READ_ACTIVITY = wx.NewIdRef()
        self.ID_TEST_SOUNDS = wx.NewIdRef()
        self.ID_TOGGLE_TIMESTAMPS = wx.NewIdRef()

        file_menu = wx.Menu()
        file_menu.Append(self.ID_CONNECT, "&Connect\tCtrl-N", "Connect to a server")
        file_menu.Append(self.ID_CONNECT_SAVED, "Connect to &Saved…\tCtrl-Shift-N", "Connect to a saved server")
        file_menu.AppendSeparator()
        file_menu.Append(self.ID_EXPORT_SERVERS, "E&xport Servers…", "Export saved servers to a JSON file")
        file_menu.Append(self.ID_IMPORT_SERVERS, "&Import Servers…", "Import servers from a JSON file")
        file_menu.AppendSeparator()
        file_menu.Append(self.ID_JOIN, "&Join Channel…\tCtrl-J", "Join a channel")
        file_menu.Append(self.ID_CLOSE_TAB, "Close &Tab\tCtrl-W", "Close current tab")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tCtrl-Q", "Quit albikirc")

        edit_menu = wx.Menu()
        edit_menu.Append(self.ID_PREFERENCES, "&Preferences…\tCtrl-,", "Open preferences")

        view_menu = wx.Menu()
        view_menu.Append(self.ID_FOCUS_INPUT, "Focus &Message Input\tCtrl-Shift-M", "Focus the message input")
        view_menu.Append(self.ID_READ_ACTIVITY, "Read &Last Activity Summary\tCtrl-Shift-A", "Speak the last activity summary for the current tab")
        item_ts = view_menu.Append(self.ID_TOGGLE_TIMESTAMPS, "Show &Timestamps", "Toggle [HH:MM] timestamps in chat", kind=wx.ITEM_CHECK)
        try:
            item_ts.Check(bool(self._timestamps))
        except Exception:
            pass

        help_menu = wx.Menu()
        help_menu.Append(self.ID_HELP_SHORTCUTS, "Keyboard &Shortcuts…\tF1", "Show keyboard shortcuts and navigation tips")
        help_menu.Append(self.ID_ABOUT, "&About", "About albikirc")
        help_menu.AppendSeparator()
        help_menu.Append(self.ID_TEST_SOUNDS, "&Test Sounds…", "Diagnose and test configured sounds")

        # Optional Speech menu (adds voice/language selection, mac-first)
        speech_menu = self._build_menu_speech()

        menubar.Append(file_menu, "&File")
        menubar.Append(edit_menu, "&Edit")
        menubar.Append(view_menu, "&View")
        if speech_menu is not None:
            menubar.Append(speech_menu, "&Speech")
        menubar.Append(help_menu, "&Help")

        self.Bind(wx.EVT_MENU, self._on_connect, id=self.ID_CONNECT)
        self.Bind(wx.EVT_MENU, self._on_connect_saved, id=self.ID_CONNECT_SAVED)
        self.Bind(wx.EVT_MENU, self._on_export_servers, id=self.ID_EXPORT_SERVERS)
        self.Bind(wx.EVT_MENU, self._on_import_servers, id=self.ID_IMPORT_SERVERS)
        self.Bind(wx.EVT_MENU, self._on_join_channel, id=self.ID_JOIN)
        self.Bind(wx.EVT_MENU, self._on_close_tab, id=self.ID_CLOSE_TAB)
        self.Bind(wx.EVT_MENU, self._on_preferences, id=self.ID_PREFERENCES)
        self.Bind(wx.EVT_MENU, self._on_focus_input, id=self.ID_FOCUS_INPUT)
        self.Bind(wx.EVT_MENU, self._on_about, id=self.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self._on_help_shortcuts, id=self.ID_HELP_SHORTCUTS)
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_read_last_activity, id=self.ID_READ_ACTIVITY)
        self.Bind(wx.EVT_MENU, self._on_test_sounds, id=self.ID_TEST_SOUNDS)
        self.Bind(wx.EVT_MENU, self._on_toggle_timestamps, id=self.ID_TOGGLE_TIMESTAMPS)

        self.SetMenuBar(menubar)

    # --- Speech menu construction (macOS preferred) ---
    def _build_menu_speech(self) -> wx.Menu | None:
        try:
            import sys
            # Build on all platforms, but language submenu is mac-only
            m = wx.Menu()

            # IDs and state
            self.ID_TTS_ENABLE = getattr(self, 'ID_TTS_ENABLE', wx.NewIdRef())
            self._tts_voice_ids = {}
            self._tts_lang_ids = {}

            # Enable toggle
            item_enable = m.Append(self.ID_TTS_ENABLE, "&Enable Text-to-Speech", kind=wx.ITEM_CHECK)
            cfg = self._get_tts_cfg()
            try:
                item_enable.Check(bool(cfg.get('enabled', False)))
            except Exception:
                pass
            self.Bind(wx.EVT_MENU, self._on_tts_toggle_enable, id=self.ID_TTS_ENABLE)

            # Voice submenu
            voices_menu = wx.Menu()
            m.AppendSubMenu(voices_menu, "&Voice")
            self._populate_voice_submenu(voices_menu)

            # Language submenu (macOS only)
            if sys.platform == 'darwin':
                lang_menu = wx.Menu()
                m.AppendSubMenu(lang_menu, "&Language")
                self._populate_language_submenu(lang_menu)

            return m
        except Exception:
            return None

    def _populate_voice_submenu(self, voices_menu: wx.Menu):
        try:
            import sys
            # Clear previous
            while True:
                item = voices_menu.FindItemByPosition(0)
                if not item:
                    break
                voices_menu.Delete(item.GetId())
        except Exception:
            pass
        self._tts_voice_ids = {}
        cfg = self._get_tts_cfg()
        current_voice = str(cfg.get('voice', 'Default'))

        # Always include Default
        id_default = wx.NewIdRef()
        self._tts_voice_ids['Default'] = id_default
        item_def = voices_menu.Append(id_default, "&Default", kind=wx.ITEM_RADIO)
        try:
            item_def.Check(current_voice.lower() == 'default')
        except Exception:
            pass
        self.Bind(wx.EVT_MENU, lambda evt, name='Default': self._on_tts_select_voice(name), id=id_default)

        # Get voices with metadata (mac: name, lang, desc, eloquence)
        voices = self._list_voices_detailed()
        sel_lang = (cfg.get('language') or '').strip()

        # Group eloquence/non-eloquence
        eloquence = [v for v in voices if v.get('eloquence')]
        others = [v for v in voices if not v.get('eloquence')]

        # Optional Eloquence submenu grouped by language (do not filter by selected language)
        if eloquence:
            sub = wx.Menu()
            # Group by language code
            groups: dict[str, list[dict]] = {}
            for v in eloquence:
                lang = (v.get('lang') or '').strip() or 'Other'
                groups.setdefault(lang, []).append(v)
            # Order with en_US, en_GB first when present
            def sort_key(k: str):
                k_l = k.lower()
                if k_l == 'en_us': return (0, k)
                if k_l == 'en_gb': return (1, k)
                return (2, k)
            for lang in sorted(groups.keys(), key=sort_key):
                vs = groups[lang]
                sm = wx.Menu()
                for v in vs:
                    nm = v.get('name') or ''
                    if not nm:
                        continue
                    vid = wx.NewIdRef()
                    # key for internal map: name|lang to avoid collisions
                    self._tts_voice_ids[f"{nm}|{lang}"] = vid
                    label = nm
                    item = sm.Append(vid, label, kind=wx.ITEM_RADIO)
                    try:
                        # Check if this entry matches current selection
                        item.Check(current_voice == nm)
                    except Exception:
                        pass
                    self.Bind(wx.EVT_MENU, lambda evt, name=nm, l=(None if lang=='Other' else lang): self._on_tts_select_voice(name, l), id=vid)
            # Label the language submenu (user-friendly)
            sub_label = self._friendly_lang_label(lang) if lang != 'Other' else 'Other'
            sub.AppendSubMenu(sm, sub_label)
            voices_menu.AppendSubMenu(sub, "&Eloquence")

        # The remaining voices
        # Apply selected language filter to non-Eloquence voices for brevity
        filtered_others = [v for v in others if (not sel_lang) or (str(v.get('lang','')).lower() == sel_lang.lower())]
        for v in filtered_others:
            nm = v.get('name') or ''
            if not nm:
                continue
            vid = wx.NewIdRef()
            self._tts_voice_ids[nm] = vid
            item = voices_menu.Append(vid, nm, kind=wx.ITEM_RADIO)
            try:
                item.Check(current_voice == nm)
            except Exception:
                pass
            self.Bind(wx.EVT_MENU, lambda evt, name=nm: self._on_tts_select_voice(name, None), id=vid)

    def _populate_language_submenu(self, lang_menu: wx.Menu):
        try:
            # Clear previous
            while True:
                item = lang_menu.FindItemByPosition(0)
                if not item:
                    break
                lang_menu.Delete(item.GetId())
        except Exception:
            pass
        self._tts_lang_ids = {}
        cfg = self._get_tts_cfg()
        sel = (cfg.get('language') or '').strip()

        # Collect languages from voice list
        voices = self._list_voices_detailed()
        langs = []
        seen = set()
        for v in voices:
            lang = (v.get('lang') or '').strip()
            if not lang or lang in seen:
                continue
            seen.add(lang)
            langs.append(lang)
        langs.sort()

        # All languages option
        id_all = wx.NewIdRef()
        self._tts_lang_ids[''] = id_all
        item_all = lang_menu.Append(id_all, "&All Languages", kind=wx.ITEM_RADIO)
        try:
            item_all.Check(sel == '')
        except Exception:
            pass
        self.Bind(wx.EVT_MENU, lambda evt, code='': self._on_tts_select_language(code), id=id_all)

        # Add each language
        for code in langs:
            lid = wx.NewIdRef()
            self._tts_lang_ids[code] = lid
            label = self._friendly_lang_label(code)
            item = lang_menu.Append(lid, label, kind=wx.ITEM_RADIO)
            try:
                item.Check(sel.lower() == code.lower())
            except Exception:
                pass
            self.Bind(wx.EVT_MENU, lambda evt, c=code: self._on_tts_select_language(c), id=lid)

    def _on_tts_toggle_enable(self, evt):
        try:
            cfg = self.settings.setdefault('tts', {})
            cfg['enabled'] = bool(evt.IsChecked())
            save(self.settings)
            self._tts_init()
        except Exception:
            pass

    def _on_tts_select_voice(self, name: str, lang: str | None = None):
        try:
            cfg = self.settings.setdefault('tts', {})
            cfg['voice'] = str(name or 'Default')
            if lang is not None:
                cfg['language'] = str(lang or '')
            save(self.settings)
            self._tts_apply_settings()
            # Refresh Speech menu to update checkmarks across submenus
            bar = self.GetMenuBar()
            if bar:
                idx = -1
                for i in range(bar.GetMenuCount()):
                    if bar.GetMenuLabelText(i).lower() == 'speech':
                        idx = i; break
                if idx >= 0:
                    try:
                        bar.Remove(idx)
                    except Exception:
                        pass
                    new_m = self._build_menu_speech()
                    if new_m is not None:
                        bar.Insert(idx, new_m, "&Speech")
                        self.SetMenuBar(bar)
        except Exception:
            pass

    def _on_tts_select_language(self, code: str):
        try:
            cfg = self.settings.setdefault('tts', {})
            cfg['language'] = str(code or '')
            save(self.settings)
            # Rebuild voice submenu to filter by language
            bar = self.GetMenuBar()
            if not bar:
                return
            # Find our Speech menu: last before Help if present
            # Simpler: rebuild entire Speech menu
            idx = -1
            for i in range(bar.GetMenuCount()):
                if bar.GetMenuLabelText(i).lower() == 'speech':
                    idx = i; break
            if idx >= 0:
                try:
                    bar.Remove(idx)
                except Exception:
                    pass
                new_m = self._build_menu_speech()
                if new_m is not None:
                    bar.Insert(idx, new_m, "&Speech")
                    self.SetMenuBar(bar)
        except Exception:
            pass

    def _list_voices_detailed(self) -> list[dict]:
        """Return a list of voice dicts: {name, lang, desc, eloquence}.
        macOS uses `say -v ?`. Other OS return names only via wx TTS if available.
        """
        out = []
        try:
            # Try wx.TextToSpeech first
            TTS = getattr(wx, 'TextToSpeech', None) or getattr(wx.adv, 'TextToSpeech', None)
            if TTS is not None:
                try:
                    tts = TTS()
                    if hasattr(tts, 'GetVoices'):
                        for v in (tts.GetVoices() or []):
                            name = None
                            for attr in ('GetName', 'GetDescription', 'Name'):
                                if hasattr(v, attr):
                                    val = getattr(v, attr)
                                    name = val() if callable(val) else val
                                    break
                            if not name and isinstance(v, (list, tuple)) and v:
                                name = str(v[0])
                            nm = str(name or 'Voice')
                            out.append({'name': nm, 'lang': '', 'desc': '', 'eloquence': self._is_eloquence_name(nm)})
                except Exception:
                    pass
        except Exception:
            pass
        # macOS: prefer richer details from say -v ?
        try:
            import sys, subprocess
            if sys.platform == 'darwin':
                p = subprocess.Popen(["say", "-v", "?"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                txt, _ = p.communicate(timeout=3)
                out = []
                for ln in (txt or '').splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    # Example: "Agnes\ten_US    # ..."
                    parts = ln.split()
                    if not parts:
                        continue
                    name = parts[0]
                    lang = ''
                    desc = ''
                    try:
                        # Language usually the next token(s) until '#'
                        if '#' in ln:
                            before, after = ln.split('#', 1)
                            desc = after.strip()
                            tokens = before.split()
                            if len(tokens) >= 2:
                                lang = tokens[1].strip()
                        else:
                            if len(parts) >= 2:
                                lang = parts[1].strip()
                    except Exception:
                        pass
                    nm = str(name)
                    elo = (self._is_eloquence_name(nm) or ('eloquence' in desc.lower()))
                    # Improve language detection for Eloquence voices (e.g., ENUS/ENGB hints)
                    if elo and (not lang or lang.lower() in ('en', 'english')):
                        inferred = self._infer_lang_from_text(ln + ' ' + desc)
                        if inferred:
                            lang = inferred
                    out.append({'name': nm, 'lang': lang, 'desc': desc, 'eloquence': elo})
        except Exception:
            pass
        # Deduplicate by (name, lang) preserving order
        seen = set(); dedup = []
        for v in out:
            key = (v.get('name'), v.get('lang') or '')
            if key in seen:
                continue
            seen.add(key); dedup.append(v)
        return dedup

    def _is_eloquence_name(self, name: str) -> bool:
        try:
            n = (name or '').strip().lower()
            # Common Eloquence voices on macOS Ventura+
            elo = {
                'eddy','flo','grandma','grandpa','reed','rocko','sandy','shelley','shelly','glen','glenn'
            }
            return n in elo
        except Exception:
            return False

    def _friendly_lang_label(self, code: str) -> str:
        try:
            c = (code or '').strip()
            if not c:
                return 'All Languages'
            # Normalize code
            c_norm = c.replace('-', '_')
            parts = c_norm.split('_', 1)
            lang = parts[0].lower()
            region = (parts[1].upper() if len(parts) > 1 else '')
            lang_names = {
                'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian',
                'pt': 'Portuguese', 'nl': 'Dutch', 'sv': 'Swedish', 'no': 'Norwegian', 'da': 'Danish',
                'fi': 'Finnish', 'is': 'Icelandic', 'pl': 'Polish', 'cs': 'Czech', 'sk': 'Slovak',
                'hu': 'Hungarian', 'ro': 'Romanian', 'bg': 'Bulgarian', 'ru': 'Russian', 'uk': 'Ukrainian',
                'tr': 'Turkish', 'el': 'Greek', 'he': 'Hebrew', 'ar': 'Arabic', 'hi': 'Hindi',
                'th': 'Thai', 'vi': 'Vietnamese', 'id': 'Indonesian', 'ms': 'Malay', 'zh': 'Chinese',
                'ja': 'Japanese', 'ko': 'Korean'
            }
            region_names = {
                'US': 'US', 'GB': 'UK', 'AU': 'Australia', 'CA': 'Canada', 'IN': 'India', 'ZA': 'South Africa',
                'ES': 'Spain', 'MX': 'Mexico', 'BR': 'Brazil', 'PT': 'Portugal', 'FR': 'France', 'DE': 'Germany',
                'IT': 'Italy', 'NL': 'Netherlands', 'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland',
                'IS': 'Iceland', 'PL': 'Poland', 'CZ': 'Czechia', 'SK': 'Slovakia', 'HU': 'Hungary', 'RO': 'Romania',
                'BG': 'Bulgaria', 'RU': 'Russia', 'UA': 'Ukraine', 'TR': 'Turkey', 'GR': 'Greece', 'IL': 'Israel',
                'SA': 'Saudi Arabia', 'TH': 'Thailand', 'VN': 'Vietnam', 'ID': 'Indonesia', 'MY': 'Malaysia',
                'CN': 'China', 'TW': 'Taiwan', 'HK': 'Hong Kong', 'JP': 'Japan', 'KR': 'Korea'
            }
            lang_label = lang_names.get(lang, c.upper())
            if region:
                reg_label = region_names.get(region, region)
                return f"{lang_label} ({reg_label})"
            return lang_label
        except Exception:
            return code or 'All Languages'

    def _infer_lang_from_text(self, text: str) -> str | None:
        try:
            t = (text or '').lower()
            # Look for common encodings of region
            if 'en_us' in t or 'en-us' in t or 'enus' in t:
                return 'en_US'
            if 'en_gb' in t or 'en-gb' in t or 'engb' in t or 'uk english' in t:
                return 'en_GB'
        except Exception:
            pass
        return None

    def _infer_lang_from_object(self, v) -> str | None:
        try:
            for attr in ('GetLanguage', 'GetLocale', 'GetId', 'GetIdentifier', 'GetAttributes'):
                if hasattr(v, attr):
                    val = getattr(v, attr)
                    s = val() if callable(val) else val
                    if s:
                        inferred = self._infer_lang_from_text(str(s))
                        if inferred:
                            return inferred
        except Exception:
            pass
        try:
            rep = repr(v)
            inferred = self._infer_lang_from_text(rep)
            if inferred:
                return inferred
        except Exception:
            pass
        return None

    def _make_accelerators(self):
        # ACCEL_CMD maps to Ctrl on Windows/Linux and Command on macOS
        entries = [
            wx.AcceleratorEntry(wx.ACCEL_CMD, ord("N"), self.ID_CONNECT),
            wx.AcceleratorEntry(wx.ACCEL_CMD | wx.ACCEL_SHIFT, ord("N"), self.ID_CONNECT_SAVED),
            wx.AcceleratorEntry(wx.ACCEL_CMD, ord("J"), self.ID_JOIN),
            wx.AcceleratorEntry(wx.ACCEL_CMD, ord("W"), self.ID_CLOSE_TAB),
            wx.AcceleratorEntry(wx.ACCEL_CMD, ord(","), self.ID_PREFERENCES),
            wx.AcceleratorEntry(wx.ACCEL_CMD | wx.ACCEL_SHIFT, ord("M"), self.ID_FOCUS_INPUT),
            wx.AcceleratorEntry(wx.ACCEL_CMD | wx.ACCEL_SHIFT, ord("A"), self.ID_READ_ACTIVITY),
            wx.AcceleratorEntry(0, wx.WXK_F1, self.ID_HELP_SHORTCUTS),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))

    def _bind_events(self):
        event_bus.subscribe("irc.status", lambda text: wx.CallAfter(self._on_irc_status, text))
        event_bus.subscribe("irc.message", lambda target, sender, text: wx.CallAfter(self._on_irc_message, target, sender, text))
        event_bus.subscribe("irc.users", lambda target, users: wx.CallAfter(self._on_irc_users, target, users))

    # Event handlers
    def _on_connect(self, evt):
        # Use stored nick as the default in the dialog
        nick_default = self.settings.get('nick', '')
        realname_default = self.settings.get('realname', '')
        # Default keepalive from preferences
        conn = self.settings.get('connection', {})
        tcp_keepalive_default = bool(conn.get('tcp_keepalive_enabled', True))
        dlg = ConnectDialog(self, nick_default=nick_default, realname_default=realname_default, tcp_keepalive_default=tcp_keepalive_default)
        if dlg.ShowModal() == wx.ID_OK:
            host = dlg.host
            port = dlg.port
            nick = dlg.nick
            real_name = getattr(dlg, 'real_name', '')
            use_tls = dlg.use_tls
            tcp_keepalive = getattr(dlg, 'tcp_keepalive_enabled', False)
            server_password = getattr(dlg, 'server_password', '')
            name = getattr(dlg, 'server_name', '') or host
            if host and nick:
                # Apply auth/tls extras
                self.irc.sasl_enabled = getattr(dlg, 'sasl_enabled', False)
                self.irc.sasl_username = getattr(dlg, 'sasl_username', '') or nick
                self.irc.sasl_password = getattr(dlg, 'sasl_password', '')
                self.irc.tls_client_certfile = getattr(dlg, 'certfile', '') or None
                self.irc.tls_client_keyfile = getattr(dlg, 'keyfile', '') or None
                self.irc.enable_tcp_keepalive = bool(tcp_keepalive)
                self.irc.server_password = server_password or None
                self.irc.connect(host, port, nick, real_name=real_name, use_tls=use_tls)
                self.settings['nick'] = nick
                self.settings['realname'] = real_name
                # Save server if requested
                try:
                    do_save = getattr(dlg, 'save_server', False)
                    if do_save:
                        servers = list(self.settings.get('servers', []))
                        entry = {
                            'name': name, 'host': host, 'port': port, 'use_tls': bool(use_tls), 'nick': nick,
                            'real_name': real_name,
                            'sasl_enabled': getattr(dlg, 'sasl_enabled', False),
                            'sasl_username': getattr(dlg, 'sasl_username', ''),
                            'tls_client_certfile': getattr(dlg, 'certfile', ''),
                            'tls_client_keyfile': getattr(dlg, 'keyfile', ''),
                            'tcp_keepalive': bool(tcp_keepalive),
                        }
                        # Prevent duplicates (same host:port:tls:name)
                        if not any((s.get('host')==host and int(s.get('port',0))==int(port) and bool(s.get('use_tls',True))==bool(use_tls) and (s.get('name') or host)==name) for s in servers):
                            servers.append(entry)
                            self.settings['servers'] = servers
                except Exception:
                    pass
                save(self.settings)
                self.SetStatusText(f"Connecting to {host}:{port} as {nick}{' with TLS' if use_tls else ''}")
        dlg.Destroy()

    def _on_join_channel(self, evt):
        dlg = wx.TextEntryDialog(self, "Enter channel and key (e.g. #channel key)", "Join Channel")
        dlg.SetName("Join channel dialog")
        if dlg.ShowModal() == wx.ID_OK:
            value = dlg.GetValue().strip()
            if value:
                parts = value.split(None, 1)
                channel = parts[0]
                key = parts[1] if len(parts) > 1 else None
                self.irc.join_channel(channel, key)
                self._chat_for_target(channel, create=True)
        dlg.Destroy()


    def _on_export_servers(self, evt):
        servers = self.settings.get('servers', [])
        if not servers:
            wx.MessageBox("No saved servers to export.", "Export Servers", wx.OK | wx.ICON_INFORMATION)
            return
        with wx.FileDialog(self, message="Export servers to…", wildcard="JSON files (*.json)|*.json|All files (*.*)|*.*",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                try:
                    import json
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(servers, f, indent=2)
                    self._on_irc_status(f"Exported {len(servers)} server(s) to {path}")
                except Exception as e:
                    wx.MessageBox(f"Failed to export: {e}", "Export Servers", wx.OK | wx.ICON_ERROR)

    def _on_import_servers(self, evt):
        with wx.FileDialog(self, message="Import servers from…", wildcard="JSON files (*.json)|*.json|All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                try:
                    import json
                    with open(path, "r", encoding="utf-8") as f:
                        incoming = json.load(f)
                    if not isinstance(incoming, list):
                        raise ValueError("Invalid file format: expected a list")
                    servers = list(self.settings.get('servers', []))
                    # Merge avoiding duplicates
                    added = 0
                    for s in incoming:
                        if not isinstance(s, dict):
                            continue
                        host = s.get('host'); port = s.get('port'); name = s.get('name') or (host or ''); tls = bool(s.get('use_tls', True))
                        if not host or not port:
                            continue
                        dup = any((x.get('host')==host and int(x.get('port',0))==int(port) and bool(x.get('use_tls',True))==tls and (x.get('name') or x.get('host',''))==name) for x in servers)
                        if not dup:
                            servers.append({
                                'name': name, 'host': host, 'port': int(port), 'use_tls': tls,
                                'nick': s.get('nick',''), 'real_name': s.get('real_name',''),
                            })
                            added += 1
                    self.settings['servers'] = servers
                    save(self.settings)
                    self._on_irc_status(f"Imported {added} server(s) from {path}")
                except Exception as e:
                    wx.MessageBox(f"Failed to import: {e}", "Import Servers", wx.OK | wx.ICON_ERROR)
    def _on_connect_saved(self, evt):
        servers = list(self.settings.get('servers', []))
        if not servers:
            wx.MessageBox("No saved servers yet. Use File → Connect, check ‘Save server to servers list’, and connect to add one.", "Saved Servers", wx.OK | wx.ICON_INFORMATION)
            return
        dlg = SavedServersDialog(self, servers)
        if dlg.ShowModal() == wx.ID_OK:
            sel = dlg.selected
            if sel:
                host = sel.get('host','')
                port = int(sel.get('port', 6697))
                nick = sel.get('nick', self.settings.get('nick',''))
                real_name = sel.get('real_name', self.settings.get('realname',''))
                use_tls = bool(sel.get('use_tls', True))
                if host and nick:
                    # Apply saved extras
                    self.irc.sasl_enabled = bool(sel.get('sasl_enabled', False))
                    self.irc.sasl_username = sel.get('sasl_username', nick)
                    self.irc.sasl_password = sel.get('sasl_password', '')
                    self.irc.tls_client_certfile = sel.get('tls_client_certfile') or None
                    self.irc.tls_client_keyfile = sel.get('tls_client_keyfile') or None
                    self.irc.enable_tcp_keepalive = bool(sel.get('tcp_keepalive', True))
                    # Server password is not stored; default empty unless provided in entry
                    self.irc.server_password = sel.get('server_password', '') or None
                    self.irc.connect(host, port, nick, real_name=real_name, use_tls=use_tls)
                    self.settings['nick'] = nick
                    self.settings['realname'] = real_name
                    self.SetStatusText(f"Connecting to {host}:{port} as {nick}{' with TLS' if use_tls else ''}")
        # Persist any removals the dialog made
        self.settings['servers'] = list(dlg._servers)
        save(self.settings)
        dlg.Destroy()

    def _on_close_tab(self, evt):
        idx = self.notebook.GetSelection()
        if idx != wx.NOT_FOUND and self.notebook.GetPageCount() > 1:
            self.notebook.DeletePage(idx)
            self._rebuild_tab_index_map()

    def _on_preferences(self, evt):
        dlg = PreferencesDialog(self, self.settings)
        if dlg.ShowModal() == wx.ID_OK:
            vals = dlg.values
            self.settings['nick'] = vals.get('nick', self.settings.get('nick',''))
            self.settings['realname'] = vals.get('realname', self.settings.get('realname',''))
            self.settings['appearance'] = vals.get('appearance', self.settings.get('appearance', {}))
            self.settings['ctcp'] = vals.get('ctcp', self.settings.get('ctcp', {}))
            self.settings['notifications'] = vals.get('notifications', self.settings.get('notifications', {}))
            self.settings['connection'] = vals.get('connection', self.settings.get('connection', {}))
            self.settings['sounds'] = vals.get('sounds', self.settings.get('sounds', {}))
            self.settings['beeps'] = vals.get('beeps', self.settings.get('beeps', {}))
            self.settings['tts'] = vals.get('tts', self.settings.get('tts', {}))
            # Apply to irc client
            self.irc.respond_to_ctcp_version = self.settings['ctcp'].get('respond_to_ctcp_version', True)
            self.irc.ignore_ctcp = self.settings['ctcp'].get('ignore_ctcp', False)
            self.irc.version_string = self.settings['ctcp'].get('version_string', self.irc.version_string)
            self.irc.show_join_part_notices = bool(self.settings['notifications'].get('show_join_part_notices', True))
            self.irc.show_quit_nick_notices = bool(self.settings['notifications'].get('show_quit_nick_notices', True))
            self.irc.activity_summaries = bool(self.settings['notifications'].get('activity_summaries', True))
            self.irc.activity_window_seconds = int(self.settings['notifications'].get('activity_window_seconds', 10))
            self.irc.route_notices_inline = bool(self.settings['notifications'].get('notices_inline', True))
            self.irc.enable_tcp_keepalive = bool(self.settings['connection'].get('tcp_keepalive_enabled', True))
            try:
                self.irc.tcp_keepalive_idle = int(self.settings['connection'].get('tcp_keepalive_idle', self.irc.tcp_keepalive_idle))
                self.irc.tcp_keepalive_interval = int(self.settings['connection'].get('tcp_keepalive_interval', self.irc.tcp_keepalive_interval))
                self.irc.tcp_keepalive_count = int(self.settings['connection'].get('tcp_keepalive_count', self.irc.tcp_keepalive_count))
            except Exception:
                pass
            # Beeps
            self._beeps_enabled = bool(self.settings.get('beeps', {}).get('enabled', False))
            # TTS
            self._tts_init()
            # Apply appearance to all tabs
            app_cfg = self.settings.get('appearance', {})
            self._theme = (app_cfg.get('theme') or 'system').lower()
            self._timestamps = bool(app_cfg.get('timestamps', True))
            try:
                for i in range(self.notebook.GetPageCount()):
                    page = self.notebook.GetPage(i)
                    if isinstance(page, ChatPanel):
                        page.set_show_timestamps(self._timestamps)
                        page.apply_theme(self._theme)
            except Exception:
                pass
            save(self.settings)
            self._on_irc_status(
                f"Updated preferences: nick='{self.settings['nick']}', timestamps={'on' if self._timestamps else 'off'}, theme={self._theme}, CTCP VERSION auto-reply={self.irc.respond_to_ctcp_version}, ignore CTCP={self.irc.ignore_ctcp}, show join/part notices={self.irc.show_join_part_notices}, show quit/nick notices={self.irc.show_quit_nick_notices}, compact summaries={self.irc.activity_summaries} ({self.irc.activity_window_seconds}s), notices inline={'on' if self.irc.route_notices_inline else 'off'}, TCP keepalive={'on' if self.irc.enable_tcp_keepalive else 'off'}"
            )
        dlg.Destroy()

    # --- Text to Speech helpers ---
    def _get_tts_cfg(self):
        try:
            tts = self.settings.get('tts', {}) or {}
            ev = tts.get('events', {}) or {}
            return {
                'enabled': bool(tts.get('enabled', False)),
                'interrupt': bool(tts.get('interrupt', False)),
                'voice': tts.get('voice', 'Default'),
                'language': tts.get('language', ''),
                'rate_wpm': int(tts.get('rate_wpm', 180)),
                'events': {
                    'channel_message': bool(ev.get('channel_message', False)),
                    'private_message': bool(ev.get('private_message', False)),
                    'mention': bool(ev.get('mention', True)),
                    'notice': bool(ev.get('notice', False)),
                }
            }
        except Exception:
            return {'enabled': False, 'voice': 'Default', 'rate_wpm': 180, 'events': {}}

    def _tts_map_rate(self, wpm: int) -> int:
        try:
            wpm = int(wpm)
        except Exception:
            wpm = 180
        baseline = 180.0
        rel = (wpm - baseline) / (600.0 - 60.0)
        rate = int(round(rel * 20))  # -10..10
        if rate < -10: rate = -10
        if rate > 10: rate = 10
        return rate

    def _tts_init(self):
        cfg = self._get_tts_cfg()
        self._tts_enabled = bool(cfg.get('enabled', False))
        if not self._tts_enabled:
            self._tts_clear_queue()
            self._tts_stop_current()
            self._stop_tts_timer()
            return
        try:
            TTS = getattr(wx, 'TextToSpeech', None) or getattr(wx.adv, 'TextToSpeech', None)
            if TTS is None:
                self._tts = None
                return
            if not hasattr(self, '_tts') or self._tts is None:
                self._tts = TTS()
            # Apply voice and rate if possible
            self._tts_apply_settings()
        except Exception:
            self._tts = None

    def _tts_apply_settings(self):
        cfg = self._get_tts_cfg()
        tts = getattr(self, '_tts', None)
        if not tts:
            return
        # Voice selection
        try:
            want = str(cfg.get('voice', 'Default'))
            want_lang = str(cfg.get('language', '') or '')
            if hasattr(tts, 'GetVoices') and hasattr(tts, 'SetVoice'):
                voices = tts.GetVoices()
                chosen = None
                fallback = None
                for v in voices:
                    name = None
                    for attr in ('GetName', 'GetDescription', 'Name'):
                        if hasattr(v, attr):
                            val = getattr(v, attr)
                            name = val() if callable(val) else val
                            break
                    if not name and isinstance(v, (list, tuple)) and v:
                        name = str(v[0])
                    nm = str(name or '')
                    if nm != want:
                        continue
                    inferred = self._infer_lang_from_object(v)
                    if want_lang and inferred and inferred.lower() == want_lang.lower():
                        chosen = v
                        break
                    if fallback is None:
                        fallback = v
                if chosen is None:
                    chosen = fallback
                if chosen is not None:
                    try:
                        tts.SetVoice(chosen)
                    except Exception:
                        pass
        except Exception:
            pass
        # Rate
        try:
            rate_param = self._tts_map_rate(int(cfg.get('rate_wpm', 180)))
            if hasattr(tts, 'SetRate'):
                tts.SetRate(rate_param)
        except Exception:
            pass

    def _ensure_tts_timer(self):
        try:
            if getattr(self, '_tts_timer', None) and not self._tts_timer.IsRunning():
                self._tts_timer.Start(150)
        except Exception:
            pass

    def _stop_tts_timer(self):
        try:
            if getattr(self, '_tts_timer', None) and self._tts_timer.IsRunning():
                self._tts_timer.Stop()
        except Exception:
            pass

    def _tts_clear_queue(self):
        try:
            if hasattr(self, '_tts_queue') and self._tts_queue is not None:
                self._tts_queue.clear()
        except Exception:
            self._tts_queue = deque()

    def _tts_is_busy(self) -> bool:
        try:
            tts = getattr(self, '_tts', None)
            if tts and hasattr(tts, 'IsSpeaking') and tts.IsSpeaking():
                self._tts_last_active = time.time()
                return True
        except Exception:
            pass
        try:
            proc = getattr(self, '_tts_proc', None)
            if proc:
                if proc.poll() is None:
                    self._tts_last_active = time.time()
                    return True
                self._tts_proc = None
        except Exception:
            self._tts_proc = None
        # Give recently started speech a short grace window even if the backend
        # does not expose speaking state.
        try:
            if self._tts_busy and (time.time() - float(self._tts_last_active or 0.0)) < 0.1:
                return True
        except Exception:
            pass
        return False

    def _tts_start_playback(self, text: str, cfg: dict):
        started = False
        try:
            tts = getattr(self, '_tts', None)
            if tts and hasattr(tts, 'Speak') and text:
                tts.Speak(text)
                started = True
        except Exception:
            started = False
        if not started:
            started = self._tts_speak_fallback(text, cfg)
        self._tts_busy = bool(started)
        if started:
            self._tts_last_active = time.time()
            self._ensure_tts_timer()
        else:
            self._tts_busy = False

    def _on_tts_timer(self, evt):
        try:
            cfg = self._get_tts_cfg()
            if not cfg.get('enabled'):
                self._tts_clear_queue()
                self._tts_stop_current()
                self._tts_busy = False
                self._stop_tts_timer()
                return
            if self._tts_is_busy():
                return
            self._tts_busy = False
            if self._tts_queue:
                nxt = self._tts_queue.popleft()
                self._tts_start_playback(nxt, cfg)
            else:
                self._stop_tts_timer()
        except Exception:
            try:
                self._stop_tts_timer()
            except Exception:
                pass

    def _tts_speak(self, text: str):
        try:
            cfg = self._get_tts_cfg()
            if not cfg.get('enabled') or not text:
                return
            if cfg.get('interrupt'):
                self._tts_clear_queue()
                self._tts_stop_current()
                self._tts_start_playback(text, cfg)
                return
            if self._tts_is_busy():
                self._tts_queue.append(text)
                self._ensure_tts_timer()
                return
            self._tts_start_playback(text, cfg)
        except Exception:
            pass

    def _tts_stop_current(self):
        try:
            tts = getattr(self, '_tts', None)
            if tts and hasattr(tts, 'Stop'):
                try:
                    tts.Stop()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            proc = getattr(self, '_tts_proc', None)
            if not proc:
                return
            try:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            finally:
                self._tts_proc = None
        except Exception:
            self._tts_proc = None
        try:
            self._tts_busy = False
            self._tts_last_active = 0.0
            if not self._tts_queue:
                self._stop_tts_timer()
        except Exception:
            pass

    def _tts_start_process(self, cmd: list[str]):
        try:
            import subprocess
            proc = subprocess.Popen(cmd)
            self._tts_proc = proc
            return proc
        except Exception:
            return None

    def _tts_speak_fallback(self, text: str, cfg: dict | None = None) -> bool:
        try:
            import sys
            cfg = cfg or self._get_tts_cfg()
            voice = str(cfg.get('voice', 'Default'))
            wpm = int(cfg.get('rate_wpm', 180))
            # macOS: say
            if sys.platform == 'darwin':
                cmd = ["say"]
                if voice and voice.lower() != 'default':
                    cmd += ["-v", voice]
                # macOS say expects approximate words per minute via -r
                cmd += ["-r", str(max(80, min(600, wpm))), text]
                if self._tts_start_process(cmd):
                    return True
            # Windows: SAPI via PowerShell
            if sys.platform.startswith('win'):
                rate = self._tts_map_rate(wpm)
                ps = (
                    "$t='" + text.replace("'","''") + "';"
                    "Add-Type -AssemblyName System.Speech;"
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                    f"$s.Rate={rate};"
                )
                if voice and voice.lower() != 'default':
                    ps += f"try{{$s.SelectVoice('{voice}')}}catch{{}};"
                ps += "$s.Speak($t);"
                if self._tts_start_process(["powershell", "-NoProfile", "-Command", ps]):
                    return True
            # Linux: espeak or spd-say
            cmd = ["espeak", f"-s{max(80,min(600,wpm))}"]
            if voice and voice.lower() != 'default':
                cmd += ["-v", voice]
            cmd.append(text)
            if self._tts_start_process(cmd):
                return True
            if self._tts_start_process(["spd-say", text]):
                return True
        except Exception:
            pass
        return False


    def _on_focus_input(self, evt):
        chat = self._current_chat()
        if chat:
            chat.focus_input()

    def _on_about(self, evt):
        info = wx.adv.AboutDialogInfo()
        info.SetName("albikirc")
        info.SetVersion("0.1.0")
        info.SetDescription("Accessible IRC client scaffold using wxPython")
        try:
            wx.adv.AboutBox(info)
        except Exception:
            wx.MessageBox("albikirc 0.1.0", "About", wx.OK | wx.ICON_INFORMATION)

    def _on_help_shortcuts(self, evt):
        dlg = HelpDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_send_message(self, text: str):
        idx = self.notebook.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        target = self.notebook.GetPageText(idx)
        chat = self.notebook.GetPage(idx)
        # Slash commands
        if text.startswith('/'):
            self._handle_slash_command(target, chat, text)
            return
        chat.append_message(f"me: {text}")
        self.irc.send_message(target=target, text=text)
        # Optional sound when sending a message
        try:
            snd_cfg = self.settings.get('sounds', {})
            if snd_cfg.get('enabled'):
                self._play_sound(snd_cfg.get('message_sent', ''))
        except Exception:
            pass
        # Experimental beep on send
        try:
            if self._beeps_enabled:
                self._play_beep('send')
        except Exception:
            pass

    def _handle_slash_command(self, target: str, chat: ChatPanel, line: str):
        try:
            parts = line[1:].strip().split(None, 1)
            if not parts:
                return
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            command_handler = getattr(self, f"_handle_slash_{cmd}", None)
            if command_handler:
                command_handler(target, chat, arg)
            else:
                self._on_irc_status(f"Unknown command: /{cmd}")
        except Exception as e:
            self._on_irc_status(f"Command error: {e}")

    def _handle_slash_j(self, target, chat, arg):
        self._handle_slash_join(target, chat, arg)

    def _handle_slash_join(self, target, chat, arg):
        chan = arg.strip()
        if chan:
            self.irc.join_channel(chan)
            self._chat_for_target(chan, create=True)

    def _handle_slash_p(self, target, chat, arg):
        self._handle_slash_part(target, chat, arg)

    def _handle_slash_part(self, target, chat, arg):
        chan = arg.strip() or target
        if chan.lower().startswith('#') or chan.lower().startswith('&'):
            reason = ""
            if ' ' in arg:
                chan, reason = arg.split(' ', 1)
            self.irc._send_raw(f"PART {chan}{(' :' + reason) if reason else ''}")

    def _handle_slash_nick(self, target, chat, arg):
        new = arg.strip()
        if new:
            self.irc._send_raw(f"NICK {new}")

    def _handle_slash_me(self, target, chat, arg):
        act = arg.strip()
        if act:
            # Echo as "* <nick> action" to match incoming ACTION format
            nick = self.irc.nick or self.settings.get('nick', 'me')
            chat.append_message(f"* {nick} {act}")
            self.irc.send_action(target, act)
            # Consistent send feedback (sound/beep)
            try:
                snd_cfg = self.settings.get('sounds', {})
                if snd_cfg.get('enabled'):
                    self._play_sound(snd_cfg.get('message_sent', ''))
            except Exception:
                pass
            try:
                if self._beeps_enabled:
                    self._play_beep('send')
            except Exception:
                pass

    def _handle_slash_notice(self, target, chat, arg):
        if not arg:
            self._on_irc_status("Usage: /notice <target> <text>")
            return
        a = arg.split(None, 1)
        tgt = a[0]
        msg = a[1] if len(a) > 1 else ""
        if not msg:
            self._on_irc_status("Usage: /notice <target> <text>")
            return
        # Route echo to the target tab for consistency
        dest = self._chat_for_target(tgt, create=True)
        dest.append_message(f"me: [notice] {msg}")
        self.irc.send_notice(tgt, msg)
        # Consistent send feedback (sound/beep)
        try:
            snd_cfg = self.settings.get('sounds', {})
            if snd_cfg.get('enabled'):
                self._play_sound(snd_cfg.get('message_sent', ''))
        except Exception:
            pass
        try:
            if self._beeps_enabled:
                self._play_beep('send')
        except Exception:
            pass

    def _handle_slash_topic(self, target, chat, arg):
        arg_s = arg.strip()
        if not arg_s:
            if target.startswith('#') or target.startswith('&'):
                self.irc.set_topic(target, None)
            else:
                self._on_irc_status("Usage: /topic [#channel] [text]")
            return
        if arg_s.startswith('#') or arg_s.startswith('&'):
            # Could be just channel (query) or channel + text
            if ' ' in arg_s:
                chan, text = arg_s.split(' ', 1)
                self.irc.set_topic(chan, text)
            else:
                self.irc.set_topic(arg_s, None)
            return
        # Otherwise, treat as text for current channel
        if target.startswith('#') or target.startswith('&'):
            self.irc.set_topic(target, arg_s)
        else:
            self._on_irc_status("Usage: /topic [#channel] [text]")

    def _handle_slash_whois(self, target, chat, arg):
        nick = arg.strip()
        if not nick:
            # If current tab is PM, default to that nick
            if not (target.startswith('#') or target.startswith('&')):
                nick = target
        if not nick:
            self._on_irc_status("Usage: /whois <nick>")
            return
        self.irc.whois(nick)

    def _handle_slash_raw(self, target, chat, arg):
        raw = arg
        if not raw:
            self._on_irc_status("Usage: /raw <line>")
            return
        self.irc.send_raw(raw)

    def _handle_slash_msg(self, target, chat, arg):
        self._handle_slash_query(target, chat, arg)

    def _handle_slash_pm(self, target, chat, arg):
        self._handle_slash_query(target, chat, arg)

    def _handle_slash_query(self, target, chat, arg):
        if not arg:
            return
        a = arg.split(None, 1)
        nick = a[0]
        msg = a[1] if len(a) > 1 else ""
        pm = self._chat_for_target(nick, create=True)
        if msg:
            pm.append_message(f"me: {msg}")
            self.irc.send_message(nick, msg)
            # Consistent send feedback (sound/beep)
            try:
                snd_cfg = self.settings.get('sounds', {})
                if snd_cfg.get('enabled'):
                    self._play_sound(snd_cfg.get('message_sent', ''))
            except Exception:
                pass
            try:
                if self._beeps_enabled:
                    self._play_beep('send')
            except Exception:
                pass
        else:
            pm.focus_input()

    def _handle_slash_quit(self, target, chat, arg):
        reason = arg.strip() or "Bye"
        try:
            self.irc._send_raw(f"QUIT :{reason}")
        except Exception:
            pass
        self.Close()

    # IRC stub callbacks
    def _resolve_sound_path(self, path: str) -> str:
        try:
            if not path:
                return ""
            import os
            # Expand user and env vars
            p = os.path.expanduser(os.path.expandvars(path))
            # Prefer the provided path (absolute or CWD-relative).
            if os.path.exists(p):
                return p
            # Backward-compat: if the configured path is missing but the filename
            # matches a bundled sound, use the bundled copy to avoid disabling sounds.
            base = os.path.basename(p)
            if base:
                fallback = _default_sound_path(base)
                if fallback:
                    return fallback
        except Exception:
            pass
        return ""

    def _play_sound_any(self, resolved_path: str):
        """Attempt to play a sound using whichever backend is available.
        Returns (ok: bool, method: str, error: str|None).
        """
        try:
            last_err = None
            if not resolved_path:
                return (False, "none", None)
            # Interrupt any currently playing sound before starting a new one
            self._stop_sound_playback()
            self._cleanup_sound_processes()
            # Prefer OS-native players we can terminate for real interruption
            import sys
            if sys.platform.startswith('win'):
                try:
                    import winsound
                    winsound.PlaySound(resolved_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return (True, "winsound", None)
                except Exception as e:
                    return (False, "winsound", str(e))
            elif sys.platform == 'darwin':
                try:
                    import subprocess
                    p = subprocess.Popen(["afplay", resolved_path])
                    self._register_sound_proc(p)
                    return (True, "afplay", None)
                except Exception as e:
                    last_err = str(e)
            else:
                # Linux: try paplay, then aplay
                try:
                    import subprocess
                    p = subprocess.Popen(["paplay", resolved_path])
                    self._register_sound_proc(p)
                    return (True, "paplay", None)
                except Exception as e1:
                    try:
                        import subprocess
                        p = subprocess.Popen(["aplay", resolved_path])
                        self._register_sound_proc(p)
                        return (True, "aplay", None)
                    except Exception as e2:
                        last_err = f"{e1}; {e2}"
            # wx.Sound (classic) or wx.adv.Sound (phoenix optional) as a fallback
            try:
                SoundCls = getattr(wx, 'Sound', None) or getattr(wx.adv, 'Sound', None)
                if SoundCls is not None:
                    snd = SoundCls(resolved_path)
                    if hasattr(snd, 'IsOk') and not snd.IsOk():
                        return (False, "wx.Sound", None)
                    self._last_sound = snd
                    snd.Play(getattr(wx, 'SOUND_ASYNC', 0))
                    return (True, "wx.Sound", None)
            except Exception as e:
                last_err = str(e)
                # fallthrough to error handling
            return (False, "none", last_err)
        except Exception as e:
            return (False, "error", str(e))

    def _register_sound_proc(self, proc):
        """Track a subprocess-based sound so finished processes can be cleaned up."""
        if not hasattr(self, '_sound_procs'):
            self._sound_procs = []
        self._sound_procs.append(proc)

    def _cleanup_sound_processes(self):
        """Remove completed subprocess sound players to avoid leaks."""
        try:
            if not hasattr(self, '_sound_procs'):
                return
            alive = []
            for p in self._sound_procs:
                try:
                    if p.poll() is None:
                        alive.append(p)
                except Exception:
                    continue
            self._sound_procs = alive
        except Exception:
            pass

    def _stop_sound_playback(self):
        """Stop any in-flight sound so the next one can start immediately."""
        try:
            SoundCls = getattr(wx, 'Sound', None) or getattr(wx.adv, 'Sound', None)
            if SoundCls is not None and hasattr(SoundCls, 'Stop'):
                SoundCls.Stop()
        except Exception:
            pass
        try:
            import sys
            if sys.platform.startswith('win'):
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        try:
            import sys
            if hasattr(self, '_sound_procs'):
                for p in list(self._sound_procs):
                    try:
                        if p.poll() is None and sys.platform == 'darwin':
                            # afplay stops cleanly on terminate
                            p.terminate()
                    except Exception:
                        pass
                    try:
                        if p.poll() is None:
                            p.kill()
                    except Exception:
                        pass
                self._sound_procs = []
        except Exception:
            pass

    def _disable_sounds_due_error(self, reason: str = ""):
        # Disable sounds globally and notify once
        if getattr(self, '_sounds_disabled_due_error', False):
            return
        self._sounds_disabled_due_error = True
        try:
            self.settings.setdefault('sounds', {})['enabled'] = False
            save(self.settings)
        except Exception:
            pass
        try:
            msg = "Sounds disabled due to an error" + (f": {reason}" if reason else ".")
            self._on_irc_status(msg)
        except Exception:
            pass

    def _play_sound(self, path: str):
        try:
            resolved = self._resolve_sound_path(path)
            if not resolved:
                self._disable_sounds_due_error("invalid or missing path")
                return
            ok, method, err = self._play_sound_any(resolved)
            if not ok:
                self._disable_sounds_due_error(err or f"backend {method} failed")
        except Exception:
            self._disable_sounds_due_error("unexpected exception during playback")

    def _on_irc_status(self, text: str):
        chat = self._chat_for_target("Console", create=True)
        msg = text
        if text.startswith("CTCP "):
            msg = f"[CTCP] {text}"
        chat.append_message(f"[status] {msg}")
        self._handle_status_sound(text)
        self._handle_status_tts(text)

    def _on_irc_message(self, target: str, sender: str, text: str):
        # Route to appropriate tab; for PMs, target is our nick → use sender
        if target.lower() == (self.irc.nick or "").lower():
            tab_target = sender
        else:
            tab_target = target
        chat = self._chat_for_target(tab_target, create=True)
        if sender == "*":
            chat.append_message(f"* {text}")
        else:
            chat.append_message(f"{sender}: {text}")

        # Track last activity summary and surface it in the status bar
        if text.startswith("[activity] "):
            if not hasattr(self, '_last_activity'):
                self._last_activity = {}
            self._last_activity[tab_target.lower()] = text
            try:
                self.SetStatusText(f"{tab_target}: {text}")
            except Exception:
                pass

        self._handle_message_sound(target, sender, text)
        self._handle_message_tts(target, sender, text)

    def _handle_message_sound(self, target, sender, text):
        # Optional sounds (safe no-op if files missing)
        try:
            snd_cfg = self.settings.get('sounds', {})
            if snd_cfg.get('enabled'):
                nick = self.settings.get('nick', '')
                is_pm = target.lower() == (self.irc.nick or "").lower()
                # Notices: play configured notice sound and skip regular message sound
                if text.startswith('[notice] '):
                    self._play_sound(snd_cfg.get('notice', ''))
                elif not is_pm and nick and nick.lower() in text.lower():
                    # Mentions only apply to channel messages
                    self._play_sound(snd_cfg.get('mention', ''))
                else:
                    if is_pm:
                        # Prefer private message sound, fallback to generic
                        self._play_sound(snd_cfg.get('message_private', '') or snd_cfg.get('message', ''))
                    else:
                        # Prefer channel message sound, fallback to generic
                        self._play_sound(snd_cfg.get('message_channel', '') or snd_cfg.get('message', ''))
        except Exception:
            pass

        # Experimental beep on receive (skip activity summaries)
        try:
            if self._beeps_enabled and not text.startswith('[activity] '):
                self._play_beep('recv')
        except Exception:
            pass

    def _handle_message_tts(self, target, sender, text):
        # Text-to-speech for incoming messages
        try:
            tts_cfg = self._get_tts_cfg()
            if tts_cfg.get('enabled'):
                nick = self.settings.get('nick', '')
                is_pm = target.lower() == (self.irc.nick or "").lower()
                # Notices: speak as notice when enabled
                if text.startswith('[notice] ') and tts_cfg.get('events',{}).get('notice'):
                    msg = text[len('[notice] '):]
                    if is_pm:
                        self._tts_speak(f"Notice from {sender}: {msg}")
                    else:
                        self._tts_speak(f"Notice from {sender} in {target}: {msg}")
                # Mentions in channel
                elif (not is_pm) and nick and nick.lower() in text.lower() and tts_cfg.get('events',{}).get('mention'):
                    self._tts_speak(f"Mentioned by {sender} in {target}: {text}")
                elif is_pm and tts_cfg.get('events',{}).get('private_message'):
                    self._tts_speak(f"Private message from {sender}: {text}")
                elif (not is_pm) and tts_cfg.get('events',{}).get('channel_message'):
                    self._tts_speak(f"{sender} in {target}: {text}")
        except Exception:
            pass

    def _handle_status_sound(self, text):
        # Play notice sound only for NOTICEs, never for CTCP, to avoid spam
        try:
            if self.settings.get('sounds',{}).get('enabled'):
                is_notice = text.startswith("NOTICE from ")
                is_ctcp = text.startswith("CTCP ")
                if is_notice and not is_ctcp:
                    self._play_sound(self.settings.get('sounds',{}).get('notice',''))
        except Exception:
            pass

    def _handle_status_tts(self, text):
        # TTS for notices
        try:
            tts_cfg = self._get_tts_cfg()
            if tts_cfg.get('enabled') and tts_cfg.get('events',{}).get('notice'):
                is_notice = text.startswith("NOTICE from ")
                is_ctcp = text.startswith("CTCP ")
                if is_notice and not is_ctcp:
                    speak_text = text
                    self._tts_speak(speak_text)
        except Exception:
            pass



    def _on_irc_users(self, target: str, users: list[str]):
        chat = self._chat_for_target(target, create=True)
        chat.set_users(users)

    # Read last activity summary action
    def _on_read_last_activity(self, evt):
        idx = self.notebook.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        target = self.notebook.GetPageText(idx)
        last = getattr(self, '_last_activity', {}).get(target.lower())
        if last:
            try:
                self.SetStatusText(f"{target}: {last}")
            except Exception:
                pass
            # Also echo to transcript to ensure it's read without moving focus
            chat = self.notebook.GetPage(idx)
            chat.append_message(f"* {last}")

    def _on_test_sounds(self, evt):
        # Diagnostic: report and attempt to play configured sounds
        chat = self._chat_for_target("Console", create=True)
        snd_cfg = self.settings.get('sounds', {})
        items = [
            ("message", 'message'),
            ("channel message", 'message_channel'),
            ("private/query message", 'message_private'),
            ("message sent", 'message_sent'),
            ("mention", 'mention'),
            ("notice", 'notice'),
        ]
        chat.append_message("[sound] — Testing configured sounds…")
        any_fail = False
        for label, key in items:
            raw = snd_cfg.get(key, '') or ''
            resolved = self._resolve_sound_path(raw)
            ok = False
            exists = False
            method = ""
            try:
                import os
                exists = bool(resolved and os.path.exists(resolved))
                if exists:
                    ok, method, err = self._play_sound_any(resolved)
                    if not ok and err:
                        chat.append_message(f"[sound] {label}: configured='{raw}' resolved='{resolved}' exists=True ok=False via={method} err={err}")
                        any_fail = True
                        continue
                else:
                    any_fail = True
                chat.append_message(f"[sound] {label}: configured='{raw}' resolved='{resolved or 'N/A'}' exists={exists} ok={ok} via={method or 'n/a'}")
            except Exception as e:
                chat.append_message(f"[sound] {label}: error {e}")
                any_fail = True
        if any_fail:
            self._disable_sounds_due_error("one or more test sounds failed")
        chat.append_message("[sound] — Test complete.")

    # --- Experimental beep tones ---
    def _ensure_beep_files(self):
        if hasattr(self, '_beep_files') and self._beep_files:
            return
        self._beep_files = {}
        try:
            self._beep_files['send'] = self._generate_beep_file([(600, 80), (800, 80), (1000, 100)])
            self._beep_files['recv'] = self._generate_beep_file([(1000, 100), (800, 80), (600, 80)])
        except Exception:
            self._beep_files = {}

    def _generate_beep_file(self, notes: list[tuple[int, int]]):
        import math, wave, struct, tempfile
        framerate = 44100
        amplitude = 16000  # 16-bit mono
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        with wave.open(tmp, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(framerate)
            for freq, dur_ms in notes:
                frames = int(framerate * (dur_ms / 1000.0))
                for i in range(frames):
                    t = i / framerate
                    val = int(amplitude * math.sin(2 * math.pi * freq * t))
                    w.writeframes(struct.pack('<h', val))
        return tmp.name

    def _play_beep(self, kind: str):
        try:
            self._ensure_beep_files()
            path = getattr(self, '_beep_files', {}).get(kind)
            if path:
                self._play_sound_any(path)
        except Exception:
            pass

    def Destroy(self):
        try:
            # Save window geometry and open tabs
            try:
                size = self.GetSize(); pos = self.GetPosition()
                self.settings.setdefault('window', {})['size'] = [size.width, size.height]
                self.settings.setdefault('window', {})['position'] = [pos.x, pos.y]
                self.settings['open_tabs'] = []
                save(self.settings)
            except Exception:
                pass
            self.irc.disconnect()
            try:
                self._tts_clear_queue()
                self._tts_stop_current()
                self._stop_tts_timer()
            except Exception:
                pass
            # Cleanup temp beep files
            try:
                for p in getattr(self, '_beep_files', {}).values():
                    if p:
                        import os
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            except Exception:
                pass
        finally:
            return super().Destroy()

    def Close(self, force=False):
        try:
            # Persist on close as well
            try:
                size = self.GetSize(); pos = self.GetPosition()
                self.settings.setdefault('window', {})['size'] = [size.width, size.height]
                self.settings.setdefault('window', {})['position'] = [pos.x, pos.y]
                self.settings['open_tabs'] = []
                save(self.settings)
            except Exception:
                pass
            self.irc.disconnect()
        finally:
            return super().Close(force)

    def _on_toggle_timestamps(self, evt):
        try:
            self._timestamps = not bool(self._timestamps)
            # Apply to all tabs
            for i in range(self.notebook.GetPageCount()):
                page = self.notebook.GetPage(i)
                if isinstance(page, ChatPanel):
                    page.set_show_timestamps(self._timestamps)
            # Persist setting
            self.settings.setdefault('appearance', {})['timestamps'] = bool(self._timestamps)
            save(self.settings)
            self._on_irc_status(f"Timestamps {'enabled' if self._timestamps else 'disabled'}")
        except Exception:
            pass

    # User list interactions
    def _on_user_list_dclick(self, evt, tab_title: str):
        try:
            lb = evt.GetEventObject()
            sel = lb.GetSelection()
            if sel != wx.NOT_FOUND:
                nick = lb.GetString(sel)
                pm = self._chat_for_target(nick, create=True)
                pm.focus_input()
        except Exception:
            pass

    def _on_user_list_key(self, evt, tab_title: str):
        try:
            key = evt.GetKeyCode()
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                lb = evt.GetEventObject()
                sel = lb.GetSelection()
                if sel != wx.NOT_FOUND:
                    nick = lb.GetString(sel)
                    pm = self._chat_for_target(nick, create=True)
                    pm.focus_input()
                    return  # handled
            # Not handled; propagate
            evt.Skip()
        except Exception:
            try:
                evt.Skip()
            except Exception:
                pass
