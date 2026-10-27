import pytest

from runtime.mongo_client import MongoClient, MongoError, connect
from scripts.mongo import main


class FakeCollection:
    def __init__(self, docs=None, count=0):
        self.docs = docs or [{"_id": "1", "level": "error"}]
        self.count_value = count
        self.calls = []

    def find(self, filter_, limit=0):
        self.calls.append(("find", filter_, limit))
        return list(self.docs)

    def aggregate(self, pipeline):
        self.calls.append(("aggregate", pipeline))
        return list(self.docs)

    def count_documents(self, filter_):
        self.calls.append(("count", filter_))
        return self.count_value

    def insert_one(self, doc):
        self.calls.append(("insert_one", doc))

    def insert_many(self, docs):
        self.calls.append(("insert_many", docs))

    def update_one(self, filter_, update):
        self.calls.append(("update_one", filter_, update))

    def update_many(self, filter_, update):
        self.calls.append(("update_many", filter_, update))

    def delete_one(self, filter_):
        self.calls.append(("delete_one", filter_))

    def delete_many(self, filter_):
        self.calls.append(("delete_many", filter_))


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        return self.collection


class FakeMongo:
    def __init__(self, collection=None):
        self.collection = collection or FakeCollection()

    def __getitem__(self, name):
        return FakeDatabase(self.collection)


def test_connect_requires_uri():
    with pytest.raises(MongoError, match="DEV_MONGO_URI"):
        connect({}, "DEV_MONGO", "hexin_logs")


def test_find_returns_documents():
    coll = FakeCollection(docs=[{"a": 1}, {"a": 2}])
    client = MongoClient("mongodb://h", "db", client=FakeMongo(coll))
    docs = client.run("logs", "find", {"a": 1}, limit=10)
    assert docs == [{"a": 1}, {"a": 2}]
    assert coll.calls == [("find", {"a": 1}, 10)]


def test_count_returns_number():
    client = MongoClient("mongodb://h", "db", client=FakeMongo(FakeCollection(count=7)))
    assert client.run("logs", "count", {}) == 7


def test_unknown_op_raises():
    client = MongoClient("mongodb://h", "db", client=FakeMongo())
    with pytest.raises(MongoError, match="未知操作"):
        client.run("logs", "drop", {})


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
    mongo_prefix: DEV_MONGO
    mongo_database: hexin_logs
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


def test_cli_prints_documents(project, capsys):
    coll = FakeCollection(docs=[{"a": 1}])
    rc = main(["--project", "demo", "--env", "dev", "--collection", "logs",
               "--find", '{"a": 1}'],
              connect_fn=lambda env, prefix, db: MongoClient("u", db, client=FakeMongo(coll)))
    out = capsys.readouterr().out
    assert rc == 0
    assert '"a": 1' in out


def test_cli_echoes_write_before_executing(project, capsys):
    coll = FakeCollection()
    rc = main(["--project", "demo", "--env", "dev", "--collection", "logs",
               "--update", '{"filter": {"a": 1}, "update": {"$set": {"b": 2}}}'],
              connect_fn=lambda env, prefix, db: MongoClient("u", db, client=FakeMongo(coll)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "update" in out and "dev" in out
    assert coll.calls == [("update_one", {"a": 1}, {"$set": {"b": 2}})]
