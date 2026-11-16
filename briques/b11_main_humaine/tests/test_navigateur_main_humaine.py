"""Brique 11 — la main humaine dans un vrai navigateur (Chromium déjà installé, Playwright pour Node). Faux robot.

L'écran de l'équipe et l'écran du jury sont ouverts en même temps, sans Internet : prendre la main, un ordre par bouton
(passé par le gardien), un ordre trop rapide refusé et expliqué, une phrase ignorée poliment, une demande du gardien
acceptée, un mot appris, puis rendre la main ; le bandeau « un humain pilote » du jury ; la largeur d'un téléphone.
Saute proprement si Node, Playwright ou Chromium manquent (on n'installe rien).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from briques.b13_ecran.capture import pourquoi_pas_de_navigateur, serveur_en_fond

RAISON = pourquoi_pas_de_navigateur()
SCRIPT = Path(__file__).with_name("navigateur_main_humaine.js")


def _lancer(url: str) -> dict:
    r = subprocess.run([shutil.which("node") or "node", str(SCRIPT), url], capture_output=True, text=True, timeout=240,
                       cwd=SCRIPT.parent)
    lignes = [ligne for ligne in r.stdout.splitlines() if ligne.startswith("{")]
    if not lignes:
        return {"ok": False, "erreurs": [f"aucune réponse du script (code {r.returncode})", r.stderr[-2000:]]}
    return json.loads(lignes[-1])


@pytest.mark.skipif(RAISON is not None, reason=RAISON or "")
def test_la_main_humaine_dans_chromium(tmp_path, reglages):
    from briques.b13_ecran.serveur import creer_app
    from commun.systeme import Systeme

    r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "regles"},
         "doute": {"aides_apprises": str(tmp_path / "aides_apprises.yaml")}}
    s = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20)
    with serveur_en_fond(creer_app(s)) as url:
        res = _lancer(url)
    if res.get("saute"):
        pytest.skip(res["saute"])
    v = res.get("verifs", {})
    assert res["erreurs"] == [], res["erreurs"]  # aucune erreur JavaScript, aucune fenêtre inattendue
    assert res["exterieur"] == []  # rien demandé à Internet
    assert res["ok"] is True
    assert v["bandeau_avant"] is True and v["ordres_caches_avant"] is True
    assert "Hiba a la main" in v["etat_equipe"]
    # Une autre tablette, sans le jeton : seulement « Libérer la main ».
    assert v["autre_liberer_visible"] and v["autre_ordres_caches"] and v["autre_rendre_cache"]
    assert v["pilote_titre"] == "UN HUMAIN PILOTE" and v["pilote_qui"] == "Hiba"
    t = v["jury_1280_avec_bandeau"]
    assert t["hauteur"] <= t["fenetre_h"] and t["largeur"] <= t["fenetre_l"], t  # 1280×720 : pas de défilement
    assert "seul « stop » passe" in v["pilote_detail"] and "gardien" in v["pilote_detail"]
    assert v["reponse_ok"].startswith("✔ Le gardien a dit oui : aller à : table")
    assert v["jury_entendu"] == "Ordre de l'humain qui pilote (Hiba) : aller à : table"
    assert "Refusé" in v["reponse_refus"] and "limite de sécurité" in v["reponse_refus"]
    assert v["jury_robot"].startswith("Un humain pilote le robot en ce moment")
    assert "prendre : tasse" in v["demande"] and "fragile" in v["demande"]
    assert v["reponse_demande"].startswith("Accepté")
    # Trois ordres par boutons : la table, le trop rapide, la tasse (son « Accepter » n'est pas un nouvel ordre).
    assert float(v["fiche_humain"]) > 0 and v["fiche_humain_d"].startswith("3 ordre(s) de l'humain")
    assert re.fullmatch(r"dont \d+ par l'humain", v["fiche_reussites_d"]), v["fiche_reussites_d"]
    assert v["bandeau_apres"] is True and v["ordres_caches_apres"] is True
    assert v["telephone"]["largeur"] <= v["telephone"]["fenetre_l"], v["telephone"]
    pilotage = [(e.donnees["quoi"], e.donnees.get("qui")) for e in s.bus.historique if e.type == "pilotage_humain"]
    assert pilotage[0] == ("reprise", "Hiba") and ("rendu", "Hiba") in pilotage and pilotage[-1] == ("rendu", "Luca")
    # Chaque action partie vers le robot a reçu le « oui » du gardien dans la même conversation.
    oui = {e.conversation for e in s.bus.historique if e.type == "gardien_decision" and e.donnees["verdict"] == "oui"}
    assert all(e.conversation in oui for e in s.bus.historique if e.type == "action_demarree")
