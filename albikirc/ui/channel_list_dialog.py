import wx


class ChannelListDialog(wx.Dialog):
    def __init__(self, parent, on_join=None, close_on_join: bool = True):
        super().__init__(
            parent,
            title="Channel List",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetName("Channel list dialog")

        self._on_join = on_join
        self.close_on_join = bool(close_on_join)
        self._channels: list[dict[str, object]] = []
        self._build_ui()
        self.SetMinSize((620, 420))
        self.SetSize((760, 520))

    def _build_ui(self):
        root = wx.BoxSizer(wx.VERTICAL)

        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_label = wx.StaticText(self, label="Search:")
        self.filter_ctrl = wx.TextCtrl(self)
        self.filter_ctrl.SetName("Channel search")
        self.filter_ctrl.SetToolTip("Search by channel name or topic")

        filter_row.Add(filter_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        filter_row.Add(self.filter_ctrl, 1)

        self.list = wx.ListBox(self, style=wx.LB_SINGLE | wx.BORDER_SUNKEN)
        self.list.SetName("Channels")
        self.list.SetToolTip("Available channels from the server. Press Enter to join.")

        self.details = wx.TextCtrl(
            self,
            value="Select a channel to hear its details.",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
        )
        self.details.SetName("Selected channel details")
        self.details.SetToolTip("Details for the selected channel")

        self.status = wx.StaticText(self, label="No channel list loaded.")
        self.status.SetName("Channel list status")

        button_row = wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_btn = wx.Button(self, label="Refresh")
        self.refresh_btn.SetName("Refresh channel list button")
        self.refresh_btn.SetToolTip("Request the channel list from the server")
        self.join_btn = wx.Button(self, label="Join")
        self.join_btn.SetName("Join selected channel button")
        self.join_btn.SetToolTip("Join the selected channel")
        close_btn = wx.Button(self, id=wx.ID_CLOSE)
        close_btn.SetName("Close channel list button")

        button_row.Add(self.refresh_btn, 0, wx.RIGHT, 6)
        button_row.AddStretchSpacer(1)
        button_row.Add(self.join_btn, 0, wx.RIGHT, 6)
        button_row.Add(close_btn, 0)

        root.Add(filter_row, 0, wx.EXPAND | wx.ALL, 10)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        root.Add(self.details, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        root.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        root.Add(button_row, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(root)

        self.filter_ctrl.Bind(wx.EVT_TEXT, lambda evt: self._apply_filters())
        self.list.Bind(wx.EVT_LISTBOX, self._on_selection_changed)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_activate)
        self.list.Bind(wx.EVT_CHAR_HOOK, self._on_list_key)
        self.join_btn.Bind(wx.EVT_BUTTON, self._on_join_clicked)
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.Close())
        self._update_join_enabled()

    def set_refresh_handler(self, handler):
        self.refresh_btn.Bind(wx.EVT_BUTTON, handler)

    def begin_list(self):
        self._channels = []
        self.list.Clear()
        self.details.SetValue("Select a channel to hear its details.")
        self.status.SetLabel("Loading channel list...")
        self._update_join_enabled()

    def add_channel(self, channel: str, users: int | None, topic: str):
        self._channels.append({"channel": channel, "users": users, "topic": topic})
        if self._matches(channel, users, topic):
            self._append_row(channel, users, topic)
            self._update_status(loading=True)

    def end_list(self):
        self._apply_filters()

    def _matches(self, channel: str, users: int | None, topic: str) -> bool:
        query = self.filter_ctrl.GetValue().strip().lower()
        return not query or query in channel.lower() or query in topic.lower()

    def _append_row(self, channel: str, users: int | None, topic: str):
        self.list.Append(self._format_channel_row(channel, users, topic))

    def _apply_filters(self):
        selected = self._selected_channel()
        self.list.Clear()
        for item in self._channels:
            channel = str(item["channel"])
            users = item["users"]
            topic = str(item["topic"])
            if self._matches(channel, users if isinstance(users, int) else None, topic):
                self._append_row(channel, users if isinstance(users, int) else None, topic)
                if channel == selected:
                    self.list.SetSelection(self.list.GetCount() - 1)
        self._update_status()
        self._update_details()
        self._update_join_enabled()

    def _update_status(self, loading: bool = False):
        visible = self.list.GetCount()
        total = len(self._channels)
        suffix = " loaded" if loading else ""
        self.status.SetLabel(f"{visible} of {total} channel(s){suffix}.")

    def _selected_channel(self) -> str:
        idx = self.list.GetSelection()
        if idx == -1:
            return ""
        row = self.list.GetString(idx)
        return row.split(",", 1)[0].strip()

    def _update_join_enabled(self):
        self.join_btn.Enable(bool(self._selected_channel()))

    def _format_channel_row(self, channel: str, users: int | None, topic: str) -> str:
        users_text = "unknown users" if users is None else f"{users} users"
        topic_text = topic.strip() or "No topic"
        return f"{channel}, {users_text}, {topic_text}"

    def _selected_item(self) -> dict[str, object] | None:
        channel = self._selected_channel()
        if not channel:
            return None
        for item in self._channels:
            if str(item["channel"]) == channel:
                return item
        return None

    def _update_details(self):
        item = self._selected_item()
        if item is None:
            self.details.SetValue("Select a channel to hear its details.")
            return
        channel = str(item["channel"])
        users = item["users"]
        topic = str(item["topic"]).strip() or "No topic"
        users_text = "Unknown users" if users is None else f"{users} users"
        self.details.SetValue(f"Channel: {channel}\nUsers: {users_text}\nTopic: {topic}")

    def _on_selection_changed(self, evt):
        self._update_details()
        self._update_join_enabled()

    def _on_list_key(self, evt):
        try:
            key = evt.GetKeyCode()
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self._join_selected()
                return
            evt.Skip()
        except Exception:
            try:
                evt.Skip()
            except Exception:
                pass

    def _on_activate(self, evt):
        self._join_selected()

    def _on_join_clicked(self, evt):
        self._join_selected()

    def _join_selected(self):
        channel = self._selected_channel()
        if channel and callable(self._on_join):
            self._on_join(channel)
            if self.close_on_join:
                self.Close()
