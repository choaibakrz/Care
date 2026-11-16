"""Brique 5 → cerveau : « prends la bouteille » → l'objet vu donne sa position, ou le robot demande.

Testé sur faux robot, caméra simulée, cerveau à règles. Les yeux éteints : rien ne change.
"""
from __future__ import annotations

import asyncio

from briques.b06_cerveau.branchements.cascade import CerveauCascade
from conftest import lancer

from aides_yeux import evenements_yeux, images_neuves, reglages_avec_yeux, systeme_avec_yeux


def test_yeux_eteints_prends_la_bouteille_comme_avant(fabrique_systeme):
    s = fabrique_systeme()

    async def go():
        await s.demarrer()
        try:
            res = await s.chaine.traiter("prends la bouteille", "fr")
            assert res.decision.genre == "action" and "Vous confirmez" in res.reponses[-1]
        finally:
            await s.arreter()

    lancer(go())


def test_la_bouteille_vue_donne_sa_direction_et_l_action_continue(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            vue = s.yeux.ou_est("bouteille")
            assert vue is not None and vue.source == "camera_simulee"
            # Depuis (1 ; 1) cap 0, la bouteille (5,2 ; 3) est à 25° à gauche. Sur la table : direction juste,
            # distance au sol trop grande (borne haute) — c'est écrit dans « precision ».
            assert 22 < vue.direction_deg < 30 and vue.distance_max_m > 4.0
            res = await s.chaine.traiter("prends la bouteille", "fr")
            # L'action continue vers le gardien… qui demande un humain : le pied du robot n'est pas vu (angle mort).
            assert res.decision.genre == "action" and res.verdict == "humain"
            assert "Je ne sais pas où sont les personnes" in res.reponses[-1]
            vu = evenements_yeux(s, "objet_vu")[-1]
            assert vu["objet"] == "bouteille" and vu["mention"] == "testé sur caméra simulée" and "table" in vu["precision"]
        finally:
            await s.arreter()

    lancer(go())


def test_avec_une_camera_fixe_qui_voit_tout_la_bouteille_vue_va_jusqu_a_la_confirmation(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages, camera="simulee_fixe")

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            res = await s.chaine.traiter("prends la bouteille", "fr")
            assert res.decision.genre == "action" and "Vous confirmez" in res.reponses[-1], res.reponses
            assert evenements_yeux(s, "objet_vu")[-1]["outil"] == "camera_simulee"
        finally:
            await s.arreter()

    lancer(go())


def test_la_bouteille_pas_vue_le_robot_demande_dans_la_langue(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages, objet_vu_depuis_s=0.3)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            s.yeux.camera.caches.add("bouteille")  # quelqu'un l'a emportée
            await images_neuves(s)
            await asyncio.sleep(0.35)
            res = await s.chaine.traiter("prends la bouteille", "fr")
            assert res.decision.genre == "question" and res.verdict is None and res.statut_action is None
            assert res.reponses[-1] == "Je ne vois pas : bouteille. Pouvez-vous me montrer où c'est ?"
            res = await s.chaine.traiter("nimm die Flasche", "de")
            assert res.reponses[-1] == "Ich sehe es nicht: Flasche. Können Sie mir zeigen, wo es ist?"
            assert evenements_yeux(s, "objet_pas_vu")[-1]["objet"] == "bouteille"
            assert not [e for e in s.bus.historique if e.type == "action_demarree" and e.donnees.get("action", {}).get("nom") == "saisir"]
            # La question est redite à l'écran du jury dans une autre langue (clé de phrases.yaml) :
            dite = [e for e in s.bus.historique if e.type == "reponse_dite" and e.donnees.get("cle") == "question_pas_vu"][-1]
            assert s.chaine.redire(dite.donnees["cle"], dite.donnees["valeurs"], "en").startswith("I cannot see it: bottle")
            s.yeux.camera.caches.discard("bouteille")  # elle revient
            await images_neuves(s)
            res = await s.chaine.traiter("prends la bouteille", "fr")
            assert res.decision.genre == "action"
        finally:
            await s.arreter()

    lancer(go())


def test_camera_en_panne_les_yeux_ne_disent_pas_je_ne_vois_pas(tmp_path, reglages):
    """Ils ne savent pas : rien ne change (le robot fera comme sans les yeux), et c'est noté dans la boîte noire."""
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            s.yeux.camera.provoquer_panne()
            await asyncio.sleep(0.2)
            decision = await s.cerveau.decider("prends la bouteille", "fr", s.prise.carte(), s.monde)
            assert decision.genre == "action" and decision.action.nom == "saisir"
            assert "pas d'image récente" in evenements_yeux(s, "objet_non_cherche")[-1]["raison"]
        finally:
            await s.arreter()

    lancer(go())


def test_les_autres_ordres_ne_passent_pas_par_les_yeux(tmp_path, reglages):
    s = systeme_avec_yeux(tmp_path, reglages)

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            for texte in ("va à la cuisine", "salue", "stop"):
                await s.chaine.traiter(texte, "fr")
            assert not evenements_yeux(s, "objet_vu") and not evenements_yeux(s, "objet_pas_vu")
        finally:
            await s.arreter()

    lancer(go())


def test_la_cascade_reste_une_cascade_pour_le_chef_de_demonstration(tmp_path, reglages):
    """Les yeux passent les décisions par leur filet sans remplacer le cerveau (le chef cherche une CerveauCascade)."""
    from commun.systeme import Systeme

    r = reglages_avec_yeux(reglages)
    r["cerveau"] = {**reglages["cerveau"], "choix": "cascade", "cascade": [{"nom": "regles"}], "serveurs": {}}
    s = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20)
    assert isinstance(s.cerveau, CerveauCascade) and s.chaine.cerveau is s.cerveau

    async def go():
        await s.demarrer()
        try:
            assert await s.yeux.attendre_une_vue()
            res = await s.chaine.traiter("prends la tasse", "fr")
            assert res.decision.genre == "action" and evenements_yeux(s, "objet_vu")[-1]["objet"] == "tasse"
        finally:
            await s.arreter()

    lancer(go())
