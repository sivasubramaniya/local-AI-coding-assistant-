"""Keep the HTML preview offline.

Generated HTML can reference remote scripts, fonts or images (for example from a CDN).
The preview uses an off-the-record QWebEngineProfile (no cookies or cache on disk) with
an interceptor that blocks every request except local ones (data:, about:, blob:, qrc:,
file:, and http(s)/ws(s) to loopback hosts). "Open in default browser" is a separate,
user-initiated action outside the app.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

LOCAL_SCHEMES = {"data", "about", "blob", "qrc", "file", ""}
NETWORK_SCHEMES = {"http", "https", "ws", "wss", "ftp"}
LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}


def is_allowed_url(scheme: str, host: str) -> bool:
    scheme = scheme.lower()
    if scheme in LOCAL_SCHEMES:
        return True
    if scheme in NETWORK_SCHEMES:
        return host.lower() in LOOPBACK
    return False


def make_offline_page(view, profile_owner):
    """A QWebEnginePage on an off-the-record profile whose non-local requests are blocked.

    ``profile_owner`` must outlive ``view`` (the profile has to be deleted after its page).
    """
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor

    class OfflineInterceptor(QWebEngineUrlRequestInterceptor):
        def __init__(self, owner) -> None:
            super().__init__(owner)
            self.blocked: list[str] = []

        def interceptRequest(self, info) -> None:  # noqa: N802 - Qt API
            url = info.requestUrl()
            if not is_allowed_url(url.scheme(), url.host()):
                info.block(True)
                self.blocked.append(url.toString())
                logger.info("Preview blocked a network request to %s", url.host() or url.scheme())

    profile = QWebEngineProfile(profile_owner)  # no storage name: off the record
    interceptor = OfflineInterceptor(profile)
    profile.setUrlRequestInterceptor(interceptor)
    page = QWebEnginePage(profile, view)
    page.offline_interceptor = interceptor  # keep a Python reference (and for tests)
    return page
