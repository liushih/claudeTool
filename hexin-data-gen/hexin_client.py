"""hexincloud dev 环境 HTTP 客户端：复刻前端登录加密（AES-ECB + RSA 包装密钥）。"""

from __future__ import annotations

import base64
import json
import os
import random
import string
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def _load_dotenv() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

BASE_URL = os.getenv("HEXIN_BASE_URL", "").rstrip("/")
CLIENT_ID = os.getenv("HEXIN_CLIENT_ID", "")
USERNAME = os.getenv("HEXIN_USERNAME", "admin")
PASSWORD = os.getenv("HEXIN_PASSWORD", "")
TENANT_ID = os.getenv("HEXIN_TENANT_ID", "000000")

_missing = [k for k, v in (("HEXIN_BASE_URL", BASE_URL), ("HEXIN_CLIENT_ID", CLIENT_ID)) if not v]
if _missing:
    raise RuntimeError(f"缺少配置 {', '.join(_missing)}：请在 hexin-data-gen/.env 中设置")

# 前端 JSEncrypt 使用的公钥（对应后端 api-decrypt 私钥）
RSA_PUBLIC_KEY_B64 = (
    "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAKoR8mX0rGKLqzcWmOzbfj64K8ZIgOdHnzkXSOVOZbFu"
    "/TJhZ7rFAN+eaGkl3C4buccQd/EjEsj9ir7ijT7h96MCAwEAAQ=="
)

TOKEN_FILE = Path(__file__).with_name(".token.json")


def _random_aes_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(32))


def _aes_encrypt(plain: str, key: str) -> str:
    raw = plain.encode("utf-8")
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad
    encryptor = Cipher(algorithms.AES(key.encode("utf-8")), modes.ECB()).encryptor()
    return base64.b64encode(encryptor.update(raw) + encryptor.finalize()).decode()


def _aes_decrypt(cipher_b64: str, key: str) -> str:
    raw = base64.b64decode(cipher_b64)
    decryptor = Cipher(algorithms.AES(key.encode("utf-8")), modes.ECB()).decryptor()
    plain = decryptor.update(raw) + decryptor.finalize()
    return plain[: -plain[-1]].decode("utf-8")


def _rsa_encrypt(text: str) -> str:
    public_key = serialization.load_der_public_key(base64.b64decode(RSA_PUBLIC_KEY_B64))
    cipher_text = public_key.encrypt(text.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(cipher_text).decode()


@dataclass
class ApiResult:
    code: int
    msg: str
    data: object
    raw: dict

    @property
    def ok(self) -> bool:
        return self.code == 200

    def __str__(self) -> str:
        body = json.dumps(self.data, ensure_ascii=False)
        if len(body) > 600:
            body = body[:600] + "..."
        return f"code={self.code} msg={self.msg} data={body}"


class HexinClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.token: str | None = None
        self._load_token()

    # ---------- 登录 ----------
    def _load_token(self) -> None:
        if not TOKEN_FILE.exists():
            return
        try:
            payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        if payload.get("expires_at", 0) > time.time() + 60:
            self.token = payload.get("access_token")

    def _save_token(self, token: str, expire_in: int) -> None:
        TOKEN_FILE.write_text(
            json.dumps(
                {"access_token": token, "expires_at": time.time() + expire_in - 120},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def login(self, force: bool = False) -> str:
        if self.token and not force:
            return self.token
        body = {
            "clientId": CLIENT_ID,
            "grantType": "password",
            "tenantId": TENANT_ID,
            "username": USERNAME,
            "password": PASSWORD,
        }
        aes_key = _random_aes_key()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "clientid": CLIENT_ID,
            "encrypt-key": _rsa_encrypt(base64.b64encode(aes_key.encode()).decode()),
        }
        resp = self.session.post(
            f"{BASE_URL}/auth/login",
            data=_aes_encrypt(json.dumps(body), aes_key),
            headers=headers,
            timeout=30,
        )
        payload = resp.json()
        if payload.get("code") != 200:
            raise RuntimeError(f"登录失败: HTTP {resp.status_code} {payload}")
        data = payload["data"]
        self.token = data["access_token"]
        self._save_token(self.token, int(data.get("expire_in", 7200)))
        return self.token

    # ---------- 通用请求 ----------
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.login()}",
            "clientid": CLIENT_ID,
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _parse(self, resp: requests.Response) -> ApiResult:
        try:
            payload = resp.json()
        except Exception:
            raise RuntimeError(f"非 JSON 响应 HTTP {resp.status_code}: {resp.text[:500]}")
        return ApiResult(
            code=payload.get("code", -1),
            msg=payload.get("msg", ""),
            data=payload.get("data"),
            raw=payload,
        )

    def get(self, path: str, params: dict | None = None) -> ApiResult:
        resp = self.session.get(f"{BASE_URL}{path}", params=params, headers=self._headers(), timeout=60)
        return self._parse(resp)

    def post(self, path: str, body: object = None, params: dict | None = None) -> ApiResult:
        resp = self.session.post(
            f"{BASE_URL}{path}",
            data=json.dumps(body, ensure_ascii=False) if body is not None else None,
            params=params,
            headers=self._headers(),
            timeout=120,
        )
        return self._parse(resp)

    def put(self, path: str, body: object = None) -> ApiResult:
        resp = self.session.put(
            f"{BASE_URL}{path}",
            data=json.dumps(body, ensure_ascii=False) if body is not None else None,
            headers=self._headers(),
            timeout=60,
        )
        return self._parse(resp)

    def post_multipart(self, path: str, files: dict, params: dict | None = None) -> ApiResult:
        headers = self._headers()
        headers.pop("Content-Type", None)
        resp = self.session.post(f"{BASE_URL}{path}", files=files, params=params, headers=headers, timeout=120)
        return self._parse(resp)


if __name__ == "__main__":
    client = HexinClient()
    token = client.login(force=True)
    print("login ok, token:", token[:12] + "...")  # noqa: secrets
    print(client.get("/wms/deliveryOrder/list", {"pageNum": 1, "pageSize": 1}))
