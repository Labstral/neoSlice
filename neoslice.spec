# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files
import subprocess as _sp

# ── Garde-fou version Python (CRITIQUE) ───────────────────────────
# La v0.1.6 a été empaquetée en mélangeant deux venvs (.venv=3.14 et
# .venv312=3.12) : l'interpréteur embarqué et les modules natifs VTK
# n'étaient pas de la même version -> au démarrage chez l'utilisateur :
#   "Module use of python312.dll conflicts with this version of Python"
#   -> import de pyvistaqt échoue -> plus de viewer 3D (placeholder).
# Cible officielle du projet = Python 3.12. On refuse de builder avec
# un autre Python, et on vérifie que les .pyd VTK visibles sont bien
# compilés pour cette version (pas de cp3xx étranger qui traînerait).
_TARGET = (3, 12)
if sys.version_info[:2] != _TARGET:
    raise SystemExit(
        f"[neoslice.spec] Build refusé : lancé avec Python "
        f"{sys.version_info.major}.{sys.version_info.minor}, cible = "
        f"{_TARGET[0]}.{_TARGET[1]}. Active .venv312 puis relance "
        f"`python -m PyInstaller --clean -y neoslice.spec`.")
try:
    import vtkmodules, glob as _glob
    _tag = f"cp{_TARGET[0]}{_TARGET[1]}"
    _pyds = _glob.glob(str(Path(vtkmodules.__file__).parent / "*.pyd"))
    _bad = [p for p in _pyds if "cp3" in p and _tag not in p]
    if _bad:
        raise SystemExit(
            f"[neoslice.spec] Build refusé : modules VTK d'une AUTRE "
            f"version de Python détectés (attendu {_tag}) : "
            f"{Path(_bad[0]).name}. Environnement mélangé — réinstalle "
            f"pyvista/vtk/pyvistaqt dans .venv312 uniquement.")
except ImportError:
    pass

# ── Pré-build : fermer neoSlice.exe s'il tourne (sinon Windows bloque l'écrasement)
_sp.run(["taskkill", "/F", "/IM", "neoSlice.exe"], capture_output=True)

# ─────────────────────────────────────────────────────────────────
#  Filtres d'exclusion — réduction de la taille de l'installateur.
#  Mêmes filtres que neoslice_mac.spec (validés en production sur macOS) :
#  l'app tourne déjà sans ces modules sur Mac, le code Python étant
#  identique, ils sont donc inutiles sur Windows aussi.
# ─────────────────────────────────────────────────────────────────

# Modules PySide6/Qt non utilisés par neoSlice
_PYSIDE6_UNUSED = {
    'Qt3D', 'QtCharts', 'QtDataVisualization', 'QtMultimedia',
    'QtQml', 'QtQuick', 'QtWebEngine', 'QtWebChannel', 'QtWebSockets',
    'QtBluetooth', 'QtLocation', 'QtPositioning', 'QtSensors',
    'QtSerialPort', 'QtSpatialAudio', 'QtTextToSpeech', 'QtVirtualKeyboard',
    'QtPdf', 'QtRemoteObjects', 'QtStateMachine', 'QtTest', 'QtSql',
    'QtUiTools', 'QtDesigner', 'QtHelp', 'QtNetwork', 'QtConcurrent',
    'QtNfc', 'QtSCXML', 'QtLottie', 'QtQuickTimeline', 'QtShaderTools',
    'PySide6_Addons',
}

