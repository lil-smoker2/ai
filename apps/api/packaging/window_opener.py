#!/usr/bin/env python3
"""LifeSmart native window shell.

Run by the SYSTEM python (the one that already has PyGObject + WebKit2GTK),
not by the frozen binary - it just points a real GTK application window at the
local server the binary started. This gives a genuine native app window (own
taskbar entry, window controls, no browser chrome) instead of a browser tab.

Usage: python3 window_opener.py http://127.0.0.1:PORT
Exits (returns to the caller) when the window is closed, so the launcher can
then shut the server down.
"""
import os
import sys

# Stability on GNOME/Wayland + some GPU drivers: the DMABUF renderer in recent
# webkit2gtk can crash the web view; fall back to a safer path when needed.
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib  # noqa: E402

APP_ID = "com.lifesmart.app"
TITLE = "LifeSmart"


def _icon_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("lifesmart.svg", "lifesmart.png"):
        p = os.path.join(here, name)
        if os.path.isfile(p):
            return p
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: window_opener.py <url>", file=sys.stderr)
        return 2
    url = sys.argv[1]

    # Set the application identity before the window is realised so GNOME
    # (Wayland) groups it as LifeSmart, not as a generic Python/GTK app.
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(TITLE)

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(TITLE)
    try:
        # WM_CLASS on X11 (harmless under Wayland).
        win.set_wmclass("lifesmart", TITLE)
    except Exception:
        pass
    win.set_default_size(1280, 860)

    icon = _icon_path()
    if icon:
        try:
            win.set_icon_from_file(icon)
        except Exception:
            pass

    webview = WebKit2.WebView()
    webview.load_uri(url)
    win.add(webview)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
