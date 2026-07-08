"""Gestion de la licence neoSlice Pro.

Modèle : 5 diagnostics gratuits, puis déblocage « Pro » via une clé de
licence Gumroad (paiement unique). L'activation se fait UNE fois en ligne
(API Gumroad) ; ensuite l'état est mémorisé dans prefs.json et fonctionne
hors-ligne.

État stocké dans ~/.neoslice/prefs.json (via core.prefs.PREFS) :
  diag_free_used        int   — nombre de diagnostics gratuits consommés
  pro_unlocked          bool  — True si une clé valide a été activée
  license_key           str   — la clé activée

Mode test (sans vraie clé), via variable d'environnement NEOSLICE_LICENSE_TEST :
  "pro"      → considéré comme Pro (illimité)
  "expired"  → 0 essai restant (pour tester le paywall)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error

try:
    import winreg   # miroir anti-reset dans le registre Windows (HKCU)
except ImportError:
    winreg = None   # non-Windows : on se rabat sur prefs.json seul

# Contexte SSL avec le bundle de certificats certifi. CRITIQUE pour macOS : une
# app Python gelée (PyInstaller) n'a pas accès au magasin de certificats système
# → tout HTTPS échouait ("Pas de connexion Internet"). certifi fournit les CA.
# Sur Windows ça marchait déjà via le magasin système ; certifi marche aussi.
try:
    import certifi
    _SSL_CTX: "ssl.SSLContext | None" = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = None   # repli : contexte par défaut (Windows OK, Mac via SSL_CERT_FILE)

from core.prefs import PREFS
from core.i18n import _

# ── Configuration ───────────────────────────────────────────────────────────
# Pré-lancement : tant que True, la version Pro est annoncée « bientôt
# disponible » et AUCUN accès n'est possible (diagnostic, devis, activation).
# Passer à False le jour du lancement public de neoSlice Pro.
PRO_COMING_SOON = False   # LANCEMENT : neoSlice Pro accessible (diagnostic + devis + activation Gumroad)

ESSAIS_GRATUITS = 0   # essais gratuits SUPPRIMES (2026-07-08) : le Diagnostic IA est
#   désormais une fonctionnalité Pro pure (activation requise, plus de version d'essai).
PRIX_AFFICHE = "$19.99"
MAX_APPAREILS = 3        # nombre max d'activations (uses Gumroad)

# Page d'achat Gumroad (bouton « Débloquer Pro »).
LIEN_ACHAT = "https://neoslice.gumroad.com/l/zetye"

# Vérification de licence Gumroad — endpoint public (aucun token vendeur requis,
# product_id + clé suffisent). Gumroad EXIGE le product_id (le permalink ne marche
# que pour les clés inexistantes). product_id = identifiant public du produit.
_GUMROAD_VERIFY = "https://api.gumroad.com/v2/licenses/verify"
_GUMROAD_PRODUCT_ID = "xMWXJLoFcQEeEnUzG4VG3g=="
_GUMROAD_PERMALINK = "zetye"   # juste pour mémoire (lien d'achat)

# Clés prefs.json
_K_USED = "diag_free_used"
_K_PRO = "pro_unlocked"
_K_LICENSE = "license_key"
_K_VALIDATED = "pro_last_validated"   # timestamp dernière validation en ligne
_K_SIG = "_lic_sig"                   # HMAC de l'état (anti-édition manuelle)

# Registre Windows (miroir anti-reset du compteur d'essais).
_REG_PATH = r"Software\neoSlice"

# ──────────────────────────────────────────────────────────────────────────────
# Niveau 1 — intégrité locale : signature HMAC + empreinte machine + miroir
# ──────────────────────────────────────────────────────────────────────────────
# But : empêcher la triche par édition de prefs.json (essais remis à 0 ou
# pro_unlocked=true à la main). Le secret est dérivé de constantes (pas un
# littéral greppable). La sécurité réelle du Pro vient surtout du Niveau 2
# (re-validation en ligne) — même si ce secret fuite, falsifier Pro exige une
# vraie clé payée.

_SECRET = hashlib.sha256(
    ("neoSlice" + "::" + "Pr0-2026" + "::" + "lic-hmac-v1").encode("utf-8")
).digest()

_FP_CACHE: str | None = None


def _machine_fingerprint() -> str:
    """Empreinte stable de la machine (hashée). Lie l'état à ce PC : copier
    prefs.json sur une autre machine invalide la signature."""
    global _FP_CACHE
    if _FP_CACHE is not None:
        return _FP_CACHE
    parts: list[str] = []
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _t = winreg.QueryValueEx(k, "MachineGuid")
                parts.append(str(guid))
        except Exception:
            pass
    elif sys.platform == "darwin":
        # UUID matériel stable (ne change pas avec le hostname/réseau).
        try:
            import re as _re, subprocess as _sp
            out = _sp.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                          capture_output=True, text=True, timeout=5).stdout
            m = _re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                parts.append(m.group(1))
        except Exception:
            pass
    parts.append(os.environ.get("USERNAME") or os.environ.get("USER") or "")
    try:
        parts.append(socket.gethostname())
    except Exception:
        pass
    raw = "|".join(p for p in parts if p) or "neoSlice-default"
    _FP_CACHE = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return _FP_CACHE


def _to_int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _sign(used: int, pro: bool, key: str) -> str:
    msg = f"{int(used)}|{int(bool(pro))}|{key}|{_machine_fingerprint()}"
    return hmac.new(_SECRET, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_used(used: int) -> str:
    """Signature légère du seul compteur (pour le miroir registre)."""
    msg = f"U|{int(used)}|{_machine_fingerprint()}"
    return hmac.new(_SECRET, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_actkey(key: str) -> str:
    """Marqueur « cette clé a déjà été comptée sur CETTE machine ».
    Lié à (clé + empreinte machine) : permet de réactiver/réinstaller sur le même
    PC sans reconsommer d'usage Gumroad, tout en gardant le plafond par appareil."""
    msg = f"A|{key}|{_machine_fingerprint()}"
    return hmac.new(_SECRET, msg.encode("utf-8"), hashlib.sha256).hexdigest()


