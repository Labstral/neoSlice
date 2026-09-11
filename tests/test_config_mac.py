# -*- coding: utf-8 -*-
"""Analyse de configuration sur Mac Apple Silicon.

Retour d'un utilisateur Mac Studio M2 Ultra (24 cœurs, 64 Go, GPU 60 cœurs) :
neoSlice affichait « GPU non détecté » et conseillait d'acheter « un GPU NVIDIA
≥ 6 Go » — impossible sur un Mac, et absurde puisque cette machine est
justement excellente pour les modèles locaux (Ollama les accélère via Metal en
mémoire unifiée). La détection ne couvrait que Windows.
"""
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _verdicts(app, info, plateforme="darwin"):
    """Texte brut des verdicts affichés pour une machine donnée."""
    from PySide6.QtWidgets import QLabel
    import ui.components.settings_dialog as S
    from ui.components.settings_dialog import SettingsDialog

    d = SettingsDialog.__new__(SettingsDialog)

    class _Btn:
        def setEnabled(self, v): pass
        def setText(self, t): pass

    d._perf_test_btn = _Btn()
    d._perf_result_lbl = QLabel()
    ancien = S.sys.platform
    try:
        S.sys.platform = plateforme
        d._on_bench_result(info)
    finally:
        S.sys.platform = ancien
    html = d._perf_result_lbl.text().replace("<br/>", "\n")
    return re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ")


# Machine exacte du retour utilisateur
MAC_STUDIO = {"tier": "full", "ram_gb": 64.0, "avail_gb": 15.0, "cores": 24,
              "gpu_name": "Apple M2 Ultra", "vram_gb": 0.0, "gpu_dedie": True,
              "gpu_accel": "metal", "disk_free_gb": 293.0}


def test_detection_apple_silicon(monkeypatch):
    """Sur Apple Silicon, le GPU est nommé et l'accélération Metal signalée."""
    import ui.components.settings_dialog as S

    class _R:
        returncode = 0
        stdout = "Apple M2 Ultra\n"

    monkeypatch.setattr(S.sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _R())
    nom, vram, dedie, accel = S._BenchmarkWorker._detect_gpu()
    assert nom == "Apple M2 Ultra"
    assert accel == "metal"
    assert dedie is True
    assert vram == 0.0            # mémoire unifiée : pas de VRAM séparée


def test_mac_intel_pas_de_metal(monkeypatch):
    import ui.components.settings_dialog as S
    monkeypatch.setattr(S.sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    _nom, _vram, _dedie, accel = S._BenchmarkWorker._detect_gpu()
    assert accel == ""


def test_mac_studio_verdict_optimal(app):
    """Les deux modèles locaux doivent être annoncés RAPIDES, pas lents."""
    txt = _verdicts(app, MAC_STUDIO)
    assert "Apple M2 Ultra" in txt
    assert "GPU non détecté" not in txt
    assert "NVIDIA" not in txt, "conseiller une carte NVIDIA à un Mac n'a aucun sens"
    assert txt.count("Optimal") >= 2          # Oen ET neoGen
    assert "réponses lentes" not in txt


def test_apple_silicon_modeste(app):
    """16 Go : Oen passe (modèle ~5 Go), neoGen (~9 Go) reste juste — mais on ne
    parle toujours pas de NVIDIA."""
    txt = _verdicts(app, {**MAC_STUDIO, "ram_gb": 16.0, "gpu_name": "Apple M2"})
    assert "Optimal" in txt                   # Oen accéléré
    assert "NVIDIA" not in txt


def test_windows_sans_gpu_inchange(app):
    """Non-régression : sur PC sans GPU, le conseil NVIDIA reste pertinent."""
    txt = _verdicts(app, {**MAC_STUDIO, "gpu_name": "", "gpu_accel": "",
                          "gpu_dedie": False, "ram_gb": 32.0}, plateforme="win32")
    assert "NVIDIA" in txt
    assert "réponses lentes" in txt


def test_windows_nvidia_inchange(app):
    """Non-régression : une carte NVIDIA garde son verdict à la VRAM."""
    txt = _verdicts(app, {**MAC_STUDIO, "gpu_name": "NVIDIA RTX 4070",
                          "vram_gb": 12.0, "gpu_accel": "cuda"}, plateforme="win32")
    assert "12" in txt and "Optimal" in txt


def test_i18n_cles_metal():
    from core.i18n import _FR, _EN
    for cle in ("settings.cfg_oen_metal", "settings.cfg_neogen_metal",
                "settings.cfg_oen_cpu_mac"):
        assert cle in _FR and cle in _EN, cle
