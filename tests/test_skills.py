from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[1] / "skills"


@pytest.mark.parametrize("name", ["data-gen-core", "db-access", "adapter-bootstrap", "report-writer", "git-workflow"])
def test_skill_has_frontmatter_and_sections(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    for section in ["## 适用场景", "## 前置检查", "## 执行", "## 失败处理"]:
        assert section in text


def test_report_skill_asks_audience_and_scope():
    text = (SKILLS / "report-writer" / "SKILL.md").read_text(encoding="utf-8")
    assert "给谁" in text
    assert "不猜" in text
    assert "collect.py" in text


def test_report_skill_asks_role():
    text = (SKILLS / "report-writer" / "SKILL.md").read_text(encoding="utf-8")
    assert "角色" in text
    assert ".role" in text
    for role in ["开发", "测试", "产品"]:
        assert role in text


def test_db_access_covers_redis_and_mongo():
    text = (SKILLS / "db-access" / "SKILL.md").read_text(encoding="utf-8")
    assert "redis.py" in text
    assert "mongo.py" in text


def test_data_gen_requires_adapter_and_forbids_improvisation():
    text = (SKILLS / "data-gen-core" / "SKILL.md").read_text(encoding="utf-8")
    assert "adapter-bootstrap" in text
    assert "不允许现场推导" in text


def test_trigger_routing_covers_all_intents():
    text = (SKILLS / "_references" / "trigger-routing.md").read_text(encoding="utf-8")
    for word in ["造数", "连库", "接入", "报告", "沉淀"]:
        assert word in text
    assert "report-writer" in text


def test_adapter_example_parses():
    data = yaml.safe_load(
        (SKILLS / "_TEMPLATE" / "adapter.example.yaml").read_text(encoding="utf-8")
    )
    assert data["version"] == 1 and "entities" in data


def test_git_skill_requires_user_tag_and_confirmation():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "user_tag" in text
    assert "set-user-tag" in text
    assert "回显" in text
    assert "确认" in text
    assert "git_host.py" in text


def test_git_skill_forbids_pasting_token_in_chat():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "不要让用户把令牌贴进对话" in text


def test_git_skill_routes_test_and_prod_merge_to_mr():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "mr create" in text
    assert "test" in text and "prod" in text


def test_git_skill_reports_existing_mr_on_conflict():
    text = (SKILLS / "git-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "409" in text and "422" in text
    assert "已存在" in text