# ── Backend de stockage sécurisé HORS prefs.json ───────────────────────────────
# Sert au miroir anti-reset des essais (u/s) et au marqueur réinstall-safe (a).
#   Windows : registre HKCU\Software\neoSlice
#   macOS   : Trousseau (Keychain) via la commande `security` (service "neoSlice")
#   Autre   : aucun → on se rabat sur prefs.json seul (dégradé)
import subprocess as _subprocess

_IS_MAC = sys.platform == "darwin"
_KC_SERVICE = "neoSlice"


def _kc_read(account: str) -> str | None:
    try:
        r = _subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", _KC_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _kc_write(account: str, value: str) -> None:
    try:
        _subprocess.run(
            ["security", "add-generic-password", "-U",
             "-a", account, "-s", _KC_SERVICE, "-w", str(value)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _kc_delete(account: str) -> None:
    try:
        _subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", _KC_SERVICE],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _reg_read() -> tuple[int, str] | None:
    if _IS_MAC:
        u, s = _kc_read("u"), _kc_read("s")
        if u is None or s is None:
            return None
        try:
            return int(u), s
        except ValueError:
            return None
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
            used, _t1 = winreg.QueryValueEx(k, "u")
            sig, _t2 = winreg.QueryValueEx(k, "s")
            return int(used), str(sig)
    except Exception:
        return None


def _reg_write(used: int, sig: str) -> None:
    if _IS_MAC:
        _kc_write("u", str(max(0, int(used))))
        _kc_write("s", sig)
        return
    if winreg is None:
        return
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
            winreg.SetValueEx(k, "u", 0, winreg.REG_DWORD, max(0, int(used)))
            winreg.SetValueEx(k, "s", 0, winreg.REG_SZ, sig)
    except Exception:
        pass


def _reg_read_actkey() -> str | None:
    """Lit le marqueur d'activation de cette machine (valeur 'a')."""
    if _IS_MAC:
        return _kc_read("a")
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
            a, _t = winreg.QueryValueEx(k, "a")
            return str(a)
    except Exception:
        return None


def _reg_write_actkey(sig: str) -> None:
    """Pose le marqueur d'activation (survit à la désactivation et à la
    suppression de prefs.json → réinstallation sur le même PC sans reconsommer)."""
    if _IS_MAC:
        _kc_write("a", sig)
        return
    if winreg is None:
        return
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
            winreg.SetValueEx(k, "a", 0, winreg.REG_SZ, sig)
    except Exception:
        pass


def _reg_clear() -> None:
    if _IS_MAC:
        for account in ("u", "s", "a"):
            _kc_delete(account)
        return
    if winreg is None:
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _REG_PATH)
    except Exception:
        pass


def _read_state() -> dict:
    """Lit l'état licence en vérifiant son intégrité.

    - Signature valide → on fait confiance aux valeurs.
    - Aucune signature → état hérité (avant cette version) : confiance unique,
      re-signé au prochain write. Un Pro hérité sera confirmé par le Niveau 2.
    - Signature présente mais fausse → édition manuelle détectée : on verrouille
      (essais épuisés, Pro retiré — re-validable en ligne si clé réelle).
    - Le compteur d'essais est ensuite borné au max avec le miroir registre :
      vider/baisser une seule des deux sources ne sert à rien."""
    used = _to_int(PREFS.get(_K_USED, 0))
    pro = bool(PREFS.get(_K_PRO, False))
    key = PREFS.get(_K_LICENSE, "") or ""
    val = PREFS.get(_K_VALIDATED, 0)
    sig = PREFS.get(_K_SIG, "") or ""

    if sig:
        if not hmac.compare_digest(sig, _sign(used, pro, key)):
            # Édition manuelle (ou prefs.json copié d'une autre machine).
            used = ESSAIS_GRATUITS
            pro = False
            key = ""
    # (pas de sig → état hérité : valeurs telles quelles)

    reg = _reg_read()
    if reg is not None:
        r_used, r_sig = reg
        if hmac.compare_digest(r_sig, _sign_used(r_used)):
            used = max(used, r_used)   # anti-reset : on garde le plus élevé

    return {"used": max(0, used), "pro": pro, "key": key, "validated": val}


def _write_state(used: int, pro: bool, key: str, validated=None) -> None:
    """Écrit l'état + sa signature (prefs.json) et met à jour le miroir registre."""
    if validated is None:
        validated = PREFS.get(_K_VALIDATED, 0)
    used = max(0, int(used))
    PREFS.set(_K_USED, used)
    PREFS.set(_K_PRO, bool(pro))
    PREFS.set(_K_LICENSE, key or "")
    PREFS.set(_K_VALIDATED, validated)
    PREFS.set(_K_SIG, _sign(used, bool(pro), key or ""))
    _reg_write(used, _sign_used(used))


def _mode_test() -> str | None:
    # Porte de test réservée au DÉVELOPPEMENT (exécution depuis les sources).
    # Dans un build distribué (PyInstaller → sys.frozen), on l'ignore totalement :
    # impossible de débloquer Pro via une variable d'environnement sur l'exe.
    import sys
    if getattr(sys, "frozen", False):
        return None
    val = os.environ.get("NEOSLICE_LICENSE_TEST", "").strip().lower()
    return val or None


def est_pro() -> bool:
    """True si l'utilisateur a débloqué neoSlice Pro.

    Exige une clé non vide : pro_unlocked=true posé à la main (sans clé) est
    ignoré → ferme l'exploit le plus coûteux même hors-ligne."""
    mode = _mode_test()
    if mode == "pro":
        return True
    if mode == "expired":
        return False
    st = _read_state()
    return bool(st["pro"] and st["key"])


def essais_restants() -> int:
    """Nombre de diagnostics gratuits encore disponibles (0 si Pro non requis)."""
    mode = _mode_test()
    if mode == "pro":
        return ESSAIS_GRATUITS
    if mode == "expired":
        return 0
    return max(0, ESSAIS_GRATUITS - _read_state()["used"])


def consommer_essai() -> None:
    """Décrémente d'un essai gratuit. Sans effet en mode test ou si déjà Pro."""
    if _mode_test() or est_pro():
        return
    st = _read_state()
    _write_state(st["used"] + 1, st["pro"], st["key"])


def peut_analyser() -> bool:
    """True si le Diagnostic IA est autorisé. Essais gratuits supprimés → Pro requis."""
    return est_pro()


def reset_for_test() -> None:
    """Réinitialise complètement l'état (essais + Pro) avec une signature valide.
    Réservé aux tests/dev — efface aussi le miroir registre."""
    _reg_clear()
    _write_state(0, False, "", validated=0)


def revalidate_pro() -> None:
    """Niveau 2 — re-valide le Pro en ligne (à lancer en arrière-plan au démarrage).

    - Pro local sans clé → révoqué (falsification).
    - Clé présente : serveur joignable et clé invalide (remboursement, révocation)
      → Pro retiré. Serveur injoignable → on garde l'état (pas de punition
      hors-ligne, achat unique). Clé toujours valide → on rafraîchit l'horodatage."""
    if _mode_test():
        return
    st = _read_state()
    if not st["pro"]:
        return
    if not st["key"]:
        _clear_local()
        return
    # Re-vérification Gumroad SANS incrémenter le compteur d'usages.
    net_ok, success, _uses, _msg = _gumroad_verify(st["key"], increment=False)
    if not net_ok:
        return   # hors-ligne → on garde le Pro (grâce, achat unique)
    if success:
        _write_state(st["used"], True, st["key"], validated=time.time())
    else:
        _clear_local()   # clé invalide / remboursée → retirer le Pro


def revalidate_pro_async() -> None:
    """Lance revalidate_pro() dans un thread démon (non bloquant au démarrage)."""
    threading.Thread(target=revalidate_pro, daemon=True).start()


def _clear_local() -> None:
    """Retire l'état Pro local (sans toucher au compteur d'essais)."""
    st = _read_state()
    _write_state(st["used"], False, "")


def _gumroad_verify(cle: str, increment: bool) -> tuple[bool, bool, int, str]:
    """Vérifie une clé de licence via l'API Gumroad.

    Retourne (réseau_ok, succès, uses, message).
      - réseau_ok=False → pas de connexion (on ne tranche pas).
      - increment=True  → compte une activation (nouvel appareil).
      - increment=False → simple validation, ne consomme rien.
    Un achat remboursé / contesté / annulé est traité comme invalide.
    """
    if not cle:
        return True, False, 0, _("license.empty_key")
    payload = urllib.parse.urlencode({
        "product_id": _GUMROAD_PRODUCT_ID,
        "license_key": cle,
        "increment_uses_count": "true" if increment else "false",
    }).encode("utf-8")
    req = urllib.request.Request(
        _GUMROAD_VERIFY, data=payload,
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Clé invalide → Gumroad renvoie 404 + {success:false, message:...}
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return True, False, 0, _("license.server_error", code=exc.code)
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        return False, False, 0, _("license.no_connection")
    except Exception as exc:  # pragma: no cover
        return False, False, 0, _("license.unexpected", error=exc)

    success = bool(data.get("success"))
    uses = _to_int(data.get("uses", 0))
    msg = data.get("message", "")
    purchase = data.get("purchase") or {}
    if success and (purchase.get("refunded") or purchase.get("disputed")
                    or purchase.get("chargebacked")):
        success = False   # achat annulé/remboursé → licence invalide
    return True, success, uses, msg


def activer_cle(cle: str) -> tuple[bool, str]:
    """Active une clé de licence Gumroad — robuste aux réseaux lents/protégés.

    Étapes :
      1. Validation IDEMPOTENTE (increment=False) → rejouable sans rien consommer.
      2. Plafond d'appareils basé sur le compteur LU (pas d'incrément aveugle).
      3. Déblocage LOCAL immédiat : un client qui a payé n'est JAMAIS verrouillé
         par un aléa réseau (timeout, antivirus…).
      4. Décompte d'appareil (slot Gumroad) réclamé en best-effort, sans bloquer
         le succès. Réinstall-safe via le marqueur machine.
    """
    cle = (cle or "").strip()
    if not cle:
        return False, _("license.empty_key")

    _st = _read_state()
    # Machine déjà comptée pour cette clé ? (clé active localement OU marqueur
    # présent → survit désactivation/réinstallation). Si oui : aucun slot à reprendre.
    deja_active_ici = (cle == _st["key"])
    deja_compte_ici = deja_active_ici or (_reg_read_actkey() == _sign_actkey(cle))

    # 1) Validation idempotente — NE consomme PAS d'usage, rejouable sans risque.
    net_ok, success, uses, _msg = _gumroad_verify(cle, increment=False)
    if not net_ok:
        return False, _("license.no_connection")
    if not success:
        return False, _("license.invalid_or_max")

    # 2) Plafond appareils sur le compteur LU (une réinstall repasse toujours).
    if not deja_compte_ici and uses >= MAX_APPAREILS:
        return False, _("license.invalid_or_max")   # trop d'appareils

    # 3) Déblocage LOCAL garanti (le client a payé → jamais bloqué par le réseau).
    _write_state(_st["used"], True, cle, validated=time.time())
    _reg_write_actkey(_sign_actkey(cle))

    # 4) Réclame le slot côté Gumroad en best-effort (n'affecte pas le succès).
    if not deja_compte_ici:
        threading.Thread(target=_claim_device_slot, args=(cle,), daemon=True).start()

    return True, _("license.already_active") if deja_active_ici else _("license.activated")


def _claim_device_slot(cle: str) -> None:
    """Incrémente le compteur d'usages Gumroad (décompte d'appareil), best-effort.
    Un échec réseau ici n'empêche pas l'activation locale déjà accordée."""
    try:
        _gumroad_verify(cle, increment=True)
    except Exception:
        pass


def desactiver_appareil() -> tuple[bool, str]:
    """Retire l'état Pro local de cet appareil.

    Note : Gumroad ne permet pas de libérer un emplacement d'activation à
    distance (pas d'API par appareil). On nettoie donc uniquement en local."""
    _clear_local()
    return True, _("license.removed")
