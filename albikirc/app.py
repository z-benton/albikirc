import wx

try:
    # When run as a package (python -m albikirc.app)
    from .config import load
    from .ui.main_frame import MainFrame
except ImportError:
    # When frozen/launched as a script where relative imports lack a package
    from albikirc.config import load
    from albikirc.ui.main_frame import MainFrame


def main():
    app = wx.App()
    settings = load()
    frame = MainFrame(None, title="albikirc", settings=settings)
    frame.Centre()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
