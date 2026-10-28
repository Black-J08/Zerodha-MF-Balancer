"""Lightweight callback server for automatic request_token capture.

Provides a built-in ``http.server``-based callback server (no new
dependencies) that listens for the Zerodha authentication redirect,
extracts the ``request_token`` from the query string, and shuts down
gracefully after capture or on timeout.

The server runs in a background thread so ``authenticate()`` can display
the login URL to the user while waiting for the redirect.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Self
from urllib.parse import parse_qs, urlparse

from src.core.logging import get_logger
from src.core.settings import Settings

logger = get_logger(__name__)

_SUCCESS_HTML = """\
<html>
  <head><title>Authentication Complete</title></head>
  <body>
    <h2>Authentication Complete</h2>
    <p>You can close this window and return to the terminal.</p>
    <script>window.close();</script>
  </body>
</html>
"""

_ERROR_HTML = """\
<html>
  <head><title>Authentication Error</title></head>
  <body>
    <h2>Authentication Error</h2>
    <p>{message}</p>
    <p>You can close this window and return to the terminal.</p>
  </body>
</html>
"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the OAuth callback.

    Captures ``request_token`` from the configured callback path and
    signals the server to shut down after the first successful capture.
    """

    # Set by the server instance before handling requests.
    callback_path: str = "/callback"
    token_event: threading.Event | None = None
    captured_token: str | None = None
    capture_error: str | None = None

    def _send_response(self, status: int, body: str, content_type: str = "text/html") -> None:
        """Send an HTTP response with the given status and body."""
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        """Handle GET requests to the callback path."""
        parsed = urlparse(self.path)
        if parsed.path != self.callback_path:
            self._send_response(404, "<html><body><h2>Not Found</h2></body></html>")
            return

        query = parse_qs(parsed.query)
        tokens = query.get("request_token")
        if not tokens:
            _CallbackHandler.capture_error = "Missing request_token in redirect URL"
            self._send_response(400, _ERROR_HTML.format(message=_CallbackHandler.capture_error))
            if self.token_event is not None:
                self.token_event.set()
            return

        token = tokens[0]
        _CallbackHandler.captured_token = token
        logger.debug("Captured request_token from callback")
        self._send_response(200, _SUCCESS_HTML)
        if self.token_event is not None:
            self.token_event.set()

    def log_message(self, format: str, *args) -> None:
        """Suppress default request logging to keep output clean."""
        logger.debug("callback_server %s", format % args)


class CallbackServer:
    """Lightweight threaded callback server for request_token capture.

    Args:
        settings: Application configuration providing the callback host,
            port, and path derived from ``KITE_REDIRECT_URL``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._token_event = threading.Event()
        self._captured_token: str | None = None
        self._capture_error: str | None = None

        # Configure the handler class with shared state.
        _CallbackHandler.callback_path = settings.kite_callback_path
        _CallbackHandler.token_event = self._token_event
        _CallbackHandler.captured_token = None
        _CallbackHandler.capture_error = None

    @property
    def host(self) -> str | None:
        """Return the callback host."""
        return self._settings.kite_callback_host

    @property
    def port(self) -> int:
        """Return the callback port.

        Returns the port exactly as configured in the redirect URL. If no
        port is specified, returns 0 so the OS assigns an ephemeral port.
        """
        port = self._settings.kite_callback_port
        return port if port is not None else 0

    @property
    def path(self) -> str:
        """Return the callback path."""
        return self._settings.kite_callback_path

    def start(self) -> None:
        """Start the callback server in a background thread.

        Raises:
            OSError: If the server cannot bind to the host/port (e.g. port
                already in use).
        """
        host = self.host or "127.0.0.1"
        port = self.port
        logger.info("Starting callback server on %s:%s%s", host, port, self.path)

        self._server = ThreadingHTTPServer((host, port), _CallbackHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def wait_for_token(self, timeout: float = 120.0) -> str | None:
        """Wait for the request_token to be captured.

        Args:
            timeout: Maximum seconds to wait before giving up.

        Returns:
            The captured request_token, or None if the timeout elapsed or
            an error occurred.
        """
        if not self._token_event.wait(timeout):
            logger.warning("Callback server timed out after %s seconds", timeout)
            self.stop()
            return None

        if _CallbackHandler.capture_error:
            logger.error("Callback capture error: %s", _CallbackHandler.capture_error)
            self.stop()
            return None

        token = _CallbackHandler.captured_token
        self._captured_token = token
        self.stop()
        return token

    def stop(self) -> None:
        """Stop the callback server gracefully."""
        if self._server is not None:
            try:
                # shutdown() must be called from a different thread than
                # serve_forever, so we schedule it on the server thread.
                self._server.shutdown()
            except OSError:
                # Server may already be shut down.
                pass
            self._server = None

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
