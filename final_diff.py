"""
Compare recovered files with current repo files.
Show exact diffs for files that differ significantly.
"""
import os
import difflib
import sys

sys.stdout.reconfigure(encoding='utf-8')

recovered_dir = 'C:/neoSlice/recovered/'

# Map recovered filename -> repo path
file_map = {
    'core_export_pdf_generator.py': 'C:/neoSlice/core/export/pdf_generator.py',
    'core_export_tmf_builder.py': 'C:/neoSlice/core/export/tmf_builder.py',
    'core_geometry_analysis_report.py': 'C:/neoSlice/core/geometry/analysis_report.py',
    'core_geometry_layer_slicer.py': 'C:/neoSlice/core/geometry/layer_slicer.py',
    'core_geometry_orientation_optimizer.py': 'C:/neoSlice/core/geometry/orientation_optimizer.py',
    'core_geometry_overhang_detector.py': 'C:/neoSlice/core/geometry/overhang_detector.py',
    'core_geometry_stability_analyzer.py': 'C:/neoSlice/core/geometry/stability_analyzer.py',
    'core_geometry_stl_loader.py': 'C:/neoSlice/core/geometry/stl_loader.py',
    'core_geometry_support_detector.py': 'C:/neoSlice/core/geometry/support_detector.py',
    'core_i18n.py': 'C:/neoSlice/core/i18n.py',
    'core_parameters_parameter_engine.py': 'C:/neoSlice/core/parameters/parameter_engine.py',
    'core_parameters_print_config.py': 'C:/neoSlice/core/parameters/print_config.py',
    'core_prefs.py': 'C:/neoSlice/core/prefs.py',
    'core_updater.py': 'C:/neoSlice/core/updater.py',
    'main.py': 'C:/neoSlice/main.py',
    'ui_components_analysis_panel.py': 'C:/neoSlice/ui/components/analysis_panel.py',
    'ui_components_drop_zone.py': 'C:/neoSlice/ui/components/drop_zone.py',
    'ui_components_filament_printer_selector.py': 'C:/neoSlice/ui/components/filament_printer_selector.py',
    'ui_components_intent_selector.py': 'C:/neoSlice/ui/components/intent_selector.py',
    'ui_components_params_preview.py': 'C:/neoSlice/ui/components/params_preview.py',
    'ui_components_settings_dialog.py': 'C:/neoSlice/ui/components/settings_dialog.py',
    'ui_components_tutorial_overlay.py': 'C:/neoSlice/ui/components/tutorial_overlay.py',
    'ui_components_viewer_3d.py': 'C:/neoSlice/ui/components/viewer_3d.py',
    'ui_main_window.py': 'C:/neoSlice/ui/main_window.py',
    'ui_styles_theme.py': 'C:/neoSlice/ui/styles/theme.py',
    'version.py': 'C:/neoSlice/version.py',
}

identical = []
different = []

for recovered_name, repo_path in sorted(file_map.items()):
    recovered_path = recovered_dir + recovered_name
    relative = repo_path.replace('C:/neoSlice/', '')

    try:
        with open(recovered_path, 'r', encoding='utf-8') as f:
            recovered_content = f.read()
        with open(repo_path, 'r', encoding='utf-8') as f:
            current_content = f.read()

        if recovered_content.strip() == current_content.strip():
            identical.append(relative)
        else:
            rec_lines = recovered_content.splitlines()
            cur_lines = current_content.splitlines()
            diff = list(difflib.unified_diff(cur_lines, rec_lines,
                                              fromfile=f'current/{relative}',
                                              tofile=f'recovered/{relative}',
                                              lineterm='', n=3))
            added = [l for l in diff if l.startswith('+') and not l.startswith('+++')]
            removed = [l for l in diff if l.startswith('-') and not l.startswith('---')]
            different.append((relative, len(added), len(removed), diff))
    except FileNotFoundError as e:
        print(f"FILE NOT FOUND: {e}")

print("=" * 70)
print("IDENTICAL (current = recovered from transcript)")
print("=" * 70)
for f in identical:
    print(f"  OK  {f}")

print()
print("=" * 70)
print("DIFFERENT (recovered has changes not in current)")
print("=" * 70)
for relative, n_added, n_removed, diff in different:
    print(f"\n  DIFF  {relative}")
    print(f"         +{n_added} lines in recovered / -{n_removed} lines in current")
    # Show first 50 diff lines
    for line in diff[:60]:
        print(f"    {line}")
    if len(diff) > 60:
        print(f"    ... ({len(diff)-60} more lines in diff)")
