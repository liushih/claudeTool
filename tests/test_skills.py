from pathlib import Path

import pytest
import yaml

SKILLS = Path(__file__).resolve().parents[1] / "skills"


@pytest.mark.parametrize("name", ["data-gen-core", "db-access", "adapter-bootstrap", "report-writer"])
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
