import json, sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.read().split('\n')

blockmap = {}
for line in lines:
    line = line.strip()
    if not line.startswith('{'):
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(obj, dict) and isinstance(obj.get('block'), dict):
        blockmap.update(obj['block'])

blocks = {}
for bid, entry in blockmap.items():
    v = entry.get('value', {})
    if isinstance(v, dict):
        v = v.get('value', {})
    if not isinstance(v, dict):
        continue
    props = v.get('properties') or {}
    title = props.get('title') or []
    text = ''
    for part in title:
        if isinstance(part, list) and part and isinstance(part[0], str):
            text += part[0]
    blocks[bid] = {
        'type': v.get('type'),
        'text': text,
        'content': v.get('content') or [],
    }

print(f"# {len(blocks)} blocks", file=sys.stderr)

visited = set()


def walk(bid, depth):
    b = blocks.get(bid)
    if not b or bid in visited:
        return
    visited.add(bid)
    print('  ' * min(depth, 8) + f"[{b['type']}] {b['text']}")
    for child in b['content']:
        walk(child, depth + 1)


pages = [bid for bid, b in blocks.items() if b['type'] == 'page']
for p in pages:
    print(f"===== page {p} =====")
    walk(p, 1)
for bid in blocks:
    if bid not in visited:
        walk(bid, 0)
