#!/usr/bin/env python3
"""LifeSmart native window shell.

Run by the SYSTEM python (the one that already has PyGObject + WebKit2GTK),
not by the frozen binary - it just points a real GTK application window at the
local server the binary started. This gives a genuine native app window (own
taskbar entry, window controls, no browser chrome) instead of a browser tab.

Links out of the app are handled here as well: a savings platform's site or a
betting site opens in the real browser, and the app window stays the app. See
_classify for why that is not a nicety.

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
# The only schemes a link in this app can use. Anything else is never opened:
# a stored javascript: or file: address reaching the browser would be a bug in
# what the API accepted, so the shell refuses rather than trusting it.
WEB_SCHEMES = ("http", "https")


def _icon_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("lifesmart.svg", "lifesmart.png"):
        p = os.path.join(here, name)
        if os.path.isfile(p):
            return p
    return None


def _origin(uri: str) -> tuple[str, str, int]:
    """(scheme, host, port) of a URI, for comparing two addresses."""
    parsed = GLib.Uri.parse(uri, GLib.UriFlags.NONE)
    if parsed is None:
        return ("", "", 0)
    return (
        (parsed.get_scheme() or "").lower(),
        (parsed.get_host() or "").lower(),
        parsed.get_port(),
    )


def _classify(uri: str, app_origin: tuple[str, str, int]) -> str:
    """Where a requested address belongs: "local", "web" or "blocked".

    Without this the web view would simply navigate away from LifeSmart when a
    link is clicked, and the app has no back button - the person would lose
    their page and any half-typed form with it.
    """
    if not uri or uri.startswith("about:"):
        return "local"  # the view's own blank start page
    scheme, host, port = _origin(uri)
    if not scheme:
        return "local"  # a relative path, which is this app's own server
    if scheme not in WEB_SCHEMES:
        return "blocked"
    if (scheme, host, port) == app_origin:
        return "local"
    return "web"


def _decision_uri(decision) -> str:
    """The address a policy decision was made about, however the view reports it.

    get_navigation_action() is the current call and get_request() the older one;
    either can be missing depending on the webkit2gtk build installed, so both
    are tried rather than assuming the version this was written against.
    """
    for getter in (
        lambda: decision.get_navigation_action().get_request().get_uri(),
        lambda: decision.get_request().get_uri(),
    ):
        try:
            return getter() or ""
        except Exception:
            continue
    return ""


def _open_in_browser(uri: str, window) -> None:
    """Hand an address to the system browser. Never to this window."""
    try:
        if Gtk.show_uri_on_window(window, uri):
            return
    except Exception:
        pass
    try:
        GLib.spawn_async(None, ["xdg-open", uri], flags=GLib.SpawnFlags.SEARCH_PATH)
    except Exception as exc:  # pragma: no cover - depends on the desktop
        print(f"could not open {uri}: {exc}", file=sys.stderr)


def _connect_links(webview, app_origin: tuple[str, str, int]) -> None:
    """Keep the app on its own pages and send every other link out."""

    def on_decide_policy(_view, decision, decision_type):
        uri = _decision_uri(decision)
        where = _classify(uri, app_origin)
        top = _view.get_toplevel()
        if where == "web":
            decision.ignore()
            # A link asking to open a new window or tab goes to the browser too;
            # this shell has exactly one window and will not grow another.
            _open_in_browser(uri, top)
            return True
        if where == "blocked":
            decision.ignore()
            print(f"refused to open {uri}", file=sys.stderr)
            return True
        decision.use()
        return False

    def on_create(_view, navigation_action):
        # target="_blank" and window.open() ask for a new web view. Decline to
        # make one, so a link cannot spawn an unstyled window inside the app.
        uri = (navigation_action.get_request().get_uri() if navigation_action else "")
        if _classify(uri, app_origin) == "web":
            _open_in_browser(uri, _view.get_toplevel())
        return None

    webview.connect("decide-policy", on_decide_policy)
    webview.connect("create", on_create)


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
    # The app's own origin, taken from the URL we were handed to open.
    _connect_links(webview, _origin(url))
    webview.load_uri(url)
    win.add(webview)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
