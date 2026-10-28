import pytest

from runtime.git_host.base import HostError
from runtime.git_host.gitlab import GitLabHost

FAKE = "fake-gitlab-token-999"


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


def test_create_mr_uses_encoded_project_path():
    sess = _Sess(body={"iid": 1819, "web_url": "http://g/mr/1819", "state": "opened", "merge_status": "can_be_merged"})
    host = GitLabHost("http://g", "hexincloud/hexincloud", FAKE, session=sess)
    mr = host.create_mr("feature/test/lsh/1-x", "test", "FMS 补全")
    method, url, kwargs = sess.calls[0]
    assert method == "POST"
    assert url == "http://g/api/v4/projects/hexincloud%2Fhexincloud/merge_requests"
    assert kwargs["json"] == {"source_branch": "feature/test/lsh/1-x", "target_branch": "test", "title": "FMS 补全"}
    assert kwargs["headers"]["PRIVATE-TOKEN"] == FAKE
    assert mr.number == "1819" and mr.mergeable is True


def test_get_mr_reads_status():
    sess = _Sess(status=200, body={"iid": 7, "web_url": "u", "state": "merged", "merge_status": "cannot_be_merged"})
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    mr = host.get_mr("7")
    assert mr.state == "merged" and mr.mergeable is False


def test_existing_mr_conflict_carries_existing_number():
    sess = _Sess(responses=[
        (409, {"message": ["Another open merge request already exists for this source branch: !1819"]}),
        (200, [{"iid": 1819, "web_url": "http://g/mr/1819", "state": "opened", "merge_status": "can_be_merged"}]),
    ])
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host.create_mr("feature/test/lsh/1-x", "test", "t")
    assert exc.value.status == 409
    assert exc.value.existing is not None
    assert exc.value.existing.number == "1819"


def test_forbidden_is_reported_as_permission_without_token():
    sess = _Sess(status=403, body={"message": "403 Forbidden"})
    host = GitLabHost("http://g", "a/b", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host.create_mr("feature/test/lsh/1-x", "test", "t")
    assert exc.value.status == 403
    assert FAKE not in str(exc.value)
