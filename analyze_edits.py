import json
from collections import defaultdict

transcript = 'C:/Users/manup/.claude/projects/c--neoSlice/ee11104c-33e3-4503-bb4b-a2fc7e55d233.jsonl'

# Collect all Edit operations per file
edits_by_file = defaultdict(list)
writes_by_file = {}

with open(transcript, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get('type') == 'assistant':
                msg = obj.get('message', {})
                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get('type') != 'tool_use':
                                continue
                            name = item.get('name', '')
                            fp = item.get('input', {}).get('file_path', '')
                            if not fp or 'neoSlice' not in fp:
                                continue
                            if not (fp.endswith('.py') or fp.endswith('.json') or fp.endswith('.spec')):
                                continue

                            if name == 'Write':
                                c = item.get('input', {}).get('content', '')
                                writes_by_file[fp] = (line_num, len(c.splitlines()))
                            elif name == 'Edit':
                                old_str = item.get('input', {}).get('old_string', '')
                                new_str = item.get('input', {}).get('new_string', '')
                                edits_by_file[fp].append((line_num, old_str[:80], new_str[:80]))
        except:
            pass

# All files touched
all_files = set(list(writes_by_file.keys()) + list(edits_by_file.keys()))

print('=== FILES TOUCHED IN ee11104c TRANSCRIPT ===\n')
print(f'Files with Write: {len(writes_by_file)}')
print(f'Files with Edit only: {len([f for f in edits_by_file if f not in writes_by_file])}')
print(f'Total unique files: {len(all_files)}')
print()

print('=== DETAIL BY FILE ===\n')
for fp in sorted(all_files):
    relative = fp.replace('C:\\neoSlice\\', '').replace('C:/neoSlice/', '').replace('\\', '/')
    w = writes_by_file.get(fp)
    e = edits_by_file.get(fp, [])
    status = []
    if w:
        status.append(f'Write(line {w[0]}, {w[1]} lines)')
    if e:
        status.append(f'{len(e)} Edit(s)')
    print(f'{relative}')
    print(f'  -> {" + ".join(status)}')
print()

print('=== FILES ONLY EDITED (no Write) - CRITICAL for recovery ===\n')
for fp in sorted(edits_by_file.keys()):
    if fp not in writes_by_file:
        relative = fp.replace('C:\\neoSlice\\', '').replace('C:/neoSlice/', '').replace('\\', '/')
        edits = edits_by_file[fp]
        print(f'{relative} ({len(edits)} edits)')
        for ln, old, new in edits:
            print(f'  Line {ln}: "{old[:60]}..." -> "{new[:60]}..."')
        print()
