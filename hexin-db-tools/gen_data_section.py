import json, re
from pathlib import Path

REPO = Path(r"C:/project/hexincloud")
rows = json.load(open('ledger.json', encoding='utf-8'))
led = {r[1].strip().replace(chr(92), '/'): r for r in rows}
paths = []
for p in (REPO / 'script/sql/releases').glob('20*/**/*.sql'):
    rel = p.relative_to(REPO).as_posix()
    if any(f'/{k}/' in rel for k in ('migrate', 'seed', 'validate')) or re.search(r'/dml/\d+_', p.name):
        paths.append(rel)
print("## E. 数据类脚本（migrate / seed / dml 直放）执行状态")
print()
print("| 日包 | 脚本 | dev | test | prod | 备注 |")
print("|---|---|---|---|---|---|")
for p in sorted(paths):
    r = led.get(p)
    if r:
        dev, test, prod = r[4] or '', r[5] or '', r[7] or ''
        note = (r[8] or '').replace('|', '/')[:110]
    else:
        dev = test = prod = '-'
        note = '台账未登记'
    short = p.split('releases/')[1]
    print(f"| {short.split('/')[0]} | `{short}` | {dev} | {test} | {prod} | {note} |")
