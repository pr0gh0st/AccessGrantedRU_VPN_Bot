from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundClientTraffic:
    """
    Traffic stats for a single client.

    Notes:
    - 3X-UI returns values in bytes.
    - We keep raw values; presentation (GB formatting) belongs to handlers/services.
    """

    uploaded_bytes: int
    downloaded_bytes: int
    total_bytes: int


class XUIAPI:
    """
    Adapter for 3X-UI API.

    The 3X-UI API sometimes differs between versions (response shapes, payload formats).
    This adapter attempts to be resilient:
    - uses an httpx cookie session
    - retries on network errors
    - relogs once on auth failures
    - normalizes `settings` / `streamSettings` if they arrive as JSON strings

    Where manual adjustment might be required:
    - request/response payload schemas for `addClient` / `update` endpoints
    - traffic extraction shape for `getClientTraffics*` endpoints
    """

    def __init__(self, *, request_timeout_seconds: float = 15.0) -> None:
        if not settings.XUI_API_URL:
            raise RuntimeError("XUI_API_URL is empty. Заполните переменные XUI в .env")

        self._timeout = httpx.Timeout(request_timeout_seconds)
        self._base_url = settings.XUI_API_URL.rstrip("/")
        self._base_path = (settings.XUI_BASE_PATH or "").strip("/")

        # Panel may be mounted under a custom prefix:
        #   http://host:port/<CUSTOM_PATH>/login
        #
        # But API prefix may vary depending on version / reverse proxy:
        #   /<CUSTOM_PATH>/panel/api/...
        #   /<CUSTOM_PATH>/api/...
        #   /panel/api/...
        #
        # We'll try candidates and lock onto the first working one.
        if self._base_path:
            self._api_root_candidates = [
                f"/{self._base_path}/panel/api",
                f"/{self._base_path}/api",
                "/panel/api",
            ]
            self._login_path_candidates = [
                # Some deployments mount the panel root at /<CUSTOM_PATH> (no /login at all)
                f"/{self._base_path}",
                f"/{self._base_path}/",
                # Most common mounts:
                f"/{self._base_path}/login",
                f"/{self._base_path}/login/",
                # Some reverse-proxy configs mount UI under /panel
                f"/{self._base_path}/panel/login",
                f"/{self._base_path}/panel/login/",
                # Fallback to root:
                "/login",
                "/login/",
                "/panel/login",
                "/panel/login/",
            ]
        else:
            self._api_root_candidates = ["/panel/api"]
            self._login_path_candidates = ["/login", "/login/", "/panel/login", "/panel/login/"]

        self._api_root = self._api_root_candidates[0]
        self._login_path = self._login_path_candidates[0]

        self._username = settings.XUI_USERNAME
        self._password = settings.XUI_PASSWORD

        # httpx client stores cookies set by /login.
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            follow_redirects=True,
            headers={"Content-Type": "application/json"},
        )

        self._is_logged_in = False

    async def close(self) -> None:
        await self._client.aclose()

    async def login(self) -> None:
        """
        Authenticate against 3X-UI.

        Docs indicate endpoint: POST /login
        Body: { "username": "...", "password": "..." }
        """

        last_status: Optional[int] = None
        last_text: Optional[str] = None

        try:
            for candidate in self._login_path_candidates:
                # Attempt JSON login (as per upstream docs).
                r = await self._client.post(candidate, json={"username": self._username, "password": self._password})
                last_status = r.status_code

                if r.status_code in (200, 204):
                    # Some setups return 200 with HTML, but still set cookies.
                    if len(self._client.cookies.jar) > 0:
                        self._login_path = candidate
                        self._is_logged_in = True
                        await self._probe_api_root()
                        return

                # Fallback: some panels expect form-encoded login.
                r2 = await self._client.post(
                    candidate,
                    data={"username": self._username, "password": self._password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                last_status = r2.status_code
                if r2.status_code in (200, 204) and len(self._client.cookies.jar) > 0:
                    self._login_path = candidate
                    self._is_logged_in = True
                    await self._probe_api_root()
                    return

                # keep small snippet for troubleshooting (no secrets)
                last_text = ((r2.text or r.text) or "")[:200]

            raise RuntimeError(f"XUI login failed, last status={last_status}, body_snippet={last_text!r}")
        except httpx.HTTPError as e:
            raise RuntimeError(f"XUI login network error: {e}") from e
        except Exception:
            # Avoid logging credentials.
            raise

    async def _probe_api_root(self) -> None:
        """
        Try to find the actual API root for the current deployment.

        Some reverse proxies mask unauthorized requests as 404.
        We probe a cheap endpoint under each candidate and pick the first that is not 404.
        """

        # These endpoints exist in upstream docs; if they differ in your version,
        # adjust only here.
        probe_paths = [
            "/server/status",
            "/inbounds/list",
        ]

        for root in self._api_root_candidates:
            for probe in probe_paths:
                try_path = f"{root}{probe}"
                try:
                    r = await self._client.get(try_path)
                except httpx.HTTPError:
                    continue

                # We accept anything except 404 as a sign that the path exists
                # (could still be 401/403 depending on auth).
                if r.status_code != 404:
                    self._api_root = root
                    logger.info("XUI API root detected: %s", self._api_root)
                    return

        # If everything is 404, keep current root and let the next request surface the error.
        logger.warning("XUI API root probe failed; keeping %s", self._api_root)

    def _normalize_json_field(self, value: Any) -> Any:
        """If value looks like JSON string - parse it; otherwise return as-is."""

        if isinstance(value, str):
            s = value.strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    return value
        return value

    async def _request(self, method: str, path: str, *, json_body: Any = None) -> Any:
        if not self._is_logged_in:
            await self.login()

        async def do_request() -> httpx.Response:
            return await self._client.request(method, path, json=json_body)

        try:
            r = await do_request()
            if r.status_code in (401, 403):
                self._is_logged_in = False
                await self.login()
                r = await do_request()
            elif r.status_code == 404 and self._base_path:
                # Likely wrong API prefix (panel/api vs api). Try other candidates once.
                for root in self._api_root_candidates:
                    if root == self._api_root:
                        continue
                    alt_path = root + path[len(self._api_root) :] if path.startswith(self._api_root) else None
                    if not alt_path:
                        continue
                    r2 = await self._client.request(method, alt_path, json=json_body)
                    if r2.status_code != 404:
                        self._api_root = root
                        r = r2
                        break

            r.raise_for_status()
            if r.content:
                # Some endpoints return empty response bodies.
                ctype = r.headers.get("content-type", "")
                if "application/json" in ctype or r.text.strip().startswith("{") or r.text.strip().startswith("["):
                    return r.json()
                # Fallback: attempt decode
                try:
                    return json.loads(r.text)
                except Exception:
                    return {"raw": r.text}
            return None
        except httpx.HTTPStatusError as e:
            # Avoid logging payloads and cookies.
            logger.warning("XUI HTTP error path=%s status=%s", path, e.response.status_code)
            raise

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get_inbound(self, inbound_id: int) -> Dict[str, Any]:
        path = f"{self._api_root}/inbounds/get/{inbound_id}"
        result = await self._request("GET", path)
        if not isinstance(result, dict):
            raise RuntimeError("Unexpected XUI get_inbound response")
        return self._extract_inbound_from_response(result)

    def _extract_inbound_from_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize inbound response shape across different 3X-UI versions.

        Common variants:
        - direct inbound object: {"id": 1, "port": 443, ...}
        - wrapped response: {"success": true, "obj": {...inbound...}}
        - wrapped response: {"data": {...inbound...}} / {"result": {...inbound...}}
        """

        if "port" in payload:
            return payload

        for key in ("obj", "data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict) and "port" in nested:
                return nested

        # Sometimes payload could be {"obj": {"inbound": {...}}}
        for key in ("obj", "data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                inbound = nested.get("inbound")
                if isinstance(inbound, dict) and "port" in inbound:
                    return inbound

        raise RuntimeError("XUI inbound response does not contain `port` in known fields")

    async def add_client(self, *, inbound_id: int, client: Mapping[str, Any]) -> None:
        """
        Add client to an inbound.

        Endpoint (upstream): POST /panel/api/inbounds/addClient
        Payload example (from upstream community):
          {
            "id": "<inbound_id>",
            "settings": {
              "clients": [ { ...client fields... } ]
            }
          }

        Manual adjustment might be required if your XUI version expects
        different keys inside `settings` or client fields.
        """

        path = f"{self._api_root}/inbounds/addClient"

        payload_obj_settings: Dict[str, Any] = {"id": inbound_id, "settings": {"clients": [dict(client)]}}

        try:
            await self._request("POST", path, json_body=payload_obj_settings)
            return
        except httpx.HTTPStatusError:
            # Some XUI versions expect `settings` as a JSON-encoded string.
            # If this also fails, we re-raise the original exception context.
            pass

        payload_str_settings: Dict[str, Any] = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [dict(client)]}, ensure_ascii=False),
        }
        await self._request("POST", path, json_body=payload_str_settings)

    async def remove_client(self, *, inbound_id: int, client_id: str) -> None:
        """
        Remove client from an inbound.

        Endpoint (upstream): POST /panel/api/inbounds/:id/delClient/:clientId
        No JSON body is required.
        """

        path = f"{self._api_root}/inbounds/{inbound_id}/delClient/{client_id}"
        await self._request("POST", path, json_body=None)

    async def get_client_traffic(
        self,
        *,
        inbound_id: int,
        client_id: str,
        email: Optional[str] = None,
    ) -> Optional[InboundClientTraffic]:
        """
        Get client traffic for a client inside a specific inbound.

        XUI returns traffic via two endpoints (shapes differ by protocol/version):
        - GET /panel/api/inbounds/getClientTrafficsById/:id (often used for “by inbound”)
        - GET /panel/api/inbounds/getClientTraffics/:email

        We:
        1) request “by inbound id”, then try to find the matching client inside the response
        2) fallback to “by email” if `email` is provided

        Response shape can vary; we extract `up` / `down` / `total` by heuristics.
        """

        path_by_inbound = f"{self._api_root}/inbounds/getClientTrafficsById/{inbound_id}"
        data = await self._request("GET", path_by_inbound)
        parsed = self._parse_traffic_from_any(
            data,
            match_client_id=client_id,
            match_email=email,
        )
        if parsed is not None:
            return parsed

        if email:
            path_by_email = f"{self._api_root}/inbounds/getClientTraffics/{email}"
            data2 = await self._request("GET", path_by_email)
            return self._parse_traffic_from_any(data2)

        return None

    async def update_inbound_clients(self, *, inbound_id: int, clients: List[Mapping[str, Any]]) -> None:
        """
        Batch update clients in an inbound.

        There is no single universal endpoint across all versions; common approach:
        - GET inbound
        - modify its `settings.clients`
        - POST update inbound

        Manual adjustment might be required if your XUI returns `settings` as a string
        with a different structure for VLESS/Reality.
        """

        inbound = await self.get_inbound(inbound_id)

        settings_field = inbound.get("settings")
        normalized_settings = self._normalize_json_field(settings_field)

        if isinstance(normalized_settings, dict):
            normalized_settings["clients"] = [dict(c) for c in clients]
            inbound["settings"] = json.dumps(normalized_settings) if isinstance(settings_field, str) else normalized_settings
        else:
            # If we can't normalize, we fail fast with a clear message.
            raise RuntimeError("Cannot update inbound clients: unexpected `settings` format")

        path = f"{self._api_root}/inbounds/update/{inbound_id}"
        await self._request("POST", path, json_body=inbound)

    def build_vless_url(
        self,
        *,
        client_id: str,
        host: str,
        port: int,
        remark: str,
    ) -> str:
        return (
            f"vless://{client_id}@{host}:{port}"
            f"?type=tcp&security=reality&pbk={settings.REALITY_PUBLIC_KEY}"
            f"&fp={settings.REALITY_FINGERPRINT}"
            f"&sni={settings.REALITY_SNI}"
            f"&sid={settings.REALITY_SHORT_ID}"
            f"&spx={settings.REALITY_SPIDER_X}"
            f"#{remark}"
        )

    def _parse_traffic_from_any(
        self,
        data: Any,
        *,
        match_client_id: Optional[str] = None,
        match_email: Optional[str] = None,
    ) -> Optional[InboundClientTraffic]:
        """
        Try to extract up/down/total from various shapes returned by XUI.

        Expected keys (community/Go struct ClientTraffic):
        - up
        - down
        - total
        """

        if data is None:
            return None

        # Direct object with up/down/total.
        if isinstance(data, dict):
            # If keys for identity exist, apply matching when provided.
            id_candidate = data.get("id") or data.get("clientId") or data.get("uuid")
            email_candidate = data.get("email") or data.get("clientEmail")
            if match_client_id and id_candidate and str(id_candidate) != match_client_id:
                return None
            if match_email and email_candidate and str(email_candidate) != match_email:
                return None

            up = data.get("up")
            down = data.get("down")
            total = data.get("total")
            if isinstance(up, (int, float)) and isinstance(down, (int, float)):
                return InboundClientTraffic(
                    uploaded_bytes=int(up),
                    downloaded_bytes=int(down),
                    total_bytes=int(total) if isinstance(total, (int, float)) else int(up) + int(down),
                )

            # Some versions wrap under a list-like field.
            for candidate_key in ("data", "result", "clients", "list"):
                maybe = data.get(candidate_key)
                parsed = self._parse_traffic_from_any(
                    maybe,
                    match_client_id=match_client_id,
                    match_email=match_email,
                )
                if parsed is not None:
                    return parsed
            return None

        # List of clients.
        if isinstance(data, list):
            for item in data:
                parsed = self._parse_traffic_from_any(
                    item,
                    match_client_id=match_client_id,
                    match_email=match_email,
                )
                if parsed is not None:
                    return parsed
            return None

        return None

    # Helper methods for services/handlers could be added later.

