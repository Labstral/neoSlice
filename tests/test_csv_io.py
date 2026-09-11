# -*- coding: utf-8 -*-
"""Import / export CSV de l'Espace Pro (clients, devis, commandes).

Demande d'un client Pro (Nord Impression 3D) : ses prospects arrivent d'un
outil commercial (Limova) et il ressaisissait chaque client à la main. Pas
d'API (neoSlice reste local) : un échange de fichiers CSV générique.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.business import store, csv_io                     # noqa: E402


@pytest.fixture(autouse=True)
def _isole_store(tmp_path, monkeypatch):
    """Toutes les collections dans un dossier temporaire : zéro écriture réelle."""
    for attr in ("_CLIENTS", "_QUOTES", "_ORDERS", "_INVOICES", "_COMPANY", "_SPOOLS"):
        monkeypatch.setattr(store, attr, tmp_path / f"{attr.strip('_').lower()}.json")
    yield


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _ecrire(tmp_path, nom, texte, encodage="utf-8"):
    p = tmp_path / nom
    p.write_bytes(texte.encode(encodage))
    return p


# Fichier type « outil commercial » : prénom/nom séparés, colonne inutile
LIMOVA = ("ID;Prénom;Nom;Entreprise;Email professionnel;Téléphone;LinkedIn;Ville;Pays\n"
          "L-001;Paul;Martin;Garage Martin;paul@garage-martin.fr;0601020304;"
          "linkedin.com/in/pm;Lille;France\n"
          "L-002;Sophie;Durand;Carrosserie Durand;s.durand@carro.fr;;;Roubaix;FR\n"
          ";;;;;;;;\n"
          "L-003;;;;;;;;\n")


# ── Lecture ──────────────────────────────────────────────────────────────────
def test_lecture_point_virgule_utf8(tmp_path):
    ent, lignes = csv_io.lire_csv(_ecrire(tmp_path, "a.csv", LIMOVA))
    assert ent[:4] == ["ID", "Prénom", "Nom", "Entreprise"]
    assert len(lignes) == 3                    # la ligne entièrement vide saute
    assert lignes[0][3] == "Garage Martin"


def test_lecture_excel_francais_cp1252_et_virgule(tmp_path):
    """Excel français enregistre souvent en Windows-1252 : les accents doivent
    survivre ; séparateur virgule détecté."""
    p = _ecrire(tmp_path, "b.csv", "Société,Contact,Email\nCafé Élysée,Hélène,h@e.fr\n",
                encodage="cp1252")
    ent, lignes = csv_io.lire_csv(p)
    assert ent == ["Société", "Contact", "Email"]
    assert lignes == [["Café Élysée", "Hélène", "h@e.fr"]]


def test_lecture_bom_et_guillemets(tmp_path):
    p = _ecrire(tmp_path, "c.csv", '﻿Nom;Notes\n"Dupont";"ligne 1\nligne 2; avec point-virgule"\n')
    ent, lignes = csv_io.lire_csv(p)
    assert ent == ["Nom", "Notes"]             # BOM retiré
    assert "ligne 2" in lignes[0][1]           # champ multiligne entre guillemets


def test_fichier_vide(tmp_path):
    with pytest.raises(ValueError):
        csv_io.lire_csv(_ecrire(tmp_path, "vide.csv", "\n\n"))


# ── Reconnaissance des colonnes ──────────────────────────────────────────────
def test_colonnes_devinees():
    ent = ["ID", "Prénom", "Nom", "Entreprise", "Email professionnel", "Téléphone",
           "LinkedIn", "Ville", "Pays"]
    assert csv_io.deviner_colonnes(ent) == [
        "ref_externe", "prenom", "nom", "societe", "email", "tel", "", "ville", "pays"]


def test_colonnes_anglaises():
    ent = ["Company Name", "Full Name", "E-mail", "Phone number", "Zip Code", "Notes"]
    assert csv_io.deviner_colonnes(ent) == [
        "societe", "nom", "email", "tel", "cp", "notes"]


def test_un_champ_une_seule_colonne():
    assert csv_io.deviner_colonnes(["Email", "Mail"]) == ["email", ""]


# ── Préparation ──────────────────────────────────────────────────────────────
def test_preparation_fusionne_prenom_et_traduit_le_pays(tmp_path):
    ent, lignes = csv_io.lire_csv(_ecrire(tmp_path, "a.csv", LIMOVA))
    clients = csv_io.preparer_clients(lignes, csv_io.deviner_colonnes(ent))
    assert len(clients) == 2                   # « L-003 » sans contact écarté
    assert clients[0]["nom"] == "Paul Martin"
    assert clients[0]["pays"] == "France"
    assert clients[1]["pays"] == "France"      # code « FR » compris
    assert "tel" not in clients[1]             # case vide : pas de clé


def test_pays_inconnu_ignore():
    c = csv_io.preparer_clients([["Dupont", "Atlantide"]], ["nom", "pays"])
    assert "pays" not in c[0]


def test_pays_dans_une_autre_langue():
    assert csv_io._pays_connu("Switzerland") == "Suisse"
    assert csv_io._pays_connu("Schweiz") == "Suisse"
    assert csv_io._pays_connu("ch") == "Suisse"


# ── Import ───────────────────────────────────────────────────────────────────
def test_import_puis_reimport_sans_doublon(tmp_path):
    ent, lignes = csv_io.lire_csv(_ecrire(tmp_path, "a.csv", LIMOVA))
    clients = csv_io.preparer_clients(lignes, csv_io.deviner_colonnes(ent))
    r1 = csv_io.importer_clients(clients)
    assert r1 == {"crees": 2, "maj": 0, "inchanges": 0}
    assert store.list_clients()[0]["ref_externe"] in ("L-001", "L-002")
    r2 = csv_io.importer_clients(clients)      # même fichier réimporté
    assert r2 == {"crees": 0, "maj": 0, "inchanges": 2}
    assert len(store.list_clients()) == 2


def test_doublon_par_adresse_mail_insensible_a_la_casse():
    store.add_client({"nom": "Paul", "email": "Paul@Garage-Martin.fr"})
    r = csv_io.importer_clients([{"email": "paul@garage-martin.fr", "tel": "0601"}])
    assert r["crees"] == 0 and r["maj"] == 1
    c = store.list_clients()[0]
    assert c["tel"] == "0601" and c["nom"] == "Paul"


def test_une_case_vide_n_efface_rien():
    store.add_client({"nom": "Paul", "email": "p@x.fr", "tel": "0601", "ville": "Lille"})
    csv_io.importer_clients([{"email": "p@x.fr", "ville": "Roubaix"}])
    c = store.list_clients()[0]
    assert c["tel"] == "0601"                  # absent du fichier : conservé
    assert c["ville"] == "Roubaix"             # présent : mis à jour


def test_doublons_dans_le_meme_fichier_fusionnes():
    r = csv_io.importer_clients([{"email": "a@b.fr", "nom": "A"},
                                 {"email": "A@B.FR", "tel": "06"}])
    assert r["crees"] == 1 and r["maj"] == 1
    assert len(store.list_clients()) == 1


# ── Export ───────────────────────────────────────────────────────────────────
def test_export_clients_se_reimporte_tel_quel(tmp_path):
    """Aller-retour : un export neoSlice est reconnu par l'import sans remapper."""
    store.add_client({"nom": "Paul", "societe": "Garage", "email": "p@x.fr",
                      "ref_externe": "L-1", "ville": "Lille", "pays": "France"})
    dest = csv_io.export_clients_csv(tmp_path / "clients.csv")
    ent, lignes = csv_io.lire_csv(dest)
    cols = csv_io.deviner_colonnes(ent)
    assert {"ref_externe", "societe", "nom", "email", "ville", "pays"} <= set(cols)
    r = csv_io.importer_clients(csv_io.preparer_clients(lignes, cols))
    assert r == {"crees": 0, "maj": 0, "inchanges": 1}


