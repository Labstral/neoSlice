# -*- coding: utf-8 -*-
"""Signature Ed25519 des paquets neoForge : vecteurs officiels RFC 8032 et
refus de tout paquet modifié."""
import os

from core.neoforge import signature as S

# RFC 8032, section 7.1, TEST 1 (message vide) et TEST 2 (un octet 0x72)
VECTEURS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bac"
     "c61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e"
     "458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


def test_vecteurs_officiels_rfc8032():
    for sk, pk, msg, sig in VECTEURS:
        sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
        assert S.cle_publique(sk) == pk
        assert S.signer(sk, msg) == sig
        assert S.verifier(pk, msg, sig)


def test_tout_changement_est_refuse():
    sk = os.urandom(32)
    pk = S.cle_publique(sk)
    msg = b'{"version": "1.0.0", "sha256": "abc"}'
    sig = S.signer(sk, msg)
    assert S.verifier(pk, msg, sig)
    assert not S.verifier(pk, msg + b" ", sig)                       # manifeste modifié
    assert not S.verifier(pk, msg, sig[:-1] + bytes([sig[-1] ^ 1]))  # signature abîmée
    assert not S.verifier(S.cle_publique(os.urandom(32)), msg, sig)  # autre clé
    assert not S.verifier(pk, msg, b"")                              # rien du tout
