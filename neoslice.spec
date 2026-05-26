# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

pyside6_datas,   pyside6_bins,   pyside6_hidden   = collect_all('PySide6')
pyvista_datas,   pyvista_bins,   pyvista_hidden    = collect_all('pyvista')
pyvistaqt_datas, pyvistaqt_bins, pyvistaqt_hidden  = collect_all('pyvistaqt')
vtkmod_datas,    vtkmod_bins,    vtkmod_hidden     = collect_all('vtkmodules')
mpl_datas,       mpl_bins,       mpl_hidden        = collect_all('matplotlib')

# Dossiers de données du projet
project_datas = [
    ('ui/styles', 'ui/styles'),
    ('assets', 'assets'),
    ('core/parameters/profiles', 'core/parameters/profiles'),
]
if Path('data').exists():
    project_datas.append(('data', 'data'))

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[
        *pyside6_bins,
        *pyvista_bins,
        *pyvistaqt_bins,
        *vtkmod_bins,
        *mpl_bins,
    ],
    datas=[
        *project_datas,
        *pyside6_datas,
        *pyvista_datas,
        *pyvistaqt_datas,
        *vtkmod_datas,
        *mpl_datas,
    ],
    hiddenimports=[
        *pyside6_hidden,
        *pyvista_hidden,
        *pyvistaqt_hidden,
        *vtkmod_hidden,
        *mpl_hidden,
        'trimesh',
        'trimesh.creation',
        'trimesh.repair',
        'trimesh.smoothing',
        'trimesh.transformations',
        'scipy',
        'scipy.spatial',
        'scipy.spatial.qhull',
        'scipy.sparse',
        'scipy.sparse.csgraph',
        'scipy.ndimage',
        'scipy.ndimage._nd_image',
        'scipy.ndimage._ni_support',
        'trimesh.voxel',
        'trimesh.voxel.creation',
        'trimesh.voxel.ops',
        'trimesh.proximity',
        'rtree',
        'loguru',
        'yaml',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/rthook_pyvistaqt.py'],
    excludes=[
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='neoSlice',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/neoSlice.ico',
    onefile=True,
)

# ── Post-build : déploiement automatique de l'EXE ───────────────────────────
# Copie l'EXE vers tous les emplacements connus (bureau physique + raccourci OneDrive)
# et met à jour le raccourci .lnk sur le bureau OneDrive.
import shutil, subprocess

_DIST_EXE = Path(r"C:\neoSlice_dist\neoSlice.exe")
_DEPLOY_TARGETS = [
    Path(r"C:\Users\manup\Desktop\neoSlice.exe"),
]

for _dst in _DEPLOY_TARGETS:
    try:
        _dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_DIST_EXE, _dst)
        print(f"[post-build] Copie OK : {_dst}")
    except Exception as _e:
        print(f"[post-build] ERREUR copie vers {_dst} : {_e}")

# Mettre à jour le raccourci .lnk sur le bureau OneDrive
_LNK = Path(r"C:\Users\manup\OneDrive\Bureau\neoSlice.lnk")
_PS = f"""
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut('{_LNK}')
$s.TargetPath       = 'C:\\neoSlice_dist\\neoSlice.exe'
$s.WorkingDirectory = 'C:\\neoSlice_dist'
$s.IconLocation     = 'C:\\neoSlice_dist\\neoSlice.exe,0'
$s.Save()
Write-Host '[post-build] Raccourci mis à jour : {_LNK}'
"""
try:
    subprocess.run(["powershell", "-Command", _PS], check=True, capture_output=True)
except Exception as _e:
    print(f"[post-build] ERREUR raccourci : {_e}")

# ── Compilation Inno Setup (si installé) ────────────────────────────────────
import os

_ISCC_CANDIDATES = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
]
_ISS = Path(SPEC).parent / "installer" / "neoSlice_setup.iss"
_ISCC = next((p for p in _ISCC_CANDIDATES if os.path.exists(p)), None)

if _ISCC and _ISS.exists():
    out_dir = Path(r"C:\neoSlice_dist\installer")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([_ISCC, str(_ISS)], capture_output=True, text=True)
    if result.returncode == 0:
        print("[post-build] Installateur cree : C:\\neoSlice_dist\\installer\\neoSlice_Setup_v0.1.0-beta.exe")
    else:
        print(f"[post-build] ERREUR Inno Setup : {result.stderr[-300:]}")
else:
    print("[post-build] Inno Setup absent - installateur non cree (voir installer/neoSlice_setup.iss)")

# Pour recompiler : python -m PyInstaller --clean -y --distpath "C:/neoSlice_dist" neoslice.spec
