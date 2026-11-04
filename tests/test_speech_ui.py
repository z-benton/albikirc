"""Native wx checks; skipped when wx or a desktop display is unavailable."""

from copy import deepcopy
import os
import sys
import unittest
from unittest.mock import Mock, patch

try:
    import wx
except ImportError:
    wx = None


HAS_DESKTOP = sys.platform in ("darwin", "win32") or bool(os.environ.get("DISPLAY"))
VOICES = [
    {"name": "Alex", "lang": "en-US", "eloquence": False},
    {"name": "Thomas", "lang": "fr-FR", "eloquence": False},
    {"name": "Eddy", "lang": "en-US", "eloquence": True},
    {"name": "Eddy", "lang": "en-GB", "eloquence": True},
]


@unittest.skipUnless(wx is not None and HAS_DESKTOP, "requires wx and a desktop display")
class SpeechUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from albikirc.ui.main_frame import MainFrame
        from albikirc.ui.preferences_dialog import PreferencesDialog

        cls.app = wx.GetApp() or wx.App(False)
        cls.frame_class = MainFrame
        cls.dialog_class = PreferencesDialog

    def setUp(self):
        self.discovery = patch(
            "albikirc.ui.speech_controls.SpeechChoicesMixin._tts_list_voices_detailed",
            return_value=VOICES,
        )
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        save_patch = patch("albikirc.ui.main_frame.save")
        self.save = save_patch.start()
        self.addCleanup(save_patch.stop)
        self.settings = {"tts": {"enabled": False, "voice": "Alex", "language": "en-US"}}
        self.frame = self.frame_class(None, settings=self.settings)
        self.addCleanup(self.frame.Destroy)

    def speech_menu(self):
        bar = self.frame.GetMenuBar()
        return next(
            bar.GetMenu(i) for i in range(bar.GetMenuCount()) if bar.GetMenuLabelText(i) == "Speech"
        )

    def submenu(self, menu, label):
        return next(
            item.GetSubMenu() for item in menu.GetMenuItems() if item.GetItemLabelText() == label
        )

    def activate(self, menu, label, checked=None):
        item = next(item for item in menu.GetMenuItems() if item.GetItemLabelText() == label)
        event = wx.CommandEvent(wx.EVT_MENU.typeId, item.GetId())
        if checked is not None:
            event.SetInt(int(checked))
        menu.ProcessEvent(event)
        self.app.ProcessPendingEvents()

    def test_preferences_cancel_keeps_voice_and_language_unchanged(self):
        before = deepcopy(self.settings)
        dialog = self.dialog_class(self.frame, self.settings, speech_page=True)
        try:
            dialog._set_tts_voice("Eddy", "en-GB")
            self.assertEqual(self.settings, before)
            self.assertEqual(dialog.values["tts"]["voice"], "Eddy")
            self.assertEqual(dialog.values["tts"]["language"], "en-GB")
            self.assertEqual(dialog.choice_tts_language.GetStringSelection(), "English (UK)")
            self.assertIn("Eddy (English (UK))", dialog.btn_tts_choose.GetName())
            page = dialog.book.GetSelection()
            self.assertEqual(dialog.book.GetPageText(page), "Text to Speech")
        finally:
            dialog.Destroy()
        self.assertEqual(self.settings, before)

    def test_menu_message_toggle_persists_and_refreshes_checkmark(self):
        events = self.submenu(self.speech_menu(), "Speak")
        self.activate(events, "Private messages", checked=True)
        self.assertTrue(self.settings["tts"]["events"]["private_message"])
        events = self.submenu(self.speech_menu(), "Speak")
        item = next(
            item for item in events.GetMenuItems() if item.GetItemLabelText() == "Private messages"
        )
        self.assertTrue(item.IsChecked())
        self.save.assert_called_once_with(self.settings)

    def test_language_menu_filters_voice_choices(self):
        languages = self.submenu(self.speech_menu(), "Language")
        self.activate(languages, "French (France)")
        self.assertEqual(self.settings["tts"]["language"], "fr-FR")
        voices = self.submenu(self.speech_menu(), "Voice")
        self.assertEqual(
            [item.GetItemLabelText() for item in voices.GetMenuItems()],
            ["Default", "Eloquence", "Thomas"],
        )

    def test_voice_checkmarks_do_not_select_first_voice_in_each_submenu(self):
        self.settings["tts"].update(voice="Thomas", language="fr-FR")
        self.frame._refresh_speech_menu()
        voices = self.submenu(self.speech_menu(), "Voice")
        self.assertFalse(voices.FindItemByPosition(0).IsChecked())
        self.assertTrue(voices.FindItemByPosition(2).IsChecked())
        eloquence = self.submenu(voices, "Eloquence")
        for language in eloquence.GetMenuItems():
            self.assertFalse(language.GetSubMenu().FindItemByPosition(0).IsChecked())

    def test_preferences_ok_refreshes_menu_state(self):
        dialog = self.dialog_class(self.frame, self.settings)
        dialog.chk_tts_enabled.SetValue(True)
        dialog.chk_tts_private.SetValue(True)
        dialog._set_tts_voice("Thomas", "fr-FR")
        with (
            patch("albikirc.ui.main_frame.PreferencesDialog", return_value=dialog),
            patch.object(dialog, "ShowModal", return_value=wx.ID_OK),
            patch.object(self.frame, "_tts_init"),
        ):
            self.frame._on_preferences(None)
        menu = self.speech_menu()
        self.assertTrue(menu.FindItemByPosition(0).IsChecked())
        voices = self.submenu(menu, "Voice")
        self.assertTrue(voices.FindItemByPosition(2).IsChecked())

    def test_menu_rate_accept_and_cancel(self):
        dialog = Mock()
        dialog.__enter__ = Mock(return_value=dialog)
        dialog.__exit__ = Mock(return_value=False)
        dialog.ShowModal.return_value = wx.ID_CANCEL
        with (
            patch("albikirc.ui.main_frame.wx.Dialog", return_value=dialog),
            patch("albikirc.ui.main_frame.wx.BoxSizer"),
            patch("albikirc.ui.main_frame.wx.StaticText"),
            patch("albikirc.ui.main_frame.wx.SpinCtrl") as spin,
        ):
            spin.return_value.GetValue.return_value = 300
            self.frame._on_tts_rate(None)
            self.assertNotIn("rate_wpm", self.settings["tts"])
            dialog.ShowModal.return_value = wx.ID_OK
            self.frame._on_tts_rate(None)
        self.app.ProcessPendingEvents()
        self.assertEqual(self.settings["tts"]["rate_wpm"], 300)

    def test_both_preview_actions_work_with_automatic_speech_disabled(self):
        with (
            patch("albikirc.ui.speech_preview.MacSpeechBackend") as backend,
            patch("albikirc.ui.speech_preview.sys.platform", "darwin"),
        ):
            backend.is_available.return_value = True
            backend.return_value.speak.return_value = True
            self.frame._on_tts_test(None)
            backend.return_value.speak.assert_called_once()
            self.assertFalse(self.settings["tts"]["enabled"])
            dialog = self.dialog_class(self.frame, self.settings)
            try:
                dialog.spin_tts_wpm.SetValue(250)
                dialog._on_tts_test(None)
                self.assertEqual(backend.return_value.speak.call_args.kwargs["rate_wpm"], 250)
                self.assertFalse(dialog.values["tts"]["enabled"])
            finally:
                dialog.Destroy()
