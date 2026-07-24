# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files
import sys as _sys
_sys.path.insert(0, str(Path('.').resolve()))
from version import __version__ as _APP_VERSION

# ── Garde-fou version Python (CRITIQUE — même règle que neoslice.spec) ────
# La v0.1.6 Windows a été cassée par un build mélangeant Python 3.12/3.14
# (interpréteur ≠ modules natifs VTK → plus de viewer 3D). Cible officielle
# du projet = Python 3.12, sur TOUTES les plateformes. On refuse de builder
# avec un autre interpréteur (Codemagic doit épingler 3.12).
_TARGET = (3, 12)
if _sys.version_info[:2] != _TARGET:
    raise SystemExit(
        f"[neoslice_mac.spec] Build refusé : lancé avec Python "
        f"{_sys.version_info.major}.{_sys.version_info.minor}, cible = "
        f"{_TARGET[0]}.{_TARGET[1]}. Utilise un environnement Python 3.12 "
        f"puis relance `python -m PyInstaller --clean -y neoslice_mac.spec`.")

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
    'vtkViewsInfovis',
    'vtkRenderingContextOpenGL2',
    'vtkRenderingImage', 'vtkRenderingParallel',
    'vtkRenderingSceneGraph',
    'vtkFiltersAMR', 'vtkFiltersFlowPaths', 'vtkFiltersParallelImaging',
    'vtkFiltersParallelStatistics', 'vtkFiltersTemporal',
    'vtkFiltersTopology', 'vtkFiltersParallel',
    'vtkInfovisLayout', 'vtkInfovisCore',
    # NE PAS exclure vtkChartsCore ni vtkRenderingVolumeOpenGL2 : pyvista les
    # importe au chargement, les exclure casse le viewer ("installez pyvistaqt").
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
    for skip in ('/examples/', '/datasets/', '/tests/', '/testing/',
                 '/data/models/', '/_dataset_cache/'):
        if skip in p:
            return False
    return True

def _keep_shapely(path: str) -> bool:
    """Garde uniquement les fichiers du package shapely lui-même.
    Exclut les libs système Homebrew (GEOS, PROJ, GDAL, etc.)
    qui peuvent ajouter plusieurs Go sur macOS."""
    p = path.replace('\\', '/')
    # Garder uniquement ce qui est dans le package shapely pip
    if '/shapely/' in p or '/shapely-' in p:
        return True
    # Rejeter tout ce qui vient de Homebrew ou des libs système
    homebrew_paths = ('/opt/homebrew/', '/usr/local/lib/', '/usr/lib/',
                      '/System/', 'libgeos', 'libproj', 'libgdal',
                      'libsqlite', 'libcurl', 'libssl', 'libcrypto',
                      'libpq', 'libhdf', 'libnetcdf', 'libexpat',
                      'libxml', 'libz.', 'liblzma', 'libbz2',
                      'libpng', 'libtiff', 'libjpeg', 'libopenjp',
                      'libfreetype', 'libfontconfig', 'libharfbuzz')
    if any(s in p for s in homebrew_paths):
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

shapely_all_d, shapely_all_b, shapely_all_h = collect_all('shapely')
shapely_datas   = [x for x in shapely_all_d if _keep_shapely(str(x[0]))]
shapely_bins    = [x for x in shapely_all_b if _keep_shapely(str(x[0]))]
shapely_hidden  = shapely_all_h

vtkmod_datas_all, vtkmod_bins_all, vtkmod_hidden_all = collect_all('vtkmodules')
vtkmod_datas   = [x for x in vtkmod_datas_all  if _keep_vtk(str(x[0]))]
vtkmod_bins    = [x for x in vtkmod_bins_all   if _keep_vtk(str(x[0]))]
vtkmod_hidden  = [x for x in vtkmod_hidden_all if _keep_vtk(x)]

# certifi : cacert.pem pour HTTPS fiable (activation Pro / updater / modèle) sur macOS gelé
certifi_datas = collect_data_files('certifi')
# onnxruntime : binaires natifs du diagnostic IA
onnx_datas, onnx_bins, onnx_hidden = collect_all('onnxruntime')

project_datas = [
    ('ui/styles', 'ui/styles'),
    ('assets', 'assets'),
    ('core/parameters/profiles', 'core/parameters/profiles'),
]
# data/ SAUF data/kb : wikis + index RAG (~5 Go) inutiles à l'app distribuée
# (l'installateur d'Oen télécharge l'index dans ~/.neoslice). Aligné sur
# neoslice.spec — ne pas ré-embarquer.
if Path('data').exists():
    for _item in sorted(Path('data').iterdir()):
        if _item.name == 'kb':
            continue
        dest = f'data/{_item.name}' if _item.is_dir() else 'data'
        project_datas.append((str(_item), dest))

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[
        *pyside6_bins,
        *pyvista_bins,
        *pyvistaqt_bins,
        *shapely_bins,
        *vtkmod_bins,
        *onnx_bins,
    ],
    datas=[
        *project_datas,
        *pyside6_datas,
        *pyvista_datas,
        *pyvistaqt_datas,
        *shapely_datas,
        *vtkmod_datas,
        *certifi_datas,
        *onnx_datas,
    ],
    hiddenimports=[
        *pyside6_hidden,
        *pyvista_hidden,
        *pyvistaqt_hidden,
        *shapely_hidden,
        *vtkmod_hidden,
        *onnx_hidden,
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
        'networkx', 'lxml', 'lxml.etree', 'certifi', 'onnxruntime', 'version',
        # neoGen (génération de pièces par texte) — imports paresseux forcés
        'core.neogen', 'core.neogen.pilote', 'core.neogen.geo_utils',
        'core.neogen.texte', 'core.neogen.goodies', 'core.neogen.logo',
        'core.neogen.objets', 'core.neogen.formes', 'core.neogen.formes2',
        'core.neogen.catalogue', 'core.neogen.libre', 'core.neogen.installation',
        'core.neogen.qrcode_3d', 'segno',
        # CRITIQUE : le catalogue charge ces modules via importlib.import_module
        # (chaîne dynamique) → PyInstaller ne les voit PAS. Sans eux, générer un
        # objet resto/mariage/boutique ou une lithophanie plante dans le build.
        'core.neogen.formes3', 'core.neogen.pro_resto', 'core.neogen.pro_mariage',
        'core.neogen.pro_boutique', 'core.neogen.relief_photo',
        'core.neogen.bicolore', 'core.neogen.carte_visite',
        # objets_module : objets neoGen téléchargeables (MAJ sans rebuild),
        # importé DANS des fonctions (catalogue/maj) → à forcer.
        'core.neogen.objets_module',
        # flashprint_builder : 9e slicer, importé dans une fonction de main_window.
        'core.export.flashprint_builder',
        # RAM macOS/Linux (analyse de configuration dans les réglages)
        'psutil',
        'mapbox_earcut', 'manifold3d', 'svgelements', 'cv2',
        'matplotlib.textpath', 'matplotlib.font_manager',
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
        'CFBundleShortVersionString': _APP_VERSION,
        'CFBundleVersion': _APP_VERSION,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)
