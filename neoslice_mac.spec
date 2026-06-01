# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

pyside6_datas,   pyside6_bins,   pyside6_hidden   = collect_all('PySide6')
pyvista_datas,   pyvista_bins,   pyvista_hidden    = collect_all('pyvista')
pyvistaqt_datas, pyvistaqt_bins, pyvistaqt_hidden  = collect_all('pyvistaqt')
vtkmod_datas,    vtkmod_bins,    vtkmod_hidden     = collect_all('vtkmodules')

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
    ],
    datas=[
        *project_datas,
        *pyside6_datas,
        *pyvista_datas,
        *pyvistaqt_datas,
        *vtkmod_datas,
    ],
    hiddenimports=[
        *pyside6_hidden,
        *pyvista_hidden,
        *pyvistaqt_hidden,
        *vtkmod_hidden,
        'trimesh',
        'trimesh.creation',
        'trimesh.repair',
        'trimesh.smoothing',
        'trimesh.transformations',
        'trimesh.voxel',
        'trimesh.voxel.creation',
        'trimesh.voxel.ops',
        'trimesh.proximity',
        'scipy',
        'scipy.spatial',
        'scipy.spatial.qhull',
        'scipy.sparse',
        'scipy.sparse.csgraph',
        'scipy.ndimage',
        'rtree',
        'loguru',
        'yaml',
        'numpy',
        'pydantic',
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
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='neoSlice',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='neoSlice',
)

app = BUNDLE(
    coll,
    name='neoSlice.app',
    bundle_identifier='com.emmanuelpercheron.neoslice',
    info_plist={
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
