"""GitLab 适配器（v4 API）。"""

from __future__ import annotations

from urllib.parse import quote

from .base import GitHost, HostError, MergeRequest

_MERGEABLE = {"can_be_merged": True, "cannot_be_merged": False}


def _to_mr(body: dict) -> MergeRequest:
    return MergeRequest(
        number=str(body.get("iid", "")),
        url=str(body.get("web_url", "")),
        state=str(body.get("state", "")),
        mergeable=_MERGEABLE.get(str(body.get("merge_status", ""))),
    )


class GitLabHost(GitHost):
    def auth_headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.token}

    def _project(self) -> str:
        return f"/api/v4/projects/{quote(self.project_path, safe='')}"

    def create_mr(self, source: str, target: str, title: str) -> MergeRequest:
        try:
            body = self._request(
                "POST",
                f"{self._project()}/merge_requests",
                json={"source_branch": source, "target_branch": target, "title": title},
            )
        except HostError as exc:
            if exc.status == 409:
                existing = self._find_open(source, target)
                raise HostError(str(exc), status=409, existing=existing) from None
            raise
        if not isinstance(body, dict):
            raise HostError("POST 合并请求返回格式异常")
        return _to_mr(body)

    def get_mr(self, number: str) -> MergeRequest:
        body = self._request("GET", f"{self._project()}/merge_requests/{number}")
        if not isinstance(body, dict):
            raise HostError(f"GET 合并请求 {number} 返回格式异常")
        return _to_mr(body)

    def _find_open(self, source: str, target: str) -> MergeRequest | None:
        try:
            body = self._request(
                "GET",
                f"{self._project()}/merge_requests",
                params={"state": "opened", "source_branch": source, "target_branch": target},
            )
        except HostError:
            return None
        if not isinstance(body, list):
            return None
        return _to_mr(body[0]) if body else None
