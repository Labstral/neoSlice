# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# ─────────────────────────────────────────────────────────────────
#  Filtres d'exclusion — réduction maximale de la taille du bundle
# ─────────────────────────────────────────────────────────────────

# Modules PySide6 non utilisés par neoSlice
_PYSIDE6_UNUSED = {
    'Qt3D', 'QtCharts', 'QtDataVisualization', 'QtMultimedia',
    'QtQml', 'QtQuick', 'QtWebEngine', 'QtWebChannel', 'QtWebSockets',
    'QtBluetooth', 'QtLocation', 'QtPositioning', 'QtSensors',
    'QtSerialPort', 'QtSpatialAudio', 'QtTextToSpeech', 'QtVirtualKeyboard',
    'QtPdf', 'QtRemoteObjects', 'QtStateMachine', 'QtTest', 'QtSql',
    'QtUiTools', 'QtDesigner', 'QtHelp', 'QtNetwork', 'QtConcurrent',
    'QtNfc', 'QtSCXML', 'QtLottie', 'QtQuickTimeline', 'QtShaderTools',
    'QtAxContainer', 'QtDBus', 'PySide6_Addons',
}

# Modules VTK non utilisés (rendering alternatifs, I/O spécialisés, tests)
_VTK_UNUSED = {
    'vtkRenderingOpenVR', 'vtkRenderingAnari', 'vtkRenderingWebGPU',
    'vtkRenderingFreeTypeFontConfig', 'vtkRenderingLOD',
    'vtkIOMovie', 'vtkIOOggTheora', 'vtkIOFFMPEG',
    'vtkIOXdmf2', 'vtkIOXdmf3', 'vtkIONetCDF', 'vtkIOEnSight',
    'vtkIOAMR', 'vtkIOFLUENT', 'vtkIOVeraOut', 'vtkIOTecplotTable',
    'vtkIOSegY', 'vtkIOParallelXML', 'vtkIOParallelLSDyna',
    'vtkIOGeometry',  # remplacé par vtkIOLegacy + vtkIOPLY pour STL
    'vtkDICOM', 'vtkTestingCore', 'vtkTestingRendering',
    'vtkWebCore', 'vtkWebGLExporter', 'web',
    'vtkDomainsChemistry', 'vtkDomainsChemistryOpenGL2',
    'vtkGeovisCore', 'vtkGeovisGDAL',
    'vtkViewsContext2D', 'vtkViewsInfovis',
    'vtkRenderingContext2D', 'vtkRenderingContextOpenGL2',
    'vtkRenderingImage', 'vtkRenderingParallel',
    'vtkRenderingSceneGraph', 'vtkRenderingVolumeOpenGL2',
    'vtkFiltersAMR', 'vtkFiltersFlowPaths', 'vtkFiltersParallelImaging',
    'vtkFiltersParallelStatistics', 'vtkFiltersTemporal',
    'vtkFiltersTopology', 'vtkFiltersParallel',
    'vtkInfovisLayout', 'vtkInfovisCore',
    'vtkChartsCore',
}

def _keep_pyside6(path: str) -> bool:
    p = path.replace('\\', '/')
    if any(mod in p for mod in _PYSIDE6_UNUSED):
        return False
    # Supprimer toutes les traductions Qt sauf fr/en
    if '/translations/' in p and p.endswith('.qm'):
        name = Path(p).stem
        if not any(name.endswith(lang) for lang in ('_fr', '_en', '_en_US', '_fr_FR')):
            return False
    return True

def _keep_vtk(path: str) -> bool:
    p = path.replace('\\', '/')
    return not any(mod in p for mod in _VTK_UNUSED)

def _keep_pyvista(path: str) -> bool:
    p = path.replace('\\', '/')
    # Supprimer exemples, datasets de démo et données de tests
    for skip in ('/examples/', '/datasets/', '/tests/', '/testing/',
                 '/data/models/', '/_dataset_cache/'):
        if skip in p:
            return False
    return True

# ─────────────────────────────────────────────────────────────────
#  Collecte filtrée
# ─────────────────────────────────────────────────────────────────

pyside6_datas_all, pyside6_bins_all, pyside6_hidden_all = collect_all('PySide6')
pyside6_datas   = [x for x in pyside6_datas_all  if _keep_pyside6(str(x[0]))]
pyside6_bins    = [x for x in pyside6_bins_all   if _keep_pyside6(str(x[0]))]
pyside6_hidden  = [x for x in pyside6_hidden_all if _keep_pyside6(x)]

pyvista_datas_all, pyvista_bins_all, pyvista_hidden_all = collect_all('pyvista')
pyvista_datas   = [x for x in pyvista_datas_all  if _keep_pyvista(str(x[0]))]
pyvista_bins    = [x for x in pyvista_bins_all   if _keep_pyvista(str(x[0]))]
pyvista_hidden  = pyvista_hidden_all

pyvistaqt_datas, pyvistaqt_bins, pyvistaqt_hidden = collect_all('pyvistaqt')

vtkmod_datas_all, vtkmod_bins_all, vtkmod_hidden_all = collect_all('vtkmodules')
vtkmod_datas   = [x for x in vtkmod_datas_all  if _keep_vtk(str(x[0]))]
vtkmod_bins    = [x for x in vtkmod_bins_all   if _keep_vtk(str(x[0]))]
vtkmod_hidden  = [x for x in vtkmod_hidden_all if _keep_vtk(x)]

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
        'shapely', 'shapely.geometry', 'shapely.ops', 'shapely.validation',
        'reportlab', 'reportlab.pdfgen', 'reportlab.lib', 'reportlab.lib.pagesizes',
        'reportlab.platypus', 'reportlab.lib.styles', 'reportlab.lib.units',
        'trimesh', 'trimesh.creation', 'trimesh.repair',
        'trimesh.smoothing', 'trimesh.transformations',
        'trimesh.voxel', 'trimesh.voxel.creation',
        'trimesh.voxel.ops', 'trimesh.proximity',
        'scipy', 'scipy.spatial', 'scipy.spatial.qhull',
        'scipy.sparse', 'scipy.sparse.csgraph', 'scipy.ndimage',
        'rtree', 'loguru', 'yaml', 'numpy', 'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/rthook_pyvistaqt.py'],
    excludes=[
        'IPython', 'jupyter', 'notebook', 'pytest', 'setuptools',
        'tkinter', 'wx', 'gi',
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
        'PySide6.QtLottie', 'PySide6.QtQuickTimeline', 'PySide6_Addons',
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
    strip=True,
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
