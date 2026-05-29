import json
import os
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

transcript = 'C:/Users/manup/.claude/projects/c--neoSlice/ee11104c-33e3-4503-bb4b-a2fc7e55d233.jsonl'

# Collect all Edit operations per file (only "Edit only" files - no Write)
edits_by_file = {}
writes_files = set()

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
                            if not fp.endswith('.py'):
                                continue

                            if name == 'Write':
                                writes_files.add(fp)
                            elif name == 'Edit':
                                old_str = item.get('input', {}).get('old_string', '')
                                new_str = item.get('input', {}).get('new_string', '')
                                replace_all = item.get('input', {}).get('replace_all', False)
                                if fp not in edits_by_file:
                                    edits_by_file[fp] = []
                                edits_by_file[fp].append((line_num, old_str, new_str, replace_all))
        except:
            pass

# Focus on "Edit only" files
edit_only_files = {fp: edits for fp, edits in edits_by_file.items() if fp not in writes_files}

print('=== VERIFICATION: EDIT-ONLY FILES ===\n')
print(f'Files modified only via Edit (no Write base): {len(edit_only_files)}\n')

for fp_win, edits in sorted(edit_only_files.items()):
    local_path = fp_win.replace('\\', '/')
    relative = local_path.replace('C:/neoSlice/', '')

    print(f'FILE: {relative} ({len(edits)} edits)')

    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            current_content = f.read()

        missing_new = []
        missing_old = []
        applied = []

        for ln, old_str, new_str, replace_all in edits:
            # Check if new_string is present (edit was applied)
            if new_str and new_str in current_content:
                applied.append((ln, new_str[:60]))
            elif old_str and old_str in current_content:
                # Old string still there = edit NOT applied
                missing_new.append((ln, old_str[:60], new_str[:60]))
            else:
                # Neither found - could be applied then overwritten, or old_str was unique
                # Check if old_str was meaningful
                if len(old_str) > 10:
                    missing_old.append((ln, old_str[:60], new_str[:60]))

        print(f'  Applied: {len(applied)}/{len(edits)}')
        if missing_new:
            print(f'  NOT APPLIED (old still present): {len(missing_new)}')
            for ln, old, new in missing_new:
                print(f'    Line {ln}: old="{old}"')
                print(f'             new="{new}"')
        if missing_old:
            print(f'  AMBIGUOUS (neither old nor new found): {len(missing_old)}')
            for ln, old, new in missing_old:
                print(f'    Line {ln}: "{old}" -> "{new}"')
        print()
    except FileNotFoundError:
        print(f'  ERROR: File not found at {local_path}\n')
    except Exception as e:
        print(f'  ERROR: {e}\n')

print('\n=== ALSO CHECK: Files with BOTH Write and many Edits ===\n')
# Files that have a Write + many edits (edits happened AFTER the Write)
both_files = [(fp, edits) for fp, edits in edits_by_file.items() if fp in writes_files and len(edits) > 10]
for fp_win, edits in sorted(both_files, key=lambda x: -len(x[1])):
    local_path = fp_win.replace('\\', '/')
    relative = local_path.replace('C:/neoSlice/', '')
    print(f'FILE: {relative} (Write + {len(edits)} edits)')

    try:
        with open(local_path, 'r', encoding='utf-8') as f:
            current_content = f.read()

        missing_new = []
        applied = []

        for ln, old_str, new_str, replace_all in edits:
            if new_str and new_str in current_content:
                applied.append(ln)
            elif old_str and old_str in current_content:
                missing_new.append((ln, old_str[:60], new_str[:60]))

        print(f'  Applied: {len(applied)}/{len(edits)}')
        if missing_new:
            print(f'  NOT APPLIED: {len(missing_new)}')
            for ln, old, new in missing_new:
                print(f'    Line {ln}: "{old}"')
        print()
    except Exception as e:
        print(f'  ERROR: {e}\n')