def test_export_devis_et_commandes_avec_statut(tmp_path):
    c = store.add_client({"nom": "Paul", "email": "p@x.fr", "ref_externe": "L-1"})
    store.add_quote({"client_id": c["id"], "client_label": "Paul", "part_name": "Support",
                     "qty": 3, "total_price": 42.5, "currency": "EUR"})
    store.add_order({"client_id": c["id"], "client_label": "Paul", "status": "done",
                     "items": [{"designation": "Support", "qty": 3}], "total_ttc": 42.5})
    ent_d, lig_d = csv_io.lire_csv(csv_io.export_devis_csv(tmp_path / "d.csv"))
    ligne = dict(zip(ent_d, lig_d[0]))
    assert ligne["Référence externe client"] == "L-1"
    assert ligne["Code statut"] == "open" and ligne["Total"] == "42.50"
    ent_o, lig_o = csv_io.lire_csv(csv_io.export_commandes_csv(tmp_path / "o.csv"))
    ligne = dict(zip(ent_o, lig_o[0]))
    assert ligne["Code statut"] == "done" and ligne["Statut"]   # code + libellé
    assert ligne["Désignation"] == "Support"


def test_export_lisible_par_excel(tmp_path):
    """Même format que l'export comptable : « ; » et BOM UTF-8."""
    store.add_client({"nom": "Hélène", "email": "h@e.fr"})
    brut = csv_io.export_clients_csv(tmp_path / "c.csv").read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")
    assert b";" in brut.split(b"\n")[0]


