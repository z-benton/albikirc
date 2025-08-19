import wx


HELP_TEXT = (
    "Keyboard Shortcuts\n"
    "\n"
    "- Connect: Cmd/Ctrl+N\n"
    "- Connect to Saved: Cmd/Ctrl+Shift+N\n"
    "- Join Channel: Cmd/Ctrl+J\n"
    "- Close Tab: Cmd/Ctrl+W\n"
    "- Preferences: Cmd/Ctrl+,\n"
    "- Focus Message Input: Cmd/Ctrl+Shift+M\n"
    "- Send Message: Enter (with input focused)\n"
    "- Start Private Message: Enter on a selected user (user list)\n"
    "\n"
    "Slash Commands\n"
    "\n"
    "- /join <#channel> — Join a channel. Alias: /j\n"
    "- /part [#channel] [reason] — Leave the current or given channel. Alias: /p\n"
    "- /nick <newnick> — Change your nickname.\n"
    "- /me <action> — Send an action (/me) to the current target.\n"
    "- /msg <nick> <text> — Send a private message. Aliases: /query, /pm\n"
    "- /quit [reason] — Disconnect and close the app.\n"
    "- /notice <target> <text> — Send a NOTICE to a user or channel.\n"
    "- /topic [#chan] [text] — Show or set the topic for a channel.\n"
    "- /whois <nick> — Query WHOIS information for a user.\n"
    "- /raw <line> — Send a raw IRC command.\n"
    "\n"
    "Navigation Tips\n"
    "\n"
    "- Tabs: focus the tab bar to switch between conversations (arrow keys or Ctrl+Tab on some systems).\n"
    "- Chat panel: Tab cycles transcript → input → Send → user list.\n"
    "- In user list: Enter or double-click opens a private message with the selected user.\n"
    "- Connect dialog: All fields are labeled (host, port, nick, TLS, optional SASL and client certificate).\n"
    "- Status messages appear in the status bar at the bottom.\n"
)


class HelpDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Keyboard Shortcuts & Help", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetName("Help dialog")

        txt = wx.TextCtrl(self, value=HELP_TEXT, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        txt.SetName("Help text")
        txt.SetToolTip("Keyboard shortcuts and navigation tips")

        btns = self.CreateButtonSizer(wx.OK)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(txt, 1, wx.EXPAND | wx.ALL, 10)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizerAndFit(sizer)
