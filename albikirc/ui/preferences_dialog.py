import sys
from copy import deepcopy

import wx

from .speech_controls import (
    MAX_SPEECH_RATE, MIN_SPEECH_RATE, SPEECH_EVENTS, SpeechChoicesMixin,
)
from .speech_preview import SpeechPreview

class PreferencesDialog(SpeechChoicesMixin, wx.Dialog):
    def __init__(self, parent, settings, *, speech_page=False):
        super().__init__(parent, title="Preferences")
        self.SetName("Preferences dialog")

        # Current settings
        self._settings = deepcopy(settings or {})
        self._speech_preview = SpeechPreview()

        # Notebook to organize categories
        book = wx.Notebook(self)
        self.book = book

        # Panels per tab
        p_app = wx.Panel(book)
        p_id = wx.Panel(book)
        p_ctcp = wx.Panel(book)
        p_snd = wx.Panel(book)
        p_notif = wx.Panel(book)
        p_conn = wx.Panel(book)
        p_tts = wx.Panel(book)

        # --- Appearance ---
        app = self._settings.get('appearance', {})
        self.chk_timestamps = wx.CheckBox(p_app, label="Show timestamps in chat")
        self.chk_timestamps.SetValue(bool(app.get('timestamps', True)))
        self.chk_timestamps.SetName("Show timestamps checkbox")
        self.chk_timestamps.SetToolTip("Prepend [HH:MM] to each line in transcript")

        interface = self._settings.get('interface', {})
        self.chk_close_channel_list = wx.CheckBox(p_app, label="Close channel list after joining")
        self.chk_close_channel_list.SetValue(
            bool(interface.get('close_channel_list_on_join', True))
        )
        self.chk_close_channel_list.SetName("Close channel list after joining checkbox")
        self.chk_close_channel_list.SetToolTip(
            "When enabled, the channel list window closes after you join a selected channel"
        )

        self.choice_theme = wx.Choice(p_app, choices=["System", "Light", "Dark"]) 
        theme_val = (app.get('theme') or 'system').lower()
        idx = {"system": 0, "light": 1, "dark": 2}.get(theme_val, 0)
        self.choice_theme.SetSelection(idx)
        self.choice_theme.SetName("Theme choice")
        self.choice_theme.SetToolTip("Choose a light or dark theme, or follow the system")

        # --- CTCP ---
        ctcp = self._settings.get('ctcp', {})
        self.chk_ctcp_version = wx.CheckBox(p_ctcp, label="Auto-respond to CTCP VERSION")
        self.chk_ctcp_version.SetName("CTCP VERSION auto-reply checkbox")
        self.chk_ctcp_version.SetToolTip("Automatically reply to CTCP VERSION requests")

        self.chk_ignore_ctcp = wx.CheckBox(p_ctcp, label="Completely ignore CTCP requests")
        self.chk_ignore_ctcp.SetName("Ignore CTCP checkbox")
        self.chk_ignore_ctcp.SetToolTip("Ignore all incoming CTCP requests")

        self.txt_version = wx.TextCtrl(p_ctcp, value=ctcp.get('version_string', 'albikirc (wxPython)'))
        self.txt_version.SetName("Version string field")
        self.txt_version.SetToolTip("Text reported in CTCP VERSION replies")

        self.chk_ctcp_version.SetValue(ctcp.get('respond_to_ctcp_version', True))
        self.chk_ignore_ctcp.SetValue(ctcp.get('ignore_ctcp', False))

        # --- Nick ---
        self.txt_nick = wx.TextCtrl(p_id, value=self._settings.get('nick', 'guest'))
        self.txt_nick.SetName("Nick field")
        self.txt_nick.SetToolTip("Default nickname to use when connecting")

        # --- Real name ---
        self.txt_realname = wx.TextCtrl(p_id, value=self._settings.get('realname', ''))
        self.txt_realname.SetName("Real name field")
        self.txt_realname.SetToolTip("Optional real name/GEcos used during registration")

        # --- Sounds ---
        snd = self._settings.get('sounds', {})
        self.chk_sounds_enabled = wx.CheckBox(p_snd, label="Enable sounds (optional)")
        self.chk_sounds_enabled.SetValue(snd.get('enabled', False))
        self.chk_sounds_enabled.SetName("Enable sounds checkbox")
        self.chk_sounds_enabled.SetToolTip("Play sounds for messages, mentions, and notices")

        self.txt_sound_message = wx.TextCtrl(p_snd, value=snd.get('message', ''))
        self.txt_sound_message.SetName("Message sound path field")
        self.txt_sound_message.SetToolTip("Path to sound file for messages")

        self.txt_sound_message_channel = wx.TextCtrl(p_snd, value=snd.get('message_channel', ''))
        self.txt_sound_message_channel.SetName("Channel message sound path field")
        self.txt_sound_message_channel.SetToolTip("Path to sound file for messages in channels")

        self.txt_sound_message_private = wx.TextCtrl(p_snd, value=snd.get('message_private', ''))
        self.txt_sound_message_private.SetName("Private/Query message sound path field")
        self.txt_sound_message_private.SetToolTip("Path to sound file for private/direct (query) messages")

        self.txt_sound_message_sent = wx.TextCtrl(p_snd, value=snd.get('message_sent', ''))
        self.txt_sound_message_sent.SetName("Message sent sound path field")
        self.txt_sound_message_sent.SetToolTip("Path to sound file played when you send a message")

        self.txt_sound_mention = wx.TextCtrl(p_snd, value=snd.get('mention', ''))
        self.txt_sound_mention.SetName("Mention sound path field")
        self.txt_sound_mention.SetToolTip("Path to sound file when your nick is mentioned")

        self.txt_sound_notice = wx.TextCtrl(p_snd, value=snd.get('notice', ''))
        self.txt_sound_notice.SetName("Notice sound path field")
        self.txt_sound_notice.SetToolTip("Path to sound file for notices/CTCP")

        # --- Notifications ---
        notif = self._settings.get('notifications', {})
        self.chk_show_join_part = wx.CheckBox(p_notif, label="Show join/part notices in channels")
        self.chk_show_join_part.SetName("Show join/part notices checkbox")
        self.chk_show_join_part.SetToolTip("When enabled, show a short message when users join or leave")
        self.chk_show_join_part.SetValue(bool(notif.get('show_join_part_notices', True)))
        self.chk_show_quit_nick = wx.CheckBox(p_notif, label="Show quit/nick notices in Console")
        self.chk_show_quit_nick.SetName("Show quit/nick notices checkbox")
        self.chk_show_quit_nick.SetToolTip("When enabled, show QUIT and nickname change notices in the Console tab")
        self.chk_show_quit_nick.SetValue(bool(notif.get('show_quit_nick_notices', True)))
        self.chk_activity_summaries = wx.CheckBox(p_notif, label="Compact activity summaries (batch join/part/kick)")
        self.chk_activity_summaries.SetName("Compact activity summaries checkbox")
        self.chk_activity_summaries.SetToolTip("Batch join/part/kick events into a single summary line per interval")
        self.chk_activity_summaries.SetValue(bool(notif.get('activity_summaries', True)))
        self.chk_notices_inline = wx.CheckBox(p_notif, label="Show NOTICEs inline in tabs (instead of Console)")
        self.chk_notices_inline.SetName("Show notices inline checkbox")
        self.chk_notices_inline.SetToolTip("When enabled, NOTICE messages to a channel or you appear in that tab; when disabled, they appear in the Console status only")
        self.chk_notices_inline.SetValue(bool(notif.get('notices_inline', True)))
        self.spin_activity_window = wx.SpinCtrl(p_notif, min=1, max=120, initial=int(notif.get('activity_window_seconds', 10)))
        self.spin_activity_window.SetName("Activity summary window seconds")
        self.spin_activity_window.SetToolTip("Number of seconds to batch activity before summarizing")

        # --- Connection (TCP keepalive) ---
        conn = self._settings.get('connection', {})
        self.chk_auto_reconnect = wx.CheckBox(p_conn, label="Reconnect automatically")
        self.chk_auto_reconnect.SetName("Automatic reconnect checkbox")
        self.chk_auto_reconnect.SetToolTip("Reconnect after an unexpected connection loss")
        self.chk_auto_reconnect.SetValue(bool(conn.get('auto_reconnect', True)))

        self.chk_auto_rejoin = wx.CheckBox(p_conn, label="Rejoin channels after reconnecting")
        self.chk_auto_rejoin.SetName("Automatic channel rejoin checkbox")
        self.chk_auto_rejoin.SetToolTip("Rejoin channels that were open before connection loss")
        self.chk_auto_rejoin.SetValue(bool(conn.get('auto_rejoin', True)))

        self.chk_tcp_keepalive = wx.CheckBox(p_conn, label="Enable TCP keepalive")
        self.chk_tcp_keepalive.SetName("Enable TCP keepalive checkbox")
        self.chk_tcp_keepalive.SetToolTip("Send periodic TCP probes to keep idle connections alive")
        self.chk_tcp_keepalive.SetValue(bool(conn.get('tcp_keepalive_enabled', True)))

        self.spin_tcp_idle = wx.SpinCtrl(p_conn, min=10, max=7200, initial=int(conn.get('tcp_keepalive_idle', 120)))
        self.spin_tcp_idle.SetName("TCP keepalive idle seconds")
        self.spin_tcp_idle.SetToolTip("Seconds of idleness before sending keepalive probes")

        self.spin_tcp_interval = wx.SpinCtrl(p_conn, min=5, max=600, initial=int(conn.get('tcp_keepalive_interval', 30)))
        self.spin_tcp_interval.SetName("TCP keepalive interval seconds")
        self.spin_tcp_interval.SetToolTip("Seconds between TCP keepalive probes")

        self.spin_tcp_count = wx.SpinCtrl(p_conn, min=1, max=10, initial=int(conn.get('tcp_keepalive_count', 4)))
        self.spin_tcp_count.SetName("TCP keepalive probe count")
        self.spin_tcp_count.SetToolTip("Number of failed probes before the OS drops the connection")

        # --- Text to Speech ---
        tts_cfg = self._settings.get('tts', {}) or {}
        self.chk_tts_enabled = wx.CheckBox(p_tts, label="Enable text-to-speech")
        self.chk_tts_enabled.SetName("Enable text-to-speech")
        self.chk_tts_enabled.SetValue(bool(tts_cfg.get('enabled', False)))
        self.chk_tts_enabled.SetToolTip("Speak selected events using system text-to-speech")
        self.chk_tts_interrupt = wx.CheckBox(p_tts, label="Interrupt speech with newer messages")
        self.chk_tts_interrupt.SetName("Interrupt speech with newer messages")
        self.chk_tts_interrupt.SetToolTip("Stop any ongoing speech when another event needs to speak")
        self.chk_tts_interrupt.SetValue(bool(tts_cfg.get('interrupt', False)))
        self.chk_tts_voiceover = wx.CheckBox(p_tts, label="Experimental: announce via VoiceOver when available (macOS)")
        self.chk_tts_voiceover.SetName("Use VoiceOver announcements")
        self.chk_tts_voiceover.SetToolTip("Use VoiceOver announcements instead of the app speech voice when available. Requires VoiceOver and AppleScript control to be enabled.")
        self.chk_tts_voiceover.SetValue(bool(tts_cfg.get('use_voiceover', False)))
        if sys.platform != 'darwin':
            self.chk_tts_voiceover.Disable()

        # Voice selection: replace dropdown with Choose Voice… (grouped submenu)
        sel_voice = str(tts_cfg.get('voice', 'Default'))
        self._last_tts_voice = sel_voice or 'Default'
        self.txt_tts_voice = wx.StaticText(p_tts, label=self._last_tts_voice or 'Default')
        self.txt_tts_voice.SetName("Current speech voice")
        self.btn_tts_choose = wx.Button(p_tts, label="Choose voice…")
        self.btn_tts_choose.SetName("Choose voice")
        self.Bind(wx.EVT_BUTTON, self._on_tts_choose_voice, self.btn_tts_choose)

        self._tts_languages = self._speech_languages()
        self.choice_tts_language = wx.Choice(
            p_tts, choices=[self._friendly_lang_label(code) for code in self._tts_languages]
        )
        self.choice_tts_language.SetName("Speech language")
        self._select_tts_language(str(tts_cfg.get('language', '') or ''))
        self.choice_tts_language.Bind(wx.EVT_CHOICE, self._on_tts_language)
        self._update_tts_voice_label()

        # Speech rate (WPM)
        try:
            default_wpm = int(tts_cfg.get('rate_wpm', 180))
        except Exception:
            default_wpm = 180
        self.spin_tts_wpm = wx.SpinCtrl(
            p_tts, min=MIN_SPEECH_RATE, max=MAX_SPEECH_RATE, initial=default_wpm
        )
        self.spin_tts_wpm.SetName("Speaking rate (words per minute)")
        self.spin_tts_wpm.SetToolTip("Approximate speaking rate in words per minute")

        # Event checkboxes
        ev = tts_cfg.get('events', {}) or {}
        self.chk_tts_channel = wx.CheckBox(p_tts, label=dict(SPEECH_EVENTS)["channel_message"])
        self.chk_tts_channel.SetValue(bool(ev.get('channel_message', False)))
        self.chk_tts_channel.SetName("Channel messages")
        self.chk_tts_private = wx.CheckBox(p_tts, label=dict(SPEECH_EVENTS)["private_message"])
        self.chk_tts_private.SetValue(bool(ev.get('private_message', False)))
        self.chk_tts_private.SetName("Private messages")
        self.chk_tts_mentions = wx.CheckBox(p_tts, label=dict(SPEECH_EVENTS)["mention"])
        self.chk_tts_mentions.SetValue(bool(ev.get('mention', True)))
        self.chk_tts_mentions.SetName("Mentions (your nick in channel)")
        self.chk_tts_notices = wx.CheckBox(p_tts, label=dict(SPEECH_EVENTS)["notice"])
        self.chk_tts_notices.SetValue(bool(ev.get('notice', False)))
        self.chk_tts_notices.SetName("Notices")

        # Layout per tab
        # Appearance
        s_app = wx.BoxSizer(wx.VERTICAL)
        help_app = wx.StaticText(p_app, label="Choose theme and whether to show timestamps in chat.")
        try:
            help_app.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_app.GetFont()
            f.MakeSmaller()
            help_app.SetFont(f)
        except Exception:
            pass
        s_app.Add(help_app, 0, wx.ALL, 6)
        rowt = wx.BoxSizer(wx.HORIZONTAL)
        rowt.Add(wx.StaticText(p_app, label="Theme:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        rowt.Add(self.choice_theme, 0)
        s_app.Add(rowt, 0, wx.EXPAND | wx.ALL, 6)
        s_app.Add(self.chk_timestamps, 0, wx.ALL, 6)
        s_app.Add(self.chk_close_channel_list, 0, wx.ALL, 6)
        p_app.SetSizer(s_app)

        # Identity
        s_id = wx.BoxSizer(wx.VERTICAL)
        help_id = wx.StaticText(p_id, label="Set your default nickname used for new connections.")
        try:
            help_id.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_id.GetFont()
            f.MakeSmaller()
            help_id.SetFont(f)
        except Exception:
            pass
        s_id.Add(help_id, 0, wx.ALL, 6)
        rown = wx.BoxSizer(wx.HORIZONTAL)
        rown.Add(wx.StaticText(p_id, label="Nick:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        rown.Add(self.txt_nick, 1, wx.EXPAND)
        s_id.Add(rown, 0, wx.EXPAND | wx.ALL, 8)
        rowr = wx.BoxSizer(wx.HORIZONTAL)
        rowr.Add(wx.StaticText(p_id, label="Real name (optional):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        rowr.Add(self.txt_realname, 1, wx.EXPAND)
        s_id.Add(rowr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        p_id.SetSizer(s_id)

        # CTCP
        s_ctcp = wx.BoxSizer(wx.VERTICAL)
        help_ctcp = wx.StaticText(p_ctcp, label="Control CTCP behavior and the VERSION string reported to others.")
        try:
            help_ctcp.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_ctcp.GetFont()
            f.MakeSmaller()
            help_ctcp.SetFont(f)
        except Exception:
            pass
        s_ctcp.Add(help_ctcp, 0, wx.ALL, 6)
        s_ctcp.Add(self.chk_ctcp_version, 0, wx.ALL, 6)
        s_ctcp.Add(self.chk_ignore_ctcp, 0, wx.ALL, 6)
        rowv = wx.BoxSizer(wx.HORIZONTAL)
        rowv.Add(wx.StaticText(p_ctcp, label="Version string to report:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        rowv.Add(self.txt_version, 1, wx.EXPAND)
        s_ctcp.Add(rowv, 0, wx.EXPAND | wx.ALL, 6)
        p_ctcp.SetSizer(s_ctcp)

        # Sounds
        s_snd = wx.BoxSizer(wx.VERTICAL)
        help_snd = wx.StaticText(p_snd, label="Enable sounds and choose files for events. Use Test to verify.")
        try:
            help_snd.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_snd.GetFont()
            f.MakeSmaller()
            help_snd.SetFont(f)
        except Exception:
            pass
        s_snd.Add(help_snd, 0, wx.ALL, 6)
        s_snd.Add(self.chk_sounds_enabled, 0, wx.ALL, 6)

        def labeled_row_with_browse(parent, label, ctrl, on_browse, on_test=None):
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
            row.Add(ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
            btn = wx.Button(parent, label="Browse…")
            btn.SetName(f"Browse button for {label}")
            btn.SetToolTip("Browse for a sound file")
            row.Add(btn, 0)
            self.Bind(wx.EVT_BUTTON, on_browse, btn)
            if on_test is not None:
                tbtn = wx.Button(parent, label="Test")
                tbtn.SetName(f"Test button for {label}")
                tbtn.SetToolTip("Play the selected sound to test it")
                row.Add(tbtn, 0, wx.LEFT, 6)
                self.Bind(wx.EVT_BUTTON, on_test, tbtn)
            return row

        s_snd.Add(labeled_row_with_browse(p_snd, "Message sound (path):", self.txt_sound_message, self._browse_message, self._test_message), 0, wx.EXPAND | wx.ALL, 6)
        s_snd.Add(labeled_row_with_browse(p_snd, "Channel message sound (path):", self.txt_sound_message_channel, self._browse_message_channel, self._test_message_channel), 0, wx.EXPAND | wx.ALL, 6)
        s_snd.Add(labeled_row_with_browse(p_snd, "Private/Query message sound (path):", self.txt_sound_message_private, self._browse_message_private, self._test_message_private), 0, wx.EXPAND | wx.ALL, 6)
        s_snd.Add(labeled_row_with_browse(p_snd, "Message sent sound (path):", self.txt_sound_message_sent, self._browse_message_sent, self._test_message_sent), 0, wx.EXPAND | wx.ALL, 6)
        s_snd.Add(labeled_row_with_browse(p_snd, "Mention sound (path):", self.txt_sound_mention, self._browse_mention, self._test_mention), 0, wx.EXPAND | wx.ALL, 6)
        s_snd.Add(labeled_row_with_browse(p_snd, "Notice sound (path):", self.txt_sound_notice, self._browse_notice, self._test_notice), 0, wx.EXPAND | wx.ALL, 6)
        note = wx.StaticText(p_snd, label=(
            "Note: If any configured sound fails to resolve or play, "
            "sounds are disabled automatically. Fix the paths and re-enable "
            "sounds in Preferences."
        ))
        note.SetName("Sounds auto-disable note")
        s_snd.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Experimental beeps
        beeps = (self._settings.get('beeps') or {})
        self.chk_beeps_enabled = wx.CheckBox(p_snd, label="Experimental: play beep tones for events (ascending on send, descending on receive)")
        self.chk_beeps_enabled.SetName("Experimental beep tones checkbox")
        self.chk_beeps_enabled.SetToolTip("When enabled, the app plays short synthesized beeps for common events")
        self.chk_beeps_enabled.SetValue(bool(beeps.get('enabled', False)))
        s_snd.Add(self.chk_beeps_enabled, 0, wx.ALL, 6)
        p_snd.SetSizer(s_snd)

        # Notifications group
        s_notif = wx.BoxSizer(wx.VERTICAL)
        help_notif = wx.StaticText(p_notif, label="Choose what notices to show and the activity summary window.")
        try:
            help_notif.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_notif.GetFont()
            f.MakeSmaller()
            help_notif.SetFont(f)
        except Exception:
            pass
        s_notif.Add(help_notif, 0, wx.ALL, 6)
        s_notif.Add(self.chk_show_join_part, 0, wx.ALL, 6)
        s_notif.Add(self.chk_show_quit_nick, 0, wx.ALL, 6)
        s_notif.Add(self.chk_activity_summaries, 0, wx.ALL, 6)
        s_notif.Add(self.chk_notices_inline, 0, wx.ALL, 6)
        row_aw = wx.BoxSizer(wx.HORIZONTAL)
        row_aw.Add(wx.StaticText(p_notif, label="Summary window (seconds):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_aw.Add(self.spin_activity_window, 0)
        s_notif.Add(row_aw, 0, wx.ALL, 6)
        p_notif.SetSizer(s_notif)

        # Connection group
        s_conn = wx.BoxSizer(wx.VERTICAL)
        help_conn = wx.StaticText(
            p_conn,
            label="Recover from connection loss and configure TCP keepalive probes.",
        )
        try:
            help_conn.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_conn.GetFont()
            f.MakeSmaller()
            help_conn.SetFont(f)
        except Exception:
            pass
        s_conn.Add(help_conn, 0, wx.ALL, 6)
        s_conn.Add(self.chk_auto_reconnect, 0, wx.ALL, 6)
        s_conn.Add(self.chk_auto_rejoin, 0, wx.ALL, 6)
        s_conn.Add(self.chk_tcp_keepalive, 0, wx.ALL, 6)
        row_idle = wx.BoxSizer(wx.HORIZONTAL)
        row_idle.Add(wx.StaticText(p_conn, label="Keepalive idle (seconds):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_idle.Add(self.spin_tcp_idle, 0)
        s_conn.Add(row_idle, 0, wx.ALL, 6)
        row_int = wx.BoxSizer(wx.HORIZONTAL)
        row_int.Add(wx.StaticText(p_conn, label="Keepalive interval (seconds):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_int.Add(self.spin_tcp_interval, 0)
        s_conn.Add(row_int, 0, wx.ALL, 6)
        row_cnt = wx.BoxSizer(wx.HORIZONTAL)
        row_cnt.Add(wx.StaticText(p_conn, label="Keepalive probe count:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_cnt.Add(self.spin_tcp_count, 0)
        s_conn.Add(row_cnt, 0, wx.ALL, 6)
        p_conn.SetSizer(s_conn)

        # Text to Speech group
        s_tts = wx.BoxSizer(wx.VERTICAL)
        help_tts = wx.StaticText(p_tts, label="Speak incoming events using the selected system voice.")
        try:
            help_tts.SetForegroundColour(wx.Colour(90, 90, 90))
            f = help_tts.GetFont()
            f.MakeSmaller()
            help_tts.SetFont(f)
        except Exception:
            pass
        s_tts.Add(help_tts, 0, wx.ALL, 6)
        s_tts.Add(self.chk_tts_enabled, 0, wx.ALL, 6)
        row_language = wx.BoxSizer(wx.HORIZONTAL)
        row_language.Add(wx.StaticText(p_tts, label="Language:"), 0,
                         wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_language.Add(self.choice_tts_language, 1)
        s_tts.Add(row_language, 0, wx.EXPAND | wx.ALL, 6)
        row_voice = wx.BoxSizer(wx.HORIZONTAL)
        row_voice.Add(wx.StaticText(p_tts, label="Voice:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_voice.Add(self.txt_tts_voice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_voice.Add(self.btn_tts_choose, 0)
        s_tts.Add(row_voice, 0, wx.EXPAND | wx.ALL, 6)
        row_rate = wx.BoxSizer(wx.HORIZONTAL)
        row_rate.Add(
            wx.StaticText(p_tts, label="Speaking rate (words per minute):"),
            0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6
        )
        row_rate.Add(self.spin_tts_wpm, 0)
        s_tts.Add(row_rate, 0, wx.ALL, 6)
        # Test speech button
        self.btn_tts_test = wx.Button(p_tts, label="Test speech")
        self.btn_tts_test.SetName("Test speech")
        self.btn_tts_test.SetToolTip("Speak a sample line using the current voice and rate")
        s_tts.Add(self.btn_tts_test, 0, wx.ALL, 6)
        self.Bind(wx.EVT_BUTTON, self._on_tts_test, self.btn_tts_test)
        s_tts.Add(wx.StaticText(p_tts, label="Speak:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        s_tts.Add(self.chk_tts_mentions, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        s_tts.Add(self.chk_tts_channel, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        s_tts.Add(self.chk_tts_private, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        s_tts.Add(self.chk_tts_notices, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 12)
        s_tts.Add(self.chk_tts_interrupt, 0, wx.ALL, 6)
        s_tts.Add(self.chk_tts_voiceover, 0, wx.ALL, 6)
        p_tts.SetSizer(s_tts)
        speech_controls = [
            self.chk_tts_enabled, self.choice_tts_language, self.btn_tts_choose,
            self.spin_tts_wpm, self.btn_tts_test, self.chk_tts_mentions,
            self.chk_tts_channel, self.chk_tts_private, self.chk_tts_notices,
            self.chk_tts_interrupt, self.chk_tts_voiceover,
        ]
        for previous, current in zip(speech_controls, speech_controls[1:]):
            current.MoveAfterInTabOrder(previous)

        # Add tabs
        book.AddPage(p_app, "Appearance")
        book.AddPage(p_id, "Identity")
        book.AddPage(p_ctcp, "CTCP")
        book.AddPage(p_snd, "Sounds")
        book.AddPage(p_notif, "Notifications")
        book.AddPage(p_conn, "Connection")
        book.AddPage(p_tts, "Text to Speech")
        if speech_page:
            book.SetSelection(book.GetPageCount() - 1)

        # Dialog layout
        top = wx.BoxSizer(wx.VERTICAL)
        top.Add(book, 1, wx.EXPAND | wx.ALL, 6)
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        top.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(top)

    def _on_tts_choose_voice(self, evt):
        menu = wx.Menu()
        try:
            self._populate_speech_voices(menu, self._speech_settings(), self._set_tts_voice)
            self.PopupMenu(menu)
        finally:
            menu.Destroy()

    def _speech_settings(self):
        return {
            'voice': self._last_tts_voice,
            'language': self._settings.get('tts', {}).get('language', ''),
        }

    def _set_tts_voice(self, name, lang=None):
        self._last_tts_voice = str(name or 'Default')
        if lang is not None:
            self._settings.setdefault('tts', {})['language'] = lang
            self._select_tts_language(lang)
        self._update_tts_voice_label()

    def _update_tts_voice_label(self):
        language = self._settings.get('tts', {}).get('language', '')
        label = self._last_tts_voice
        if language:
            label += f" ({self._friendly_lang_label(language)})"
        self.txt_tts_voice.SetLabel(label)
        self.btn_tts_choose.SetName(f"Choose voice, current voice: {label}")
        self.Layout()

    def _select_tts_language(self, language):
        if language not in self._tts_languages:
            self._tts_languages.append(language)
            self.choice_tts_language.Append(self._friendly_lang_label(language))
        self.choice_tts_language.SetSelection(self._tts_languages.index(language))

    def _on_tts_language(self, evt):
        language = self._tts_languages[self.choice_tts_language.GetSelection()]
        self._settings.setdefault('tts', {})['language'] = language
        self._update_tts_voice_label()

    def _browse(self, target_ctrl):
        with wx.FileDialog(self, message="Choose a sound file",
                           wildcard="Sound files (*.wav;*.aiff;*.aif)|*.wav;*.aiff;*.aif|All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                target_ctrl.SetValue(path)

    def _browse_message(self, evt):
        self._browse(self.txt_sound_message)

    def _browse_message_channel(self, evt):
        self._browse(self.txt_sound_message_channel)

    def _browse_message_private(self, evt):
        self._browse(self.txt_sound_message_private)

    def _browse_message_sent(self, evt):
        self._browse(self.txt_sound_message_sent)

    def _browse_mention(self, evt):
        self._browse(self.txt_sound_mention)

    def _browse_notice(self, evt):
        self._browse(self.txt_sound_notice)

    # --- Per-field testing helpers ---
    def _resolve_sound_path(self, path: str) -> str:
        try:
            if not path:
                return ""
            import os
            p = os.path.expanduser(os.path.expandvars(path))
            if os.path.exists(p):
                return p
        except Exception:
            pass
        return ""

    def _play_sound_any(self, resolved_path: str) -> tuple[bool, str, str | None]:
        try:
            if not resolved_path:
                return (False, "none", None)
            try:
                import wx
                SoundCls = getattr(wx, 'Sound', None) or getattr(wx.adv, 'Sound', None)
                if SoundCls is not None:
                    snd = SoundCls(resolved_path)
                    if hasattr(snd, 'IsOk') and not snd.IsOk():
                        return (False, "wx.Sound", None)
                    snd.Play(getattr(wx, 'SOUND_ASYNC', 0))
                    return (True, "wx.Sound", None)
            except Exception as e:
                _ = str(e)
            import subprocess
            if sys.platform.startswith('win'):
                try:
                    import winsound
                    winsound.PlaySound(resolved_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return (True, "winsound", None)
                except Exception as e:
                    return (False, "winsound", str(e))
            elif sys.platform == 'darwin':
                try:
                    subprocess.Popen(["afplay", resolved_path])
                    return (True, "afplay", None)
                except Exception as e:
                    return (False, "afplay", str(e))
            else:
                try:
                    subprocess.Popen(["paplay", resolved_path])
                    return (True, "paplay", None)
                except Exception as e1:
                    try:
                        subprocess.Popen(["aplay", resolved_path])
                        return (True, "aplay", None)
                    except Exception as e2:
                        return (False, "paplay/aplay", f"{e1}; {e2}")
        except Exception as e:
            return (False, "error", str(e))

    def _test_sound(self, ctrl: wx.TextCtrl, label: str):
        raw = ctrl.GetValue().strip()
        resolved = self._resolve_sound_path(raw)
        if not resolved:
            wx.MessageBox(f"{label}: file not found. Check the path.", "Test Sound", wx.OK | wx.ICON_WARNING)
            return
        ok, method, err = self._play_sound_any(resolved)
        if ok:
            wx.MessageBox(f"{label}: ok via {method}", "Test Sound", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox(f"{label}: playback failed via {method}{' — ' + err if err else ''}", "Test Sound", wx.OK | wx.ICON_ERROR)

    def _test_message(self, evt):
        self._test_sound(self.txt_sound_message, "Message sound")

    def _test_message_channel(self, evt):
        self._test_sound(self.txt_sound_message_channel, "Channel message sound")

    def _test_message_private(self, evt):
        self._test_sound(self.txt_sound_message_private, "Private message sound")

    def _test_message_sent(self, evt):
        self._test_sound(self.txt_sound_message_sent, "Message sent sound")

    def _test_mention(self, evt):
        self._test_sound(self.txt_sound_mention, "Mention sound")

    def _test_notice(self, evt):
        self._test_sound(self.txt_sound_notice, "Notice sound")

    def _on_tts_test(self, evt):
        self._speech_preview.speak(self.values['tts'])

    def Destroy(self):
        self._speech_preview.stop()
        return super().Destroy()

    @property
    def values(self):
        return {
            'nick': self.txt_nick.GetValue().strip(),
            'realname': self.txt_realname.GetValue().strip(),
            'appearance': {
                'timestamps': self.chk_timestamps.GetValue(),
                'theme': ["system", "light", "dark"][max(0, self.choice_theme.GetSelection())],
            },
            'interface': {
                'close_channel_list_on_join': self.chk_close_channel_list.GetValue(),
            },
            'ctcp': {
                'respond_to_ctcp_version': self.chk_ctcp_version.GetValue(),
                'ignore_ctcp': self.chk_ignore_ctcp.GetValue(),
                'version_string': self.txt_version.GetValue().strip() or 'albikirc (wxPython)',
            },
            'notifications': {
                'show_join_part_notices': self.chk_show_join_part.GetValue(),
                'show_quit_nick_notices': self.chk_show_quit_nick.GetValue(),
                'activity_summaries': self.chk_activity_summaries.GetValue(),
                'activity_window_seconds': int(self.spin_activity_window.GetValue()),
                'notices_inline': self.chk_notices_inline.GetValue(),
            },
            'connection': {
                'auto_reconnect': self.chk_auto_reconnect.GetValue(),
                'auto_rejoin': self.chk_auto_rejoin.GetValue(),
                'tcp_keepalive_enabled': self.chk_tcp_keepalive.GetValue(),
                'tcp_keepalive_idle': int(self.spin_tcp_idle.GetValue()),
                'tcp_keepalive_interval': int(self.spin_tcp_interval.GetValue()),
                'tcp_keepalive_count': int(self.spin_tcp_count.GetValue()),
            },
            'sounds': {
                'enabled': self.chk_sounds_enabled.GetValue(),
                'message': self.txt_sound_message.GetValue().strip(),
                'message_channel': self.txt_sound_message_channel.GetValue().strip(),
                'message_private': self.txt_sound_message_private.GetValue().strip(),
                'message_sent': self.txt_sound_message_sent.GetValue().strip(),
                'mention': self.txt_sound_mention.GetValue().strip(),
                'notice': self.txt_sound_notice.GetValue().strip(),
            },
            'beeps': {
                'enabled': self.chk_beeps_enabled.GetValue(),
            },
            'tts': {
                'enabled': self.chk_tts_enabled.GetValue(),
                'interrupt': self.chk_tts_interrupt.GetValue(),
                'voice': (getattr(self, '_last_tts_voice', '') or 'Default').strip(),
                # Use the dialog-local language until OK is pressed
                'language': str((self._settings.get('tts', {}) or {}).get('language', '')),
                'rate_wpm': int(self.spin_tts_wpm.GetValue()),
                'use_voiceover': self.chk_tts_voiceover.GetValue(),
                'events': {
                    'channel_message': self.chk_tts_channel.GetValue(),
                    'private_message': self.chk_tts_private.GetValue(),
                    'mention': self.chk_tts_mentions.GetValue(),
                    'notice': self.chk_tts_notices.GetValue(),
                }
            }
        }