# ── Interface ────────────────────────────────────────────────────────────────
def test_boite_import_propose_les_colonnes_devinees(app, tmp_path):
    from ui.components.import_clients_dialog import ImportClientsDialog
    ent, lignes = csv_io.lire_csv(_ecrire(tmp_path, "a.csv", LIMOVA))
    dlg = ImportClientsDialog(None, ent, lignes, "a.csv")
    assert dlg.colonnes()[3] == "societe"
    assert len(dlg.clients()) == 2
    assert dlg._ok.isEnabled()
    for cb in dlg._combos:                     # tout ignorer → import impossible
        cb.setCurrentIndex(0)
    assert not dlg._ok.isEnabled()
    dlg.deleteLater()


def test_fiche_client_a_le_champ_reference_externe(app):
    from ui.components.clients_page import ClientForm
    f = ClientForm(client={"nom": "Paul", "ref_externe": "L-9"})
    assert f.data()["ref_externe"] == "L-9"
    f.deleteLater()


def test_i18n_cles():
    from core.i18n import _FR, _EN
    for cle in ("client.ref_ext", "client.import", "csvio.title", "csvio.done",
                "dash.export_menu", "dash.exp_clients", "csvio.q_open"):
        assert cle in _FR and cle in _EN, cle


# ── Vrai export Limova (en-têtes EXACTS reçus du client, données fictives) ──
LIMOVA_REEL = (
    "N°;SIREN;Nom du Garage / Raison Sociale;Nom du Dirigeant;Prénom du Dirigeant;"
    "Dirigeant Complet;Fonction du Dirigeant;Adresse (Rue & N°);Code Postal;Ville;"
    "Adresse Complète;Numéro de Téléphone;Email de Contact;Site Web / Formulaire;"
    "Code NAF;Activité\n"
    "1;111222333;GARAGE TEST;Dupont;Jean;Jean Dupont;Gérant;1 Rue A;59100;Roubaix;"
    "1 Rue A, 59100 Roubaix;03 20 00 00 01;contact@garage-test.fr;https://x.fr;"
    "45.20A;Réparation\n"
    "2;444555666;CARROSSERIE ESSAI;Martin;Anne Marie;Anne Marie Martin;Président de SAS;"
    "2 Rue B;59000;Lille;2 Rue B, 59000 Lille;03 20 00 00 02;contact@essai.fr;;"
    "45.20A;Réparation\n")


def test_vrai_export_limova_colonnes(tmp_path):
    """Vécu : « Email de Contact » partait dans le NOM (le mot « contact »
    l'emportait) et le nom du dirigeant n'était pas reconnu."""
    ent, _l = csv_io.lire_csv(_ecrire(tmp_path, "limova.csv", LIMOVA_REEL))
    cols = dict(zip(ent, csv_io.deviner_colonnes(ent)))
    assert cols["Email de Contact"] == "email"
    assert cols["Nom du Dirigeant"] == "nom"
    assert cols["Prénom du Dirigeant"] == "prenom"
    assert cols["Nom du Garage / Raison Sociale"] == "societe"
    assert cols["SIREN"] == "id_fiscal"
    assert cols["Adresse (Rue & N°)"] == "adresse"
    for neutre in ("N°", "Dirigeant Complet", "Fonction du Dirigeant",
                   "Adresse Complète", "Site Web / Formulaire", "Code NAF", "Activité"):
        assert cols[neutre] == "", neutre


def test_vrai_export_limova_pays_atelier_et_reimport(tmp_path):
    """Vécu : sans colonne pays, les garages du Nord devenaient « Suisse » ;
    et réimporter recréait tout en double faute d'adresse mail reconnue."""
    store.save_company({"nom": "Nord Impression 3D", "pays": "France"})
    ent, lignes = csv_io.lire_csv(_ecrire(tmp_path, "limova.csv", LIMOVA_REEL))
    clients = csv_io.preparer_clients(lignes, csv_io.deviner_colonnes(ent))
    assert csv_io.importer_clients(clients)["crees"] == 2
    anne = next(c for c in store.list_clients() if c["id_fiscal"] == "444555666")
    assert anne["nom"] == "Anne Marie Martin"
    assert anne["email"] == "contact@essai.fr"
    assert anne["pays"] == "France"
    r = csv_io.importer_clients(clients)
    assert r["crees"] == 0 and len(store.list_clients()) == 2


def test_doublon_par_identifiant_fiscal():
    store.add_client({"societe": "Garage", "id_fiscal": "849 504 048"})
    r = csv_io.importer_clients([{"societe": "GARAGE", "id_fiscal": "849504048",
                                  "tel": "03"}])
    assert r["crees"] == 0 and r["maj"] == 1


def test_prenom_deja_dans_le_nom_complet():
    c = csv_io.preparer_clients([["Hamid", "Hamid Gaoua"]], ["prenom", "nom"])
    assert c[0]["nom"] == "Hamid Gaoua"
