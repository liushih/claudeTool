"""git 托管的命令行入口。规则违反与平台错误统一以退出码 1 返回。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import config  # noqa: E402
from runtime.git_host import get_host  # noqa: E402
from runtime.git_host.base import HostError  # noqa: E402
from runtime.git_host.config import (  # noqa: E402
    GitHostConfigError,
    load_git_host_config,
    save_user_tag,
)
from runtime.git_host.repo import Repo, RepoError  # noqa: E402
from runtime.git_host.rules import RuleViolation, check_merge  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2

DIRECT_MERGE_FORBIDDEN = ("test", "prod")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多平台 git 托管")
    parser.add_argument("--project", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("commit")
    c.add_argument("-m", "--message", required=True)

    sub.add_parser("push").add_argument("--branch", required=False)

    m = sub.add_parser("merge")
    m.add_argument("--from", dest="source", required=True)
    m.add_argument("--to", dest="target", required=True)
    m.add_argument("--confirm-bring-in", action="store_true")

    mr = sub.add_parser("mr")
    mr_sub = mr.add_subparsers(dest="mr_cmd", required=True)
    create = mr_sub.add_parser("create")
    create.add_argument("--from", dest="source", required=True)
    create.add_argument("--to", dest="target", required=True)
    create.add_argument("--title", required=True)
    status = mr_sub.add_parser("status")
    status.add_argument("number")

    b = sub.add_parser("branch")
    b_sub = b.add_subparsers(dest="branch_cmd", required=True)
    bc = b_sub.add_parser("create")
    bc.add_argument("--name", required=True)
    bc.add_argument("--target", required=True)

    vf = sub.add_parser("verify-flow")
    vf.add_argument("--prod-branch", required=True)
    vf.add_argument("--test-branch", required=True)
    vf.add_argument("--target", required=True, choices=["dev", "test"])

    hf = sub.add_parser("hotfix")
    hf_sub = hf.add_subparsers(dest="hotfix_cmd", required=True)
    hs = hf_sub.add_parser("sync")
    hs.add_argument("--fix-branch", required=True)
    hs.add_argument("--task", required=True)

    t = sub.add_parser("set-user-tag")
    t.add_argument("tag")
    return parser


def main(argv: list[str] | None = None, host_fn=None, repo_fn=None) -> int:
    args = _build_parser().parse_args(argv)
    project = args.project

    try:
        if args.cmd == "set-user-tag":
            return _set_user_tag(project, args.tag)

        cfg = load_git_host_config(project)
        repo = (repo_fn or _default_repo)(cfg)

        if args.cmd == "commit":
            short = repo.commit(args.message, forbidden=cfg.forbid_commit_paths)
            print(f"已提交 {short}")
            return EXIT_OK

        if args.cmd == "push":
            branch = args.branch or repo.current_branch()
            repo.push(branch)
            print(f"已推送 {branch}")
            return EXIT_OK

        if args.cmd == "merge":
            if args.target in DIRECT_MERGE_FORBIDDEN:
                check_merge(args.source, args.target, None, [])
            repo.merge(args.source, args.target, None, list(DIRECT_MERGE_FORBIDDEN), args.confirm_bring_in)
            print(f"已合并 {args.source} → {args.target}")
            return EXIT_OK

        if args.cmd == "verify-flow":
            report = repo.verify_flow(args.prod_branch, args.test_branch, args.target)
            _print_flow(report)
            return EXIT_OK if report.safe else EXIT_FAIL

        if args.cmd == "hotfix":
            commits = repo.hotfix_commits(args.fix_branch)
            new = repo.cherry_pick(commits)
            print(f"已同步 {len(new)} 个热修提交（任务 {args.task}）")
            return EXIT_OK

        host = (host_fn or _default_host)(project)

        if args.cmd == "mr":
            if args.mr_cmd == "create":
                mr = host.create_mr(args.source, args.target, args.title)
                print(f"已创建 MR !{mr.number} {mr.url}")
                return EXIT_OK
            mr = host.get_mr(args.number)
            print(f"MR !{mr.number} 状态 {mr.state}，可合并 {mr.mergeable}")
            return EXIT_OK

        if args.cmd == "branch":
            repo.create_branch(args.name, args.target)
            print(f"已从 origin/{args.target} 切出 {args.name}")
            return EXIT_OK

    except RuleViolation as exc:
        print(f"[{exc.rule}] {exc.message}")
        return EXIT_FAIL
    except HostError as exc:
        if exc.status == 409 or exc.status == 422:
            existing = exc.existing
            if existing is not None:
                print(f"[HTTP {exc.status}] 已存在 MR !{existing.number} {existing.url}")
                return EXIT_FAIL
        prefix = f"[HTTP {exc.status}] " if exc.status else ""
        print(f"{prefix}{exc}")
        return EXIT_FAIL
    except RepoError as exc:
        print(f"[git] {exc}")
        return EXIT_FAIL
    except GitHostConfigError as exc:
        print(f"[配置] {exc}")
        return EXIT_USAGE

    return EXIT_USAGE


def _set_user_tag(project: str, tag: str) -> int:
    cfg = load_git_host_config(project)
    if cfg.user_tag:
        print(f"[配置] user_tag 已是 {cfg.user_tag}，如需修改请手工编辑 git_hosts.yaml")
        return EXIT_USAGE
    save_user_tag(project, tag)
    print(f"user_tag: {tag}")
    return EXIT_OK


def _default_repo(cfg) -> Repo:
    return Repo(cfg.repo_path)


def _default_host(project: str):
    return get_host(project)


def _print_flow(report) -> None:
    def show(title, commits):
        print(f"{title}：{len(commits)} 个提交")
        for c in commits:
            print(f"  {c.hash[:7]} {c.subject}")

    show("A. prod 带入 test 衍生分支", report.prod_into_test)
    show("B. test 衍生分支相对 test 的净增量", report.test_net_vs_test)
    show("C. test 衍生分支相对 dev 的净增量", report.test_net_vs_target)
    if report.prod_only:
        print(f"[危险] 存在 prod 独有提交 {len(report.prod_only)} 个，已停止后续合并")


if __name__ == "__main__":
    raise SystemExit(main())
