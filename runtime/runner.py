"""按 adapter 执行单条业务链。"""

from __future__ import annotations

import importlib.util
import re
import threading
import time
from pathlib import Path

from .adapter import Entity, Step

POLL_INTERVAL = 0.5

_REF = re.compile(r"\$\{([^}]+)\}")


class RunError(Exception):
    pass


def _lookup(ref: str, ctx: dict):
    parts = ref.split(".")
    if parts[0] == "ctx":
        value = ctx
        parts = parts[1:]
    elif parts[0] == "prev":
        value = ctx["values"]
        parts = parts[1:]
    else:
        raise RunError(f"未知引用 {ref}")

    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise RunError(f"引用不存在 {ref}")
        value = value[part]
    return value


def _resolve(value, ctx):
    if isinstance(value, str):
        whole = _REF.fullmatch(value)
        if whole:
            return _lookup(whole.group(1), ctx)
        return _REF.sub(lambda m: str(_lookup(m.group(1), ctx)), value)
    if isinstance(value, dict):
        return {k: _resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, ctx) for v in value]
    return value


def _until(expr: str | None, resp, ctx: dict) -> bool:
    if not expr:
        return True
    return bool(eval(expr, {"__builtins__": {}}, {"resp": resp, "ctx": ctx}))


def _load_impl(spec: str, root: Path):
    file_part, func_name = spec.split(":", 1)
    path = Path(root) / file_part
    module_spec = importlib.util.spec_from_file_location(f"impl_{abs(hash(path))}", path)
    if module_spec is None or module_spec.loader is None:
        raise RunError(f"无法加载脚本 {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    func = getattr(module, func_name, None)
    if func is None:
        raise RunError(f"{path} 中没有函数 {func_name}")
    return func


def _run_step(step: Step, client, ctx: dict, impl_root: Path | None) -> None:
    if step.call:
        method, path = step.call.split(" ", 1)
        ctx["values"][step.id] = client.request(
            method, path,
            json=_resolve(step.body, ctx),
            params=_resolve(step.params, ctx),
        )
    elif step.poll:
        method, path = step.poll.split(" ", 1)
        deadline = time.monotonic() + step.timeout
        while True:
            resp = client.request(method, path, params=_resolve(step.params, ctx))
            if _until(step.until, resp, ctx):
                break
            if time.monotonic() >= deadline:
                raise RunError(f"timeout: {step.id}")
            time.sleep(POLL_INTERVAL)
        ctx["values"][step.id] = resp
    elif step.impl:
        func = _load_impl(step.impl, impl_root or Path("."))
        ctx["values"][step.id] = func(ctx, None)
    else:
        raise RunError(f"步骤 {step.id} 没有可执行内容")
    ctx["stage"] = step.id


def run_entity(entity: Entity, client, ctx: dict, impl_root: Path | None = None) -> dict:
    ctx.setdefault("values", {})
    by_id = {step.id: step for step in entity.steps}
    executed: set[str] = set()
    running: set[str] = set()

    def execute(step: Step) -> None:
        if step.id in executed:
            return
        if step.id in running:
            raise RunError(f"步骤依赖成环：{step.id}")
        running.add(step.id)
        for pre in step.before:
            if pre not in by_id:
                raise RunError(f"步骤 {step.id} 依赖的 {pre} 不存在")
            execute(by_id[pre])
        _run_step(step, client, ctx, impl_root)
        running.discard(step.id)
        executed.add(step.id)

    for step in entity.steps:
        execute(step)

    return ctx


def run_batch(entity: Entity, client_factory, count: int, workers: int,
              run_id: str, ledger, impl_root: Path | None = None, verify=None,
              env: dict | None = None) -> dict:
    done = ledger.read_done(run_id)
    todo = [i for i in range(count) if i not in done]
    if not todo:
        return {"done": 0, "failed": 0, "failures": []}

    workers = max(1, min(workers, len(todo)))
    chunks = [todo[i::workers] for i in range(workers)]
    counter = {"done": 0, "failed": 0}
    failures: list[tuple[int, str]] = []
    lock = threading.Lock()

    def work(indexes: list[int]) -> None:
        client = None
        for idx in indexes:
            external_no = ""
            ctx = {"external_no": "", "values": {}, "stage": "init",
                   "env": env or {}, "stop_at": entity.stop_at}
            try:
                external_no = entity.id_rule.format(run_id=run_id, idx=idx)
                ctx["external_no"] = external_no
                if client is None:
                    client = client_factory()
                run_entity(entity, client, ctx, impl_root)
                if verify is not None:
                    ok, got = verify(ctx)
                    if not ok:
                        raise RunError(f"verify 未通过：实际 {got}")
            except Exception as exc:  # noqa: BLE001
                reason = f"{type(exc).__name__}: {exc}"
                with lock:
                    counter["failed"] += 1
                    failures.append((idx, reason))
                ledger.append({
                    "run_id": run_id, "idx": idx, "external_no": external_no,
                    "stage": ctx.get("stage", ""), "status": "failed", "error": reason,
                })
            else:
                with lock:
                    counter["done"] += 1
                ledger.append({
                    "run_id": run_id, "idx": idx, "external_no": external_no,
                    "stage": ctx.get("stage", ""), "status": "done",
                })

    threads = [
        threading.Thread(target=work, args=(chunk,), daemon=True)
        for chunk in chunks if chunk
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return {"done": counter["done"], "failed": counter["failed"], "failures": failures}
