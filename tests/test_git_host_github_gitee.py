from runtime.git_host.base import HostError
from runtime.git_host.github import GitHubHost
from runtime.git_host.gitee import GiteeHost

FAKE = "fake-platform-token-777"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Sess:
    def __init__(self, status=201, body=None, responses=None):
        self.status = status
        self.body = body or {}
        self.responses = list(responses or [])
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.responses:
            status, body = self.responses.pop(0)
            return _Resp(status, body)
        return _Resp(self.status, self.body)


def test_github_pr_uses_bearer_and_head_base():
    sess = _Sess(body={"number": 42, "html_url": "https://github.com/o/r/pull/42", "state": "open", "mergeable": True})
    host = GitHubHost("https://api.github.com", "o/r", FAKE, session=sess)
    pr = host.create_mr("feature/dev/lsh/1-x", "dev", "t")
    method, url, kwargs = sess.calls[0]
    assert method == "POST" and url == "https://api.github.com/repos/o/r/pulls"
    assert kwargs["json"] == {"head": "feature/dev/lsh/1-x", "base": "dev", "title": "t"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE}"
    assert pr.number == "42" and pr.mergeable is True


def test_github_unknown_mergeable_is_none():
    sess = _Sess(status=200, body={"number": 1, "html_url": "u", "state": "open"})
    host = GitHubHost("https://api.github.com", "o/r", FAKE, session=sess)
    assert host.get_mr("1").mergeable is None


def test_github_existing_pr_422_reports_existing_number():
    sess = _Sess(responses=[
        (422, {"message": "Validation Failed", "errors": [{"message": "A pull request already exists"}]}),
        (200, [{"number": 42, "html_url": "https://github.com/o/r/pull/42", "state": "open", "mergeable": True}]),
    ])
    host = GitHubHost("https://api.github.com", "o/r", FAKE, session=sess)
    try:
        host.create_mr("feature/dev/lsh/1-x", "dev", "t")
    except HostError as exc:
        assert exc.existing is not None and exc.existing.number == "42"
    else:
        raise AssertionError("expected HostError")


def test_gitee_pr_puts_token_only_in_header():
    sess = _Sess(body={"number": 9, "html_url": "https://gitee.com/o/r/pulls/9", "state": "open", "mergeable": False})
    host = GiteeHost("https://gitee.com", "o/r", FAKE, session=sess)
    pr = host.create_mr("feature/test/lsh/1-x", "test", "t")
    method, url, kwargs = sess.calls[0]
    assert url == "https://gitee.com/api/v5/repos/o/r/pulls"
    assert "access_token" not in kwargs["json"]
    assert kwargs["headers"]["Authorization"] == f"token {FAKE}"
    assert pr.number == "9" and pr.mergeable is False


def test_gitee_existing_pr_reports_existing_number():
    sess = _Sess(responses=[
        (422, {"message": "已存在相同的 Pull Request"}),
        (200, [{"number": 9, "html_url": "https://gitee.com/o/r/pulls/9", "state": "open", "mergeable": False}]),
    ])
    host = GiteeHost("https://gitee.com", "o/r", FAKE, session=sess)
    try:
        host.create_mr("feature/test/lsh/1-x", "test", "t")
    except HostError as exc:
        assert exc.existing is not None and exc.existing.number == "9"
    else:
        raise AssertionError("expected HostError")
