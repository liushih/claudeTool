"""认证实现加载。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


class AuthError(Exception):
    pass


def _load(spec: str, root: Path):
    file_part, func_name = spec.split(":", 1)
    path = Path(root) / file_part
    module_spec = importlib.util.spec_from_file_location(f"auth_{abs(hash(path))}", path)
    if module_spec is None or module_spec.loader is None:
        raise AuthError(f"无法加载认证脚本 {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    func = getattr(module, func_name, None)
    if func is None:
        raise AuthError(f"{path} 中没有函数 {func_name}")
    return func


def build_auth(spec: dict | None, impl_root: Path | None):
    if not spec or spec.get("type") in (None, "none"):
        return None

    impl = spec.get("impl")
    if not impl:
        raise AuthError("auth.type 不是 none 时必须提供 impl")
    return _load(impl, impl_root or Path("."))()