# Modules VTK non utilisés (rendus alternatifs, I/O spécialisés, tests)
_VTK_UNUSED = {
    'vtkRenderingOpenVR', 'vtkRenderingAnari', 'vtkRenderingWebGPU',
    'vtkRenderingFreeTypeFontConfig', 'vtkRenderingLOD',
    'vtkIOMovie', 'vtkIOOggTheora', 'vtkIOFFMPEG',
    'vtkIOXdmf2', 'vtkIOXdmf3', 'vtkIONetCDF', 'vtkIOEnSight',
    'vtkIOAMR', 'vtkIOFLUENT', 'vtkIOVeraOut', 'vtkIOTecplotTable',
    'vtkIOSegY', 'vtkIOParallelXML', 'vtkIOParallelLSDyna',
    'vtkDICOM', 'vtkTestingCore', 'vtkTestingRendering',
    'vtkWebCore', 'vtkWebGLExporter',
    'vtkDomainsChemistry', 'vtkDomainsChemistryOpenGL2',
    'vtkGeovisCore', 'vtkGeovisGDAL',
    'vtkViewsInfovis',
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
    p = str(path).replace('\\', '/')
    if any(mod in p for mod in _PYSIDE6_UNUSED):
        return False
    # Supprimer toutes les traductions Qt sauf fr/en
    if '/translations/' in p and p.endswith('.qm'):
        name = Path(p).stem
        if not any(name.endswith(lang) for lang in ('_fr', '_en', '_en_US', '_fr_FR')):
            return False
    return True

def _keep_vtk(path: str) -> bool:
    p = str(path).replace('\\', '/')
    return not any(mod in p for mod in _VTK_UNUSED)

def _keep_pyvista(path: str) -> bool:
    p = str(path).replace('\\', '/')
    for skip in ('/examples/', '/datasets/', '/tests/', '/testing/',
                 '/data/models/', '/_dataset_cache/'):
        if skip in p:
            return False
    return True

_p6_d, _p6_b, _p6_h = collect_all('PySide6')
pyside6_datas  = [x for x in _p6_d if _keep_pyside6(x[0])]
pyside6_bins   = [x for x in _p6_b if _keep_pyside6(x[0])]
pyside6_hidden = [x for x in _p6_h if _keep_pyside6(x)]

_pv_d, _pv_b, _pv_h = collect_all('pyvista')
pyvista_datas  = [x for x in _pv_d if _keep_pyvista(x[0])]
pyvista_bins   = [x for x in _pv_b if _keep_pyvista(x[0])]
pyvista_hidden = _pv_h

pyvistaqt_datas, pyvistaqt_bins, pyvistaqt_hidden  = collect_all('pyvistaqt')

_vtk_d, _vtk_b, _vtk_h = collect_all('vtkmodules')
vtkmod_datas  = [x for x in _vtk_d if _keep_vtk(x[0])]
vtkmod_bins   = [x for x in _vtk_b if _keep_vtk(x[0])]
vtkmod_hidden = [x for x in _vtk_h if _keep_vtk(x)]

mpl_datas,       mpl_bins,       mpl_hidden        = collect_all('matplotlib')
shapely_datas,   shapely_bins,   shapely_hidden    = collect_all('shapely')

# certifi : embarque cacert.pem (HTTPS fiable en app gelée, surtout macOS)
certifi_datas = collect_data_files('certifi')

# Dossiers de données du projet
project_datas = [
    ('ui/styles', 'ui/styles'),
    ('assets', 'assets'),
    ('core/parameters/profiles', 'core/parameters/profiles'),
]
# data/ SAUF data/kb : les wikis moissonnés + l'index RAG pèsent ~5 Go et ne
# servent PAS à l'app distribuée (l'installateur d'Oen télécharge l'index dans
# ~/.neoslice/assistant/kb ; les .md bruts ne servent qu'à tools/kb_index.py en
# dev). Les embarquer ferait exploser le build (et le retrait --clean plantait
# déjà sur des fichiers kb verrouillés).
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
        *vtkmod_bins,
        *mpl_bins,
        *shapely_bins,
    ],
    datas=[
        *project_datas,
        *pyside6_datas,
        *pyvista_datas,
        *pyvistaqt_datas,
        *vtkmod_datas,
        *mpl_datas,
        *shapely_datas,
        *certifi_datas,
    ],
    hiddenimports=[
        *pyside6_hidden,
        *pyvista_hidden,
        *pyvistaqt_hidden,
        *vtkmod_hidden,
        *mpl_hidden,
        *shapely_hidden,
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
        'networkx',
        'lxml',
        # neoGen (génération de pièces par texte) — imports paresseux dans
        # core/neogen/* : on les force pour que l'analyse ne les rate JAMAIS
        # (cf. bug "No module named networkx" v0.1.5.4).
        'core.neogen', 'core.neogen.pilote', 'core.neogen.geo_utils',
        'core.neogen.texte', 'core.neogen.goodies', 'core.neogen.logo',
        'core.neogen.objets',
        'mapbox_earcut', 'manifold3d', 'svgelements', 'cv2',
        'matplotlib.textpath', 'matplotlib.font_manager',
        'lxml.etree',
        'shapely',
        'shapely.geometry',
        'shapely.ops',
        'shapely.validation',
        'certifi',
        'version',
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
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir : binaires/datas vont dans COLLECT, pas dans l'EXE
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
)

# ── onedir : regroupe l'EXE + tous les binaires/données dans dist/neoSlice/ ──
# Évite le dossier temporaire _MEIxxxx (plus de popup "Failed to remove temporary
# directory", démarrage plus rapide). L'installateur Inno Setup empaquette ce dossier.
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='neoSlice',
)

# ── Post-build : déploiement automatique de l'EXE ───────────────────────────
import shutil, subprocess

_DIST_EXE = Path(r"C:\neoSlice\dist\neoSlice\neoSlice.exe")

# Mettre à jour le raccourci .lnk sur le bureau (onedir : exe dans dist\neoSlice\)
_LNK = Path(r"C:\Users\manup\OneDrive\Bureau\neoSlice.lnk")
_PS = f"""
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut('{_LNK}')
$s.TargetPath       = 'C:\\neoSlice\\dist\\neoSlice\\neoSlice.exe'
$s.WorkingDirectory = 'C:\\neoSlice\\dist\\neoSlice'
$s.IconLocation     = 'C:\\neoSlice\\dist\\neoSlice\\neoSlice.exe,0'
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
    out_dir = Path(r"C:\neoSlice\dist\installer")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([_ISCC, str(_ISS)], capture_output=True, text=True)
    if result.returncode == 0:
        import re as _re
        _ver = _re.search(r'#define AppVersion\s+"([^"]+)"', _ISS.read_text()).group(1)
        print(f"[post-build] Installateur cree : C:\\neoSlice\\dist\\installer\\neoSlice_Setup_v{_ver}_Windows.exe")
    else:
        print(f"[post-build] ERREUR Inno Setup : {result.stderr[-300:]}")
else:
    print("[post-build] Inno Setup absent - installateur non cree (voir installer/neoSlice_setup.iss)")

# Pour recompiler : python -m PyInstaller --clean -y --distpath "C:/neoSlice_dist" neoslice.spec
