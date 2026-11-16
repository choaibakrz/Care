"""Brique 13 — /jury dans un vrai navigateur (Chromium déjà installé, Playwright pour Node). Testé sur faux robot.

Le programme sert la page sur 127.0.0.1 ; le navigateur n'a le droit d'ouvrir AUCUNE adresse d'Internet
(résolution des noms coupée, toute autre demande bloquée et notée). On envoie une phrase par la page et on vérifie
les sous-titres (dans deux langues), la fiche de vérité, la mention « testé sur faux robot », le bouton
« Internet coupé », le mode silence, le clair et le sombre, la largeur d'un téléphone, et zéro erreur JavaScript.
Saute proprement si Node, Playwright ou Chromium manquent (on n'installe rien).
"""
from __future__ import annotations

import pytest

from briques.b13_ecran.capture import lancer_navigateur, pourquoi_pas_de_navigateur, serveur_en_fond

RAISON = pourquoi_pas_de_navigateur()


@pytest.mark.skipif(RAISON is not None, reason=RAISON or "")
def test_le_jury_s_ouvre_dans_chromium_sans_internet(fabrique_systeme):
    from briques.b13_ecran.serveur import creer_app

    s = fabrique_systeme(acceleration=20)
    with serveur_en_fond(creer_app(s)) as url:
        r = lancer_navigateur(url, "verifier")
    if r.get("saute"):
        pytest.skip(r["saute"])
    v = r["verifs"]
    assert r["erreurs"] == [], r["erreurs"]  # aucune erreur JavaScript
    assert r["exterieur"] == []  # la page n'a rien demandé à Internet
    assert r["ok"] is True
    assert v["sous_titre_personne"] == "« Va à la cuisine »"
    assert v["sous_titre_robot"] == "Je vais à : cuisine." or v["sous_titre_robot"] == "C'est fait."
    assert v["sous_titre_robot_de"] in ("Ich gehe zu: Küche.", "Erledigt.")
    assert v["sous_titre_personne_de"] == "traduction indisponible hors ligne"
    assert v["compris"].startswith("aller à : cuisine")
    assert v["fiche_demandes"] == "1" and v["fiche_reussites"] == "1"
    assert v["mention"] == v["mention_haut"] == "testé sur faux robot"
    assert "Internet coupé — tout continue" in v["bandeau_internet"] and v["internet_retabli"] and v["silence"]
    for cle in ("tailles_1920", "tailles_1280", "tailles_1280_coupe"):  # grand écran : pas de défilement
        t = v[cle]
        assert t["hauteur"] <= t["fenetre_h"] and t["largeur"] <= t["fenetre_l"], (cle, t)
    for cle in ("telephone_jury", "telephone_equipe"):  # téléphone : pas de défilement de côté
        t = v[cle]
        assert t["largeur"] <= t["fenetre_l"], (cle, t)
    assert v["fond_light"] == "rgb(255, 255, 255)" and v["fond_dark"] == "rgb(0, 0, 0)"
    assert [e.donnees["coupe"] for e in s.bus.historique if e.type == "internet_coupe"] == [True, False]
