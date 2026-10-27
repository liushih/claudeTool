import pytest

from runtime.redis_client import RedisClient, RedisError, connect
from scripts.redis import main


class FakeRedis:
    def __init__(self, value="v", scan=("0", ["a", "b"]), hash_=None):
        self.value = value
        self.scan_result = scan
        self.hash = hash_ or {"f": "1"}
        self.calls = []

    def execute_command(self, *parts):
        self.calls.append(list(parts))
        cmd = str(parts[0]).upper()
        if cmd == "SCAN":
            return self.scan_result
        if cmd == "HGETALL":
            return self.hash
        if cmd == "DEL":
            return 1
        return self.value


def test_connect_requires_host():
    with pytest.raises(RedisError, match="DEV_REDIS_HOST"):
        connect({}, "DEV_REDIS")


def test_connect_builds_client_from_env(monkeypatch):
    import runtime.redis_client as mod

    seen = {}
    monkeypatch.setattr(mod.redis, "Redis", lambda **kw: seen.update(kw) or FakeRedis())
    connect({"DEV_REDIS_HOST": "h", "DEV_REDIS_PORT": "6380",
             "DEV_REDIS_PASSWORD": "p", "DEV_REDIS_DB": "2"}, "DEV_REDIS")
    assert seen == {"host": "h", "port": 6380, "password": "p", "db": 2}


def test_command_returns_value_and_kind():
    client = RedisClient("h", 6379, client=FakeRedis())
    value, kind = client.command(["GET", "k"])
    assert value == "v" and kind == "string"


def test_scan_returns_keys():
    client = RedisClient("h", 6379, client=FakeRedis())
    value, kind = client.command(["SCAN", "0"])
    assert kind == "scan" and value == ["a", "b"]


def test_hgetall_returns_mapping():
    client = RedisClient("h", 6379, client=FakeRedis())
    value, kind = client.command(["HGETALL", "h"])
    assert kind == "hash" and value == {"f": "1"}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("BASE=http://x\n", encoding="utf-8")
    (proj / "adapter.yaml").write_text(
        """version: 1
project: demo
envs:
  dev:
    base_url: ${BASE}
    redis_prefix: DEV_REDIS
auth:
  type: none
entities:
  order:
    steps:
      - id: hook
        impl: hook.py:go
""",
        encoding="utf-8",
    )
    return tmp_path


def test_cli_echoes_write_before_executing(project, capsys):
    fake = FakeRedis()
    rc = main(["--project", "demo", "--env", "dev", "--cmd", "SET k v"],
              connect_fn=lambda env, prefix: RedisClient("h", 6379, client=fake))
    out = capsys.readouterr().out
    assert rc == 0
    assert "SET k v" in out and "dev" in out
    assert fake.calls == [["SET", "k", "v"]]


def test_cli_read_does_not_echo_command(project, capsys):
    fake = FakeRedis()
    main(["--project", "demo", "--env", "dev", "--cmd", "GET k"],
         connect_fn=lambda env, prefix: RedisClient("h", 6379, client=fake))
    out = capsys.readouterr().out
    assert out.strip() == "v"


def test_cli_warns_on_flushall(project, capsys):
    fake = FakeRedis()
    main(["--project", "demo", "--env", "dev", "--cmd", "FLUSHALL"],
         connect_fn=lambda env, prefix: RedisClient("h", 6379, client=fake))
    assert "警示" in capsys.readouterr().out
