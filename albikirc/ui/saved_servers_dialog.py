import wx

class SavedServersDialog(wx.Dialog):
    def __init__(self, parent, servers):
        super().__init__(parent, title="Connect to Saved Server")
        self.SetName("Saved servers dialog")
        self._servers = list(servers or [])

        self.listbox = wx.ListBox(self, choices=[self._display_text(s) for s in self._servers], style=wx.LB_SINGLE)
        self.listbox.SetName("Saved servers list")
        self.listbox.SetToolTip("Choose a saved server to connect or remove")

        btn_connect = wx.Button(self, wx.ID_OK, "Connect")
        btn_connect.SetName("Connect button")
        btn_connect.SetToolTip("Connect to the selected server")

        btn_remove = wx.Button(self, wx.ID_DELETE, "Remove")
        btn_remove.SetName("Remove button")
        btn_remove.SetToolTip("Remove the selected server from the list")

        btn_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btn_cancel.SetName("Cancel button")
        btn_cancel.SetToolTip("Close this dialog without connecting")

        btns = wx.BoxSizer(wx.HORIZONTAL)
        btns.Add(btn_connect, 0, wx.RIGHT, 6)
        btns.Add(btn_remove, 0, wx.RIGHT, 6)
        btns.Add(btn_cancel, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.listbox, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_remove, btn_remove)

    def _display_text(self, s):
        name = s.get('name') or s.get('host','')
        host = s.get('host','')
        port = s.get('port', 6697)
        tls = 'TLS' if s.get('use_tls', True) else 'Plain'
        sasl = 'SASL' if s.get('sasl_enabled', False) else ''
        ka = 'KA' if s.get('tcp_keepalive', False) else ''
        nick = s.get('nick','')
        parts = [name or host, f"{host}:{port}", tls]
        if sasl:
            parts.append(sasl)
        if ka:
            parts.append(ka)
        if nick:
            parts.append(f"nick={nick}")
        return "  |  ".join(parts)

    def _on_remove(self, evt):
        sel = self.listbox.GetSelection()
        if sel != wx.NOT_FOUND:
            del self._servers[sel]
            self.listbox.Delete(sel)

    @property
    def selected(self):
        idx = self.listbox.GetSelection()
        if idx == wx.NOT_FOUND:
            return None
        return self._servers[idx]
