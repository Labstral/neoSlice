"""
Extract the LAST (most recent) version of each file from the transcript,
including all Edit operations applied in sequence.
This script reconstructs what each file should look like after all edits.
"""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

transcript = 'C:/Users/manup/.claude/projects/c--neoSlice/ee11104c-33e3-4503-bb4b-a2fc7e55d233.jsonl'

# Collect all operations in order
operations = []  # (line_num, op_type, file_path, old_str/content, new_str, replace_all)

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
                                c = item.get('input', {}).get('content', '')
                                operations.append((line_num, 'Write', fp, c, '', False))
                            elif name == 'Edit':
                                old_str = item.get('input', {}).get('old_string', '')
                                new_str = item.get('input', {}).get('new_string', '')
                                replace_all = item.get('input', {}).get('replace_all', False)
                                operations.append((line_num, 'Edit', fp, old_str, new_str, replace_all))
        except:
            pass

# Group by file, in order
files_ops = {}
for op in operations:
    fp = op[2]
    if fp not in files_ops:
        files_ops[fp] = []
    files_ops[fp].append(op)

print(f"Total files touched: {len(files_ops)}")
print(f"Total operations: {len(operations)}")
print()

# For each file, reconstruct from last Write + apply all subsequent Edits
output_dir = 'C:/neoSlice/recovered/'
import os
os.makedirs(output_dir, exist_ok=True)

for fp_win, ops in sorted(files_ops.items()):
    relative = fp_win.replace('C:\\neoSlice\\', '').replace('C:/neoSlice/', '').replace('\\', '/')

    # Find the last Write
    last_write_idx = -1
    for i, op in enumerate(ops):
        if op[1] == 'Write':
            last_write_idx = i

    if last_write_idx >= 0:
        # Start from Write content
        content = ops[last_write_idx][3]
        start_idx = last_write_idx + 1
    else:
        # No Write - start from current file on disk
        local_path = fp_win.replace('\\', '/')
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            start_idx = 0
        except:
            print(f"ERROR: Cannot read {relative}")
            continue

    # Apply all Edits after the last Write
    edit_ops = ops[start_idx:]
    applied = 0
    failed = []

    for op in edit_ops:
        if op[1] != 'Edit':
            continue
        old_str = op[3]
        new_str = op[4]
        replace_all = op[5]
        ln = op[0]

        if replace_all:
            if old_str in content:
                content = content.replace(old_str, new_str)
                applied += 1
            else:
                failed.append((ln, old_str[:50]))
        else:
            if old_str in content:
                content = content.replace(old_str, new_str, 1)
                applied += 1
            else:
                failed.append((ln, old_str[:50]))

    total_edits = len(edit_ops)
    fname = relative.replace('/', '_').replace('\\', '_')
    out_path = output_dir + fname

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)

    status = 'Write+Edits' if last_write_idx >= 0 else 'Disk+Edits'
    print(f"{relative}")
    print(f"  Source: {status}, Edits: {applied}/{total_edits} applied, {len(failed)} failed")
    if failed:
        for ln, old in failed[:3]:
            print(f"    Failed ln{ln}: '{old}'")
    print(f"  -> Saved to: {out_path}")
    print()

print("Done! Check C:/neoSlice/recovered/ for reconstructed files.")
