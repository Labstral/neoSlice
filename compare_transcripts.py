import json
import difflib
import os

transcript = 'C:/Users/manup/.claude/projects/c--neoSlice/ee11104c-33e3-4503-bb4b-a2fc7e55d233.jsonl'

neofiles = {}
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
                            if isinstance(item, dict) and item.get('type') == 'tool_use' and item.get('name') == 'Write':
                                fp = item.get('input', {}).get('file_path', '')
                                c = item.get('input', {}).get('content', '')
                                if fp and 'neoSlice' in fp and fp.endswith('.py'):
                                    neofiles[fp] = (line_num, c)
        except:
            pass

print('=== COMPARISON: transcript vs current ===\n')
for fp_win, (ln, transcript_content) in sorted(neofiles.items()):
    # Convert Windows path to forward slashes
    local_path = fp_win.replace(chr(92), '/')

    fname = fp_win.split(chr(92))[-1] if chr(92) in fp_win else fp_win.split('/')[-1]
    relative = local_path.replace('C:/neoSlice/', '')

    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            current_content = f.read()

        tc_lines = transcript_content.splitlines()
        cc_lines = current_content.splitlines()

        if transcript_content.strip() == current_content.strip():
            print(f'[OK] {relative}  -- IDENTICAL')
        else:
            diff = list(difflib.unified_diff(tc_lines, cc_lines, lineterm='', n=0))
            added = [l for l in diff if l.startswith('+') and not l.startswith('+++')]
            removed = [l for l in diff if l.startswith('-') and not l.startswith('---')]
            print(f'[DIFF] {relative}')
            print(f'  Transcript: {len(tc_lines)} lines')
            print(f'  Current:    {len(cc_lines)} lines')
            print(f'  +{len(added)} added / -{len(removed)} removed lines')
            # Show first few diff lines
            for dl in diff[:30]:
                print(f'    {dl}')
            if len(diff) > 30:
                print(f'    ... ({len(diff)-30} more diff lines)')
    except Exception as e:
        print(f'[ERROR] {relative}: {e}')
