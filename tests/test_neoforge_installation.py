# -*- coding: utf-8 -*-
"""neoForge : installation depuis un dépôt (ici local, file://) avec
signature, empreintes, tout-ou-rien, mise à jour sans retélécharger le noyau,
désinstallation. Ne touche JAMAIS au vrai ~/.neoslice (dossier temporaire)."""
import hashlib
import json
import os
import zipfile

import pytest

from core.neoforge import installation as I
from core.neoforge.signature import cle_publique, signer

SK = bytes(range(32))
PK = cle_publique(SK)


def _zip(chemin, contenu: dict):
    with zipfile.ZipFile(chemin, "w") as z:
        for nom, data in contenu.items():
            z.writestr(nom, data)
    return chemin


def _depot(tmp, version="1.0.0", noyau="ocp-1", neoslice_min="0.1", cle=SK, abimer=None):
    d = tmp / f"depot_{version}_{noyau}"
    d.mkdir()
    code = _zip(d / f"neoforge_code_{version}.zip",
                {"neoforge/__init__.py": f'VERSION = "{version}"\n'})
    plat = I.plateforme()
    nz = _zip(d / f"neoforge_noyau_{plat}.zip", {"OCP/__init__.py": f"# {noyau}\n"})

    def entree(p):
        return {"fichier": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "taille": p.stat().st_size}
    m = {"version": version, "neoslice_min": neoslice_min,
         "code": entree(code), "noyaux": {plat: {"version": noyau, **entree(nz)}}}
    brut = json.dumps(m).encode()
    (d / I.MANIFESTE).write_bytes(brut)
    (d / I.SIGNATURE).write_text(signer(cle, brut).hex())
    if abimer:
        abimer(d)
    return d.as_uri()


@pytest.fixture(autouse=True)
def _plateforme_connue(monkeypatch):
    if I.plateforme() is None:
        monkeypatch.setattr(I, "plateforme", lambda: "win-amd64")


def test_installation_puis_desinstallation(tmp_path):
    cible = tmp_path / "neoforge"
    info = I.installer(dossier=cible, base_url=_depot(tmp_path), cle=PK)
    assert info["version"] == "1.0.0" and I.est_installe(cible)
    assert (cible / "code" / "neoforge" / "__init__.py").read_text().strip() == 'VERSION = "1.0.0"'
    projets = cible.parent / "Documents_neoForge"          # rangés ailleurs
    projets.mkdir()
    I.desinstaller(cible)
    assert not I.est_installe(cible) and not (cible / "noyau").exists()
    assert projets.exists()


def test_signature_d_une_autre_cle_refusee(tmp_path):
    cible = tmp_path / "neoforge"
    with pytest.raises(I.ErreurNeoForge) as e:
        I.installer(dossier=cible, base_url=_depot(tmp_path, cle=bytes(32)), cle=PK)
    assert e.value.code == I.ERR_SIGNATURE and not I.est_installe(cible)


def test_fichier_modifie_refuse_et_ancienne_version_intacte(tmp_path):
    cible = tmp_path / "neoforge"
    I.installer(dossier=cible, base_url=_depot(tmp_path), cle=PK)

    def abimer(d):
        # un octet inversé AU MILIEU (le dernier octet d'un zip vaut déjà 0)
        z = next(d.glob("neoforge_code_*.zip"))
        data = bytearray(z.read_bytes())
        data[len(data) // 2] ^= 0xFF
        z.write_bytes(bytes(data))
    with pytest.raises(I.ErreurNeoForge) as e:
        I.installer(dossier=cible, base_url=_depot(tmp_path, "1.1.0", abimer=abimer), cle=PK)
    assert e.value.code == I.ERR_EMPREINTE
    assert I.etat(cible)["version"] == "1.0.0"
    assert 'VERSION = "1.0.0"' in (cible / "code" / "neoforge" / "__init__.py").read_text()


def test_neoslice_trop_ancien_refuse(tmp_path):
    with pytest.raises(I.ErreurNeoForge) as e:
        I.installer(dossier=tmp_path / "nf", base_url=_depot(tmp_path, neoslice_min="99.0"), cle=PK)
    assert e.value.code == I.ERR_VERSION


def test_mise_a_jour_du_code_sans_retelecharger_le_noyau(tmp_path, monkeypatch):
    cible = tmp_path / "neoforge"
    I.installer(dossier=cible, base_url=_depot(tmp_path), cle=PK)
    depot2 = _depot(tmp_path, "1.1.0")
    assert I.verifier_maj(cible, depot2, PK)["version"] == "1.1.0"
    vus = []
    vrai = I._telecharger
    monkeypatch.setattr(I, "_telecharger", lambda url, *a, **k: (vus.append(url), vrai(url, *a, **k)))
    info = I.installer(dossier=cible, base_url=depot2, cle=PK)
    assert info == {"version": "1.1.0", "noyau_version": "ocp-1", "plateforme": I.plateforme()}
    assert len(vus) == 1 and "code" in vus[0]                 # le noyau n'est pas repris
    assert I.verifier_maj(cible, depot2, PK) is None
    # nouveau noyau : cette fois il est retéléchargé
    assert I.verifier_maj(cible, _depot(tmp_path, "1.1.0", "ocp-2"), PK) is not None


def test_hors_ligne_pas_d_exception(tmp_path):
    cible = tmp_path / "neoforge"
    I.installer(dossier=cible, base_url=_depot(tmp_path), cle=PK)
    assert I.verifier_maj(cible, (tmp_path / "absent").as_uri(), PK) is None


def test_archive_qui_sort_du_dossier_refusee(tmp_path):
    def abimer(d):
        z = next(d.glob("neoforge_code_*.zip"))
        _zip(z, {"../../evasion.py": "x"})
        m = json.loads((d / I.MANIFESTE).read_bytes())
        m["code"].update(sha256=hashlib.sha256(z.read_bytes()).hexdigest(), taille=z.stat().st_size)
        brut = json.dumps(m).encode()
        (d / I.MANIFESTE).write_bytes(brut)
        (d / I.SIGNATURE).write_text(signer(SK, brut).hex())
    with pytest.raises(I.ErreurNeoForge):
        I.installer(dossier=tmp_path / "nf", base_url=_depot(tmp_path, abimer=abimer), cle=PK)
    assert not (tmp_path / "evasion.py").exists() and not os.path.exists(tmp_path.parent / "evasion.py")
