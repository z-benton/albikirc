import wx
from datetime import datetime


class ChatPanel(wx.Panel):
    def __init__(self, parent, on_send=None):
        super().__init__(parent)
        self.on_send = on_send
        self.show_timestamps: bool = True
        self._theme: str = "system"  # system|light|dark

        self._build_ui()

    def _build_ui(self):
        self.SetName("Chat panel")

        root = wx.BoxSizer(wx.HORIZONTAL)

        # Left column: transcript + input row
        left = wx.BoxSizer(wx.VERTICAL)

        self.transcript = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        self.transcript.SetName("Chat transcript")
        self.transcript.SetToolTip("Chat transcript")

        input_row = wx.BoxSizer(wx.HORIZONTAL)
        self.input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.input.SetName("Message input")
        self.input.SetToolTip("Type a message or slash command (e.g., /join #channel)")
        self.input.Bind(wx.EVT_TEXT_ENTER, self._on_send_clicked)

        self.send_btn = wx.Button(self, label="Send")
        self.send_btn.SetName("Send button")
        self.send_btn.SetToolTip("Send the message")
        self.send_btn.SetDefault()
        self.send_btn.Bind(wx.EVT_BUTTON, self._on_send_clicked)

        input_row.Add(self.input, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        input_row.Add(self.send_btn, 0)

        left.Add(self.transcript, 1, wx.EXPAND | wx.BOTTOM, 6)
        left.Add(input_row, 0, wx.EXPAND)

        # Right column: user list
        self.user_list = wx.ListBox(self)
        self.user_list.SetName("User list")
        self.user_list.SetToolTip("Users in channel")

        root.Add(left, 1, wx.EXPAND | wx.ALL, 8)
        root.Add(self.user_list, 0, wx.EXPAND | wx.TOP | wx.BOTTOM | wx.RIGHT, 8)

        self.SetSizer(root)

        # Tab order: transcript -> input -> send -> users
        self.input.MoveAfterInTabOrder(self.transcript)
        self.send_btn.MoveAfterInTabOrder(self.input)
        self.user_list.MoveAfterInTabOrder(self.send_btn)

    # Public helpers
    def append_message(self, text: str):
        if self.show_timestamps:
            ts = datetime.now().strftime("%H:%M")
            line = f"[{ts}] {text}"
        else:
            line = text
        self.transcript.AppendText(line + "\n")

    def set_show_timestamps(self, enabled: bool):
        self.show_timestamps = bool(enabled)

    def apply_theme(self, theme: str):
        self._theme = theme
        try:
            if theme == "dark":
                bg = wx.Colour(30, 30, 30)
                fg = wx.Colour(230, 230, 230)
            elif theme == "light":
                bg = wx.NullColour
                fg = wx.NullColour
            else:  # system
                bg = wx.NullColour
                fg = wx.NullColour
            for ctrl in (self.transcript, self.input, self.user_list):
                if bg.IsOk():
                    ctrl.SetBackgroundColour(bg)
                if fg.IsOk():
                    ctrl.SetForegroundColour(fg)
                ctrl.Refresh()
        except Exception:
            pass

    def focus_input(self):
        self.input.SetFocus()
        self.input.SetInsertionPointEnd()

    def clear_input(self):
        self.input.SetValue("")

    def set_users(self, users: list[str]):
        self.user_list.Set(users)

    # Events
    def _on_send_clicked(self, evt):
        text = self.input.GetValue().strip()
        if not text:
            return
        if callable(self.on_send):
            self.on_send(text)
        self.clear_input()
