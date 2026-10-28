"""Gitee 适配器（REST v5，Pull Request）。"""

from __future__ import annotations

from .base import GitHost, HostError, MergeRequest


def _to_pr(body: dict) -> MergeRequest:
    mergeable = body.get("mergeable")
    return MergeRequest(
        number=str(body.get("number", "")),
        url=str(body.get("html_url", "")),
        state=str(body.get("state", "")),
        mergeable=mergeable if isinstance(mergeable, bool) else None,
    )


class GiteeHost(GitHost):
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.token}"}

    def _repo(self) -> str:
        return f"/api/v5/repos/{self.project_path}"

    def create_mr(self, source: str, target: str, title: str) -> MergeRequest:
        try:
            body = self._request(
                "POST",
                f"{self._repo()}/pulls",
                json={"head": source, "base": target, "title": title},
            )
        except HostError as exc:
            if exc.status == 422:
                existing = self._find_open(source, target)
                if existing is not None:
                    raise HostError(str(exc), status=422, existing=existing) from None
            raise
        if not isinstance(body, dict):
            raise HostError("POST 拉取请求返回格式异常")
        return _to_pr(body)

    def get_mr(self, number: str) -> MergeRequest:
        body = self._request("GET", f"{self._repo()}/pulls/{number}")
        if not isinstance(body, dict):
            raise HostError(f"GET 拉取请求 {number} 返回格式异常")
        return _to_pr(body)

    def _find_open(self, source: str, target: str) -> MergeRequest | None:
        try:
            body = self._request(
                "GET",
                f"{self._repo()}/pulls",
                params={"state": "open", "head": source, "base": target},
            )
        except HostError:
            return None
        if not isinstance(body, list) or not body:
            return None
        return _to_pr(body[0])
