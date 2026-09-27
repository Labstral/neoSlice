# -*- coding: utf-8 -*-
"""Signatures Ed25519 en Python pur (implémentation de référence RFC 8032).

neoForge exécute du code téléchargé : neoSlice n'installe un paquet que si son
manifeste est signé par la clé privée du projet (gardée hors du dépôt, voir
tools/publier_neoforge.py). La clé publique est dans installation.py.
Aucune dépendance : le module de chiffrement « cryptography » n'est pas dans
l'exe. Vérifier une signature prend quelques millisecondes.
"""
from __future__ import annotations

import hashlib

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_RACINE_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512_modq(s: bytes) -> int:
    return int.from_bytes(hashlib.sha512(s).digest(), "little") % _Q


def _add(P, Q):
    a = (P[1] - P[0]) * (Q[1] - Q[0]) % _P
    b = (P[1] + P[0]) * (Q[1] + Q[0]) % _P
    c = 2 * P[3] * Q[3] * _D % _P
    d = 2 * P[2] * Q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f, g * h, f * g, e * h)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _egal(P, Q) -> bool:
    return ((P[0] * Q[2] - Q[0] * P[2]) % _P == 0
            and (P[1] * Q[2] - Q[1] * P[2]) % _P == 0)


def _x(y: int, signe: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if signe else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RACINE_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != signe:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compresser(P) -> bytes:
    zi = _inv(P[2])
    x, y = P[0] * zi % _P, P[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompresser(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    signe = y >> 255
    y &= (1 << 255) - 1
    x = _x(y, signe)
    return None if x is None else (x, y, 1, x * y % _P)


def _etendre(secret: bytes):
    if len(secret) != 32:
        raise ValueError("clé privée : 32 octets attendus")
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def cle_publique(secret: bytes) -> bytes:
    a, _ = _etendre(secret)
    return _compresser(_mul(a, _G))


def signer(secret: bytes, message: bytes) -> bytes:
    a, prefixe = _etendre(secret)
    A = _compresser(_mul(a, _G))
    r = _sha512_modq(prefixe + message)
    R = _compresser(_mul(r, _G))
    h = _sha512_modq(R + A + message)
    return R + int.to_bytes((r + h * a) % _Q, 32, "little")


def verifier(publique: bytes, message: bytes, signature: bytes) -> bool:
    """True seulement si `signature` a été produite par la clé privée de
    `publique` sur exactement `message`. Jamais d'exception."""
    try:
        if len(publique) != 32 or len(signature) != 64:
            return False
        A = _decompresser(publique)
        R = _decompresser(signature[:32])
        if A is None or R is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _Q:
            return False
        h = _sha512_modq(signature[:32] + publique + message)
        return _egal(_mul(s, _G), _add(R, _mul(h, A)))
    except Exception:
        return False
