"""
_http.py — shared async HTTP layer for aiorew.

Wraps httpx.AsyncClient with:
- Base URL construction from host + port
- Uniform JSON error handling (raises REWError on non-2xx)
- A _poll() helper for long-running commands that return 202 Accepted
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

import httpx


class REWError(Exception):
    """Raised when the REW API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"REW API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class _HTTPClient:
    """
    Thin async wrapper around httpx.AsyncClient bound to a single REW instance.

    All public methods return parsed JSON (dict / list / scalar) or raise
    REWError.  The caller is responsible for dataclass construction.
    """

    def __init__(self, host: str, port: int) -> None:
        self._base = f"http://{host}:{port}"  # noqa
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "_HTTPClient":
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "_HTTPClient not started — call start() or use as async context manager"
            )
        return self._client

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
            msg = body.get("message") or body.get("error") or str(body)
        except Exception:
            msg = response.text or response.reason_phrase
        raise REWError(response.status_code, msg)

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        """Return parsed body: dict, list, scalar, or None for empty 2xx."""
        text = response.text.strip()
        if not text:
            return None
        try:
            return response.json()
        except Exception:
            # Plain scalar (e.g. target-level returns "75.0")
            return text.strip('"')

    # ------------------------------------------------------------------
    # HTTP verbs
    # ------------------------------------------------------------------

    async def get(self, path: str, **params: Any) -> Any:
        r = await self._http().get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        self._raise_for_status(r)
        return self._parse(r)

    async def post(self, path: str, body: Any = None) -> Any:
        r = await self._http().post(path, json=body)
        self._raise_for_status(r)
        return self._parse(r)

    async def put(self, path: str, body: Any = None) -> Any:
        r = await self._http().put(path, json=body)
        self._raise_for_status(r)
        return self._parse(r)

    async def delete(self, path: str) -> Any:
        r = await self._http().delete(path)
        self._raise_for_status(r)
        return self._parse(r)

    # ------------------------------------------------------------------
    # Polling helper
    # ------------------------------------------------------------------

    @staticmethod
    async def poll_until(
        check: Callable[[], Any],
        *,
        condition: Callable[[Any], bool],
        poll_interval: float = 0.5,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Repeatedly call *check()* (an async or sync callable) until
        *condition(result)* returns True, then return the result.

        Parameters
        ----------
        check:
            Async callable (no arguments) that fetches the current state.
        condition:
            Predicate applied to the result of *check()*. Returns True when
            the operation is considered complete.
        poll_interval:
            Seconds between polls (default 0.5).
        timeout:
            Optional maximum seconds to wait before raising TimeoutError.
        """
        elapsed = 0.0
        while True:
            result = await check()
            if condition(result):
                return result
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if timeout is not None and elapsed >= timeout:
                raise TimeoutError(f"REW operation did not complete within {timeout}s")
