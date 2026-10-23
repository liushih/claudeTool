"""HTTP 请求：拼接、超时、重试。"""

from __future__ import annotations

import requests


class HttpClientError(Exception):
    pass


class HttpClient:
    def __init__(self, base_url: str, auth=None, timeout: float = 15.0, retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def request(self, method: str, path: str, json=None, params=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self.auth.apply({}) if self.auth is not None else {}
        last: Exception | None = None

        for _ in range(self.retries + 1):
            try:
                resp = self.session.request(
                    method, url, json=json, params=params, headers=headers, timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
                continue

            if resp.status_code >= 400:
                raise HttpClientError(f"{method} {url} 返回 {resp.status_code}")
            return resp.json()

        raise HttpClientError(f"{method} {url} 连接失败：{last}")
