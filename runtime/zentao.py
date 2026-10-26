"""禅道 API v2 的薄客户端与采集。"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import requests

from .report_config import ZentaoConfig

API_ROOT = "/api.php/v2"
MAX_PAGES = 20
PAGE_SIZE = 1000

_TASK_DATE_KEYS = ("finishedDate", "finished", "realFinished")
_BUG_DATE_KEYS = ("resolvedDate", "resolved", "closedDate")


class ZentaoError(Exception):
    pass


class ZentaoClient:
    def __init__(
        self,
        base_url: str,
        account: str = "",
        password: str = "",
        token: str = "",
        cache_path: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.account = account
        self.password = password
        self.cache_path = Path(cache_path) if cache_path else self._default_cache_path()
        self.token = token or (self._cached_token() if not password else "")

    def login(self, force: bool = False) -> str:
        if self.token and not force:
            return self.token
        if not self.password:
            self._clear_cache()
            raise ZentaoError(
                "禅道缓存 token 已失效且未配置 password，请在 report.yaml 或 .env 补充 ZENTAO_PASSWORD"
            )
        try:
            resp = requests.post(
                f"{self.base_url}{API_ROOT}/users/login",
                json={"account": self.account, "password": self.password},
                timeout=15,
            )
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ZentaoError(f"禅道登录失败：{exc}") from exc

        token = (payload.get("data") or {}).get("token") or payload.get("token") or ""
        if not token:
            raise ZentaoError("禅道登录失败：响应中没有 token")
        self.token = str(token)
        self._write_cache()
        return self.token

    def get(self, path: str, params: dict | None = None, _retry: bool = True) -> dict:
        token = self.login()
        try:
            resp = requests.get(
                f"{self.base_url}{API_ROOT}{path}",
                params=params,
                headers={"token": token},
                timeout=30,
            )
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ZentaoError(f"禅道请求失败：{exc}") from exc

        message = str(payload.get("message") or payload.get("msg") or "")
        if "Not allowed" in message and _retry:
            self.login(force=True)
            return self.get(path, params, _retry=False)

        if str(payload.get("status") or "").lower() in {"fail", "error"}:
            raise ZentaoError(f"禅道接口报错：{message or payload.get('status')}")
        return payload

    def _default_cache_path(self) -> Path:
        override = os.getenv("ZENTAO_TOKEN_CACHE")
        return Path(override) if override else Path.home() / ".zentao-token.json"

    def _cached_token(self) -> str:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        if str(data.get("url") or "").rstrip("/") != self.base_url:
            return ""
        return str(data.get("token") or "")

    def _write_cache(self) -> None:
        try:
            self.cache_path.write_text(
                json.dumps(
                    {"url": self.base_url, "token": self.token, "account": self.account},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _clear_cache(self) -> None:
        try:
            self.cache_path.unlink()
        except OSError:
            pass


def _items_from(payload: dict, key: str) -> list[dict]:
    items = payload.get(key)
    return items if isinstance(items, list) else []


def _payload_total(payload: dict) -> int | None:
    candidates = [payload.get("total")]
    pager = payload.get("pager")
    if isinstance(pager, dict):
        candidates.append(pager.get("recTotal"))
    for value in candidates:
        if value is None:
            continue
        try:
            return int(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return None


def _pages(client: ZentaoClient, path: str, key: str, params: dict, warnings: list[str]) -> list[dict]:
    items: list[dict] = []
    seen: set = set()
    total: int | None = None

    for page in range(1, MAX_PAGES + 1):
        payload = client.get(path, {**params, "recPerPage": PAGE_SIZE, "pageID": page})
        if key not in payload:
            warnings.append(f"{path} 返回缺少 {key} 字段")
        if total is None:
            total = _payload_total(payload)

        added = 0
        for item in _items_from(payload, key):
            item_id = item.get("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(item)
            added += 1

        if added == 0:
            if total is not None and len(items) < total:
                warnings.append(f"{path} total={total}，实际只拉到 {len(items)} 条")
            break
        if total is not None and len(items) >= total:
            break
    else:
        warnings.append(f"{path} 达到最大分页数 {MAX_PAGES}，可能未拉全")

    return items


def _normalize(item: dict, date_keys: tuple[str, ...]) -> tuple[date, dict] | None:
    raw = next((item[key] for key in date_keys if item.get(key)), None)
    if raw is None:
        return None
    day = str(raw)[:10]
    try:
        when = date.fromisoformat(day)
    except ValueError:
        return None
    return when, {
        "id": item.get("id"),
        "title": item.get("name") or item.get("title") or "",
        "status": item.get("status", ""),
        "date": day,
    }


def collect_zentao(
    cfg: ZentaoConfig, start: date, end: date
) -> tuple[list[dict], list[dict], list[str]]:
    tasks: list[dict] = []
    bugs: list[dict] = []
    warnings: list[str] = []

    if cfg.api == "v1":
        return [], [], ["禅道 v1 驱动未实现，请改用 api: v2"]

    try:
        client = ZentaoClient(cfg.base_url, cfg.account, cfg.password)
        client.login()
    except ZentaoError as exc:
        return [], [], [f"禅道采集失败：{exc}"]

    executions: list[dict] = []
    for project_id in cfg.project_ids:
        try:
            executions.extend(
                _pages(client, f"/projects/{project_id}/executions", "executions", {}, warnings)
            )
        except ZentaoError as exc:
            warnings.append(f"禅道执行列表拉取失败（项目 {project_id}）：{exc}")

    unparsed = 0
    for execution in executions:
        execution_id = execution.get("id")
        if execution_id is None:
            continue
        try:
            items = _pages(
                client,
                f"/executions/{execution_id}/tasks",
                "tasks",
                {"browseType": "assignedtome"},
                warnings,
            )
        except ZentaoError as exc:
            warnings.append(f"禅道任务拉取失败（执行 {execution_id}）：{exc}")
            continue

        for item in items:
            parsed = _normalize(item, _TASK_DATE_KEYS)
            if parsed is None:
                unparsed += 1
                continue
            when, normalized = parsed
            if start <= when <= end:
                tasks.append({**normalized, "execution": execution_id})

    if cfg.product_id:
        try:
            items = _pages(
                client,
                f"/products/{cfg.product_id}/bugs",
                "bugs",
                {"browseType": "assignedtome"},
                warnings,
            )
        except ZentaoError as exc:
            warnings.append(f"禅道 Bug 拉取失败：{exc}")
            items = []

        for item in items:
            parsed = _normalize(item, _BUG_DATE_KEYS)
            if parsed is None:
                unparsed += 1
                continue
            when, normalized = parsed
            if start <= when <= end:
                bugs.append({**normalized, "product": cfg.product_id})

    if unparsed:
        warnings.append(f"未解析 {unparsed} 条：缺少日期字段")

    return tasks, bugs, warnings
