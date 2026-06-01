# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# Modules PySide6 NON utilisés par neoSlice — exclus pour réduire la taille
# (WebEngine seul = ~1.5 Go, Qt3D + QML + Multimedia = ~2 Go de plus)
_PYSIDE6_UNUSED = {
    'Qt3D', 'QtCharts', 'QtDataVisualization', 'QtMultimedia',
    'QtQml', 'QtQuick', 'QtWebEngine', 'QtWebChannel', 'QtWebSockets',
    'QtBluetooth', 'QtLocation', 'QtPositioning', 'QtSensors',
    'QtSerialPort', 'QtSpatialAudio', 'QtTextToSpeech', 'QtVirtualKeyboard',
    'QtPdf', 'QtRemoteObjects', 'QtStateMachine', 'QtTest', 'QtSql',
    'QtUiTools', 'QtDesigner', 'QtHelp', 'QtNetwork', 'QtConcurrent',
    'QtNfc', 'QtSCXML', 'QtLottie', 'QtQuickTimeline', 'QtShaderTools',
    'QtAxContainer', 'QtDBus',
}

def _keep(path: str) -> bool:
    return not any(mod in path for mod in _PYSIDE6_UNUSED)

pyside6_datas_all, pyside6_bins_all, pyside6_hidden_all = collect_all('PySide6')
pyside6_datas   = [x for x in pyside6_datas_all   if _keep(str(x[0]))]
pyside6_bins    = [x for x in pyside6_bins_all    if _keep(str(x[0]))]
pyside6_hidden  = [x for x in pyside6_hidden_all  if _keep(x)]

pyvista_datas,   pyvista_bins,   pyvista_hidden    = collect_all('pyvista')
pyvistaqt_datas, pyvistaqt_bins, pyvistaqt_hidden  = collect_all('pyvistaqt')
vtkmod_datas,    vtkmod_bins,    vtkmod_hidden      = collect_all('vtkmodules')

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
        'IPython', 'jupyter', 'notebook', 'pytest', 'setuptools',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick', 'PySide6.QtQml', 'PySide6.QtQuick',
        'PySide6.QtQuickWidgets', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth', 'PySide6.QtLocation', 'PySide6.QtPositioning',
        'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSpatialAudio',
        'PySide6.QtTextToSpeech', 'PySide6.QtVirtualKeyboard',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtRemoteObjects',
        'PySide6.QtStateMachine', 'PySide6.QtTest', 'PySide6.QtSql',
        'PySide6.QtUiTools', 'PySide6.QtHelp', 'PySide6.QtNetwork',
        'PySide6.QtNfc', 'PySide6.QtSCXML', 'PySide6.QtShaderTools',
        'PySide6.QtLottie', 'PySide6.QtQuickTimeline',
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
    strip=True,   # Supprime les symboles debug des .dylib — réduit la taille de 30-50%
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    name='neoSlice',
)

app = BUNDLE(
    coll,
    name='neoSlice.app',
    icon='assets/neoSlice.icns',
    bundle_identifier='com.emmanuelpercheron.neoslice',
    info_plist={
        'CFBundleShortVersionString': '0.1.2',
        'CFBundleVersion': '0.1.2',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
