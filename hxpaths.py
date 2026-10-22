"""跨机器路径解析。

默认按目录关系推断（claudeTool 与 hexincloud 同级），换机器时可用环境变量覆盖：

    HEXIN_REPO           hexincloud 仓库根目录
    HEXIN_SKILL_SCRIPTS  飞书台账脚本目录
    HEXIN_DB_ENV         hexin-db-tools/.env 路径
"""

import os
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO = Path(os.getenv("HEXIN_REPO") or TOOLS_DIR.parent / "hexincloud")
SKILL_SCRIPTS = Path(
    os.getenv("HEXIN_SKILL_SCRIPTS")
    or REPO / "dev-overlay/.agents/skills/hx-sql-feishu-progress/scripts"
)
DB_ENV_FILE = Path(os.getenv("HEXIN_DB_ENV") or TOOLS_DIR / "hexin-db-tools" / ".env")
