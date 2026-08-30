# -*- coding: utf-8 -*-
"""Parité i18n — chaque clé FR existe en EN (et réciproquement), placeholders
identiques. Règle projet : jamais de FR sans EN (retour Emmanuel, récurrent).
Ce test la rend PERMANENTE au lieu d'un contrôle manuel par audit.
"""
import re

from core import i18n


def test_cles_symetriques():
    fr, en = set(i18n._FR), set(i18n._EN)
    assert fr - en == set(), f"clés FR sans EN : {sorted(fr - en)[:10]}"
    assert en - fr == set(), f"clés EN sans FR : {sorted(en - fr)[:10]}"


def test_placeholders_identiques():
    diff = []
    for k in set(i18n._FR) & set(i18n._EN):
        pf = set(re.findall(r"\{(\w+)\}", i18n._FR[k]))
        pe = set(re.findall(r"\{(\w+)\}", i18n._EN[k]))
        if pf != pe:
            diff.append((k, sorted(pf), sorted(pe)))
    assert not diff, f"placeholders divergents : {diff[:5]}"
