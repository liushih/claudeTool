"""托管平台的公共基类：统一请求、错误处理和令牌脱敏。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

READ_TIMEOUT = 30
WRITE_TIMEOUT = 60
MESSAGE_LIMIT = 200


class HostError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class MergeRequest:
    number: str
    url: str
    state: str
    mergeable: bool | None


class GitHost(ABC):
    def __init__(self, base_url: str, project_path: str, token: str, session=None):
        self.base_url = base_url.rstrip("/")
        self.project_path = project_path
        self.token = token
        self.session = session or requests.Session()

    @abstractmethod
    def create_mr(self, source: str, target: str, title: str) -> MergeRequest:
        ...

    @abstractmethod
    def get_mr(self, number: str) -> MergeRequest:
        ...

    @abstractmethod
    def auth_headers(self) -> dict[str, str]:
        ...

    def _redact(self, text: str) -> str:
        if self.token:
            return text.replace(self.token, "***")
        return text

    def _request(self, method: str, path: str, *, json=None, params=None) -> dict:
        url = f"{self.base_url}{path}"
        timeout = READ_TIMEOUT if method.upper() == "GET" else WRITE_TIMEOUT
        try:
            resp = self.session.request(
                method, url, json=json, params=params,
                headers=self.auth_headers(), timeout=timeout,
            )
        except requests.RequestException as exc:
            raise HostError(self._redact(f"{method} {path} 连接失败：{type(exc).__name__}")) from None

        try:
            body = resp.json()
        except ValueError:
            body = {}

        if resp.status_code >= 400:
            detail = ""
            if isinstance(body, dict):
                raw = body.get("message") or body.get("error") or ""
                detail = str(raw)[:MESSAGE_LIMIT]
            message = f"{method} {path} 失败（HTTP {resp.status_code}）"
            if detail:
                message += f"：{self._redact(detail)}"
            raise HostError(message, status=resp.status_code)

        return body if isinstance(body, dict) else {}
