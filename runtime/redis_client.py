"""Redis 连接与命令执行。"""

from __future__ import annotations

import redis

WRITE_COMMANDS = {
    "SET", "SETEX", "SETNX", "GETSET", "MSET", "DEL", "UNLINK", "EXPIRE", "EXPIREAT",
    "PERSIST", "RENAME", "HSET", "HMSET", "HDEL", "HINCRBY", "LPUSH", "RPUSH",
    "LPOP", "RPOP", "LSET", "LREM", "SADD", "SREM", "SPOP", "ZADD", "ZREM",
    "INCR", "DECR", "INCRBY", "DECRBY", "FLUSHDB", "FLUSHALL",
}
DESTRUCTIVE_COMMANDS = {"FLUSHALL", "FLUSHDB"}


class RedisError(Exception):
    pass


class RedisClient:
    def __init__(self, host: str, port=6379, password: str = "", db=0, client=None):
        self.client = client or redis.Redis(
            host=host, port=int(port), password=password, db=int(db)
        )

    def command(self, parts: list[str]) -> tuple[object, str]:
        if not parts:
            raise RedisError("命令为空")
        result = self.client.execute_command(*parts)
        name = parts[0].upper()

        if name == "SCAN":
            _cursor, keys = result
            return _decode(list(keys)), "scan"
        if name == "HGETALL":
            if isinstance(result, dict):
                return _decode(result), "hash"
            return _decode(dict(zip(result[::2], result[1::2]))), "hash"

        value = _decode(result)
        return value, _kind(value)


def connect(env: dict, prefix: str) -> RedisClient:
    host = env.get(f"{prefix}_HOST")
    if not host:
        raise RedisError(f"{prefix}_HOST 未配置")
    return RedisClient(
        host,
        port=env.get(f"{prefix}_PORT", 6379),
        password=env.get(f"{prefix}_PASSWORD", ""),
        db=env.get(f"{prefix}_DB", 0),
    )


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_decode(item) for item in value)
    if isinstance(value, dict):
        return {_decode(key): _decode(item) for key, item in value.items()}
    return value


def _kind(value) -> str:
    if value is None:
        return "nil"
    if isinstance(value, dict):
        return "hash"
    if isinstance(value, (list, tuple)):
        return "list"
    return "string"
