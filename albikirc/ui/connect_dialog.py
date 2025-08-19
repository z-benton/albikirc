import wx


class ConnectDialog(wx.Dialog):
    def __init__(self, parent, host_default="", port_default=6667, nick_default="", use_tls_default=False, tcp_keepalive_default=True, enable_save=True):
        super().__init__(parent, title="Connect to IRC")
        self.SetName("Connect dialog")

        # --- Basic fields ---
        host_label = wx.StaticText(self, label="Host:")
        self.host_ctrl = wx.TextCtrl(self, value=str(host_default))
        self.host_ctrl.SetName("Host field")
        self.host_ctrl.SetToolTip("Hostname or IP of the IRC server")

        port_label = wx.StaticText(self, label="Port:")
        self.port_ctrl = wx.SpinCtrl(self, min=1, max=65535, initial=int(port_default))
        self.port_ctrl.SetName("Port field")
        self.port_ctrl.SetToolTip("Server port number (1–65535)")

        nick_label = wx.StaticText(self, label="Nick:")
        self.nick_ctrl = wx.TextCtrl(self, value=str(nick_default))
        self.nick_ctrl.SetName("Nick field")
        self.nick_ctrl.SetToolTip("Nickname to use on this server")

        pass_label = wx.StaticText(self, label="Server password (optional, not saved):")
        self.pass_ctrl = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self.pass_ctrl.SetName("Server password field")
        self.pass_ctrl.SetToolTip("PASS sent before registration if provided. This value is not saved.")

        self.tls_checkbox = wx.CheckBox(self, label="Use TLS")
        self.tls_checkbox.SetName("Use TLS checkbox")
        self.tls_checkbox.SetValue(bool(use_tls_default))
        self.tls_checkbox.SetToolTip("Enable TLS encryption for the connection")

        # TCP keepalive
        self.keepalive_checkbox = wx.CheckBox(self, label="Enable TCP keepalive")
        self.keepalive_checkbox.SetName("Enable TCP keepalive checkbox")
        self.keepalive_checkbox.SetValue(bool(tcp_keepalive_default))
        self.keepalive_checkbox.SetToolTip("Send periodic TCP probes to keep idle connections alive")

        # Optional server display name
        name_label = wx.StaticText(self, label="Server name (optional):")
        self.name_ctrl = wx.TextCtrl(self)
        self.name_ctrl.SetName("Server name field")
        self.name_ctrl.SetToolTip("Optional display name for saved servers")

        # --- SASL options ---
        self.sasl_checkbox = wx.CheckBox(self, label="Use SASL (PLAIN)")
        self.sasl_checkbox.SetName("Use SASL checkbox")
        self.sasl_checkbox.SetToolTip("Enable SASL PLAIN authentication")
        self.sasl_user_ctrl = wx.TextCtrl(self)
        self.sasl_user_ctrl.SetName("SASL username field")
        self.sasl_user_ctrl.SetToolTip("SASL username (often same as nick)")
        self.sasl_pass_ctrl = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self.sasl_pass_ctrl.SetName("SASL password field")
        self.sasl_pass_ctrl.SetToolTip("SASL password (hidden). This value is not saved.")
        self.sasl_file_btn = wx.Button(self, label="Load SASL from file…")
        self.sasl_file_btn.SetToolTip("Load SASL credentials from a file")

        # --- TLS client cert (optional) ---
        self.certfile_ctrl = wx.TextCtrl(self)
        self.certfile_ctrl.SetName("TLS client cert field")
        self.certfile_ctrl.SetToolTip("Path to client certificate file (PEM)")
        self.keyfile_ctrl = wx.TextCtrl(self)
        self.keyfile_ctrl.SetName("TLS client key field")
        self.keyfile_ctrl.SetToolTip("Path to client private key file (PEM)")
        self.certfile_btn = wx.Button(self, label="Browse cert…")
        self.certfile_btn.SetToolTip("Browse for certificate file")
        self.keyfile_btn = wx.Button(self, label="Browse key…")
        self.keyfile_btn.SetToolTip("Browse for private key file")

        # Save option
        self.save_checkbox = wx.CheckBox(self, label="Save server to servers list")
        self.save_checkbox.SetName("Save server checkbox")
        self.save_checkbox.Enable(bool(enable_save))
        self.save_checkbox.SetToolTip("Save this server in the servers list")

        # --- Layout ---
        root = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(0, 2, 6, 6)
        grid.AddGrowableCol(1, 1)
        grid.AddMany([
            (host_label, 0, wx.ALIGN_CENTER_VERTICAL), (self.host_ctrl, 1, wx.EXPAND),
            (port_label, 0, wx.ALIGN_CENTER_VERTICAL), (self.port_ctrl, 0),
            (nick_label, 0, wx.ALIGN_CENTER_VERTICAL), (self.nick_ctrl, 1, wx.EXPAND),
            (pass_label, 0, wx.ALIGN_CENTER_VERTICAL), (self.pass_ctrl, 1, wx.EXPAND),
            (wx.StaticText(self, label=""), 0), (self.tls_checkbox, 0),
            (wx.StaticText(self, label=""), 0), (self.keepalive_checkbox, 0),
            (name_label, 0, wx.ALIGN_CENTER_VERTICAL), (self.name_ctrl, 1, wx.EXPAND),
        ])
        root.Add(grid, 0, wx.ALL | wx.EXPAND, 12)

        # SASL area
        sasl_box = wx.StaticBoxSizer(wx.StaticBox(self, label="Authentication (optional)"), wx.VERTICAL)
        sasl_box.Add(self.sasl_checkbox, 0, wx.ALL, 6)
        row_user = wx.BoxSizer(wx.HORIZONTAL)
        row_user.Add(wx.StaticText(self, label="SASL username:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_user.Add(self.sasl_user_ctrl, 1, wx.EXPAND)
        sasl_box.Add(row_user, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        row_pass = wx.BoxSizer(wx.HORIZONTAL)
        row_pass.Add(wx.StaticText(self, label="SASL password (not saved):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_pass.Add(self.sasl_pass_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
        row_pass.Add(self.sasl_file_btn, 0)
        sasl_box.Add(row_pass, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        root.Add(sasl_box, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

        # TLS client cert/key area
        tls_box = wx.StaticBoxSizer(wx.StaticBox(self, label="TLS client certificate (optional)"), wx.VERTICAL)
        row_cert = wx.BoxSizer(wx.HORIZONTAL)
        row_cert.Add(wx.StaticText(self, label="Client cert:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_cert.Add(self.certfile_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
        row_cert.Add(self.certfile_btn, 0)
        tls_box.Add(row_cert, 0, wx.EXPAND | wx.ALL, 6)

        row_key = wx.BoxSizer(wx.HORIZONTAL)
        row_key.Add(wx.StaticText(self, label="Client key:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row_key.Add(self.keyfile_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
        row_key.Add(self.keyfile_btn, 0)
        tls_box.Add(row_key, 0, wx.EXPAND | wx.ALL, 6)
        root.Add(tls_box, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

        # Save checkbox and buttons
        root.Add(self.save_checkbox, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Accessibility note about passwords not being saved
        note = wx.StaticText(self, label="Passwords are not saved. This may be implemented in the future if a secure method is available.")
        note.SetName("Passwords not saved note")
        note.SetToolTip("Passwords entered here are not saved. A secure save option may be added in the future.")
        root.Add(note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btns, 0, wx.ALL | wx.ALIGN_RIGHT, 12)

        self.SetSizerAndFit(root)

        # Focus first field
        self.host_ctrl.SetFocus()

        # Enable/disable SASL fields when toggled
        def _sync_sasl_enabled(evt=None):
            enabled = self.sasl_checkbox.GetValue()
            self.sasl_user_ctrl.Enable(enabled)
            self.sasl_pass_ctrl.Enable(enabled)
            self.sasl_file_btn.Enable(enabled)
        self.Bind(wx.EVT_CHECKBOX, _sync_sasl_enabled, self.sasl_checkbox)
        _sync_sasl_enabled()

        # Browse handlers
        def pick_file(msg):
            with wx.FileDialog(self, message=msg, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    return dlg.GetPath()
            return ""
        self.Bind(wx.EVT_BUTTON, lambda e: self.certfile_ctrl.SetValue(pick_file("Choose client certificate")), self.certfile_btn)
        self.Bind(wx.EVT_BUTTON, lambda e: self.keyfile_ctrl.SetValue(pick_file("Choose client key")), self.keyfile_btn)
        def load_sasl_from_file(evt):
            path = pick_file("Choose SASL auth file (user:pass or two lines)")
            if path:
                try:
                    data = open(path, 'r', encoding='utf-8').read()
                    if ':' in data:
                        u, p = data.strip().split(':', 1)
                    else:
                        parts = [x.strip() for x in data.strip().splitlines() if x.strip()]
                        u, p = (parts + ['', ''])[:2]
                    self.sasl_user_ctrl.SetValue(u)
                    self.sasl_pass_ctrl.SetValue(p)
                except Exception as e:
                    wx.MessageBox(f"Failed to read file: {e}", "SASL", wx.OK | wx.ICON_ERROR)
        self.Bind(wx.EVT_BUTTON, load_sasl_from_file, self.sasl_file_btn)
    @property
    def host(self) -> str:
        return self.host_ctrl.GetValue().strip()

    @property
    def port(self) -> int:
        return int(self.port_ctrl.GetValue())

    @property
    def nick(self) -> str:
        return self.nick_ctrl.GetValue().strip()

    @property
    def use_tls(self) -> bool:
        return self.tls_checkbox.GetValue()

    @property
    def server_name(self) -> str:
        return self.name_ctrl.GetValue().strip()

    @property
    def save_server(self) -> bool:
        return self.save_checkbox.GetValue()


    @property
    def sasl_enabled(self) -> bool:
        return self.sasl_checkbox.GetValue()

    @property
    def sasl_username(self) -> str:
        return self.sasl_user_ctrl.GetValue().strip()

    @property
    def sasl_password(self) -> str:
        return self.sasl_pass_ctrl.GetValue()

    @property
    def certfile(self) -> str:
        return self.certfile_ctrl.GetValue().strip()

    @property
    def keyfile(self) -> str:
        return self.keyfile_ctrl.GetValue().strip()

    @property
    def tcp_keepalive_enabled(self) -> bool:
        return self.keepalive_checkbox.GetValue()

    @property
    def server_password(self) -> str:
        return self.pass_ctrl.GetValue()
