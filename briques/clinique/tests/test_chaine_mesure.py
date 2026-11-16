"""La clinique en boîte — H07, la chaîne entière mesurée sur l'iMac (demande de Hiba, 12.11).

« Fini » veut dire :
- une commande fait tourner ensemble l'écoute, le cerveau et la voix : une phrase dite → le texte entendu → la
  décision du cerveau → le son de la réponse ;
- pour chaque phrase : le temps de l'écoute, du cerveau, de la voix, et le total « de la fin de la phrase au début de
  la réponse » ; les réponses de plus de cinq secondes sont listées ;
- la mémoire est relevée pendant toute la mesure : le moins de mémoire libre vu, la mémoire d'échange, et la ligne
  « la mémoire manque » si la règle écrite est franchie ;
- le compte rendu dit d'où viennent les phrases (voix de synthèse du Mac, ou sons du dépôt), et dit vrai : aucun robot ;
- une pièce absente : « PAS POSSIBLE », la raison, aucun chiffre ;
- le résultat est AJOUTÉ à docs/projet/MESURE_APERTUS.md : ni cette commande ni « apertus-essai » n'effacent la part de l'autre.
Ces essais prennent de fausses pièces : aucun modèle, aucun son. L'essai réel saute sans le serveur d'Apertus.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from briques.clinique import apertus_essai, chaine_mesure


class FausseMontre:
    """Chaque pièce « prend » le temps qu'on lui donne : la montre avance d'autant."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _pieces(montre, ecoute_s=0.8, cerveau_s=1.5, voix_s=0.3, lente=None, casse=None):
    def ecouter(son, langue):
        if casse == "ecoute":
            raise RuntimeError("micro")
        montre.t += ecoute_s
        return {"texte": f"entendu {Path(son).stem}"}

    async def decider(texte, langue):
        if casse == "cerveau":
            raise RuntimeError("éteint")
        montre.t += 6.0 if lente and lente in texte else cerveau_s
        return {"genre": "action", "resume": "se_deplacer(lieu=cuisine)", "a_dire": "D'accord."}

    def dire(texte, langue, sortie):
        montre.t += voix_s
        return Path(sortie)

    return ecouter, decider, dire


def _memoire(valeurs):
    file = list(valeurs)
    return lambda: {"disponible_go": file.pop(0) if len(file) > 1 else file[0], "echange_go": 0.0, "total_go": 16.0}


def _jouer(tmp_path, memoire=(9.0,), **kw):
    montre = FausseMontre()
    ecouter, decider, dire = _pieces(montre, **kw)
    phrases = [{"id": f"p{i}", "langue": lg, "texte": f"phrase {i}", "son": tmp_path / f"p{i}.wav"} for i, lg in enumerate(("fr", "de", "it"))]
    return asyncio.run(chaine_mesure.mesurer(phrases, ecouter, decider, dire, tmp_path, montre=montre, memoire=_memoire(memoire),
                                             origine="voix de synthèse du Mac (essai)"))


def test_pour_chaque_phrase_les_trois_temps_et_le_total(tmp_path):
    r = _jouer(tmp_path)
    assert r["possible"] is True and len(r["phrases"]) == 3
    une = r["phrases"][0]
    assert (une["ecoute_ms"], une["cerveau_ms"], une["voix_ms"], une["total_ms"]) == (800, 1500, 300, 2600)
    assert une["entendu"] == "entendu p0" and une["decision"] == "se_deplacer(lieu=cuisine)"
    assert r["total_median_ms"] == 2600 and r["total_max_ms"] == 2600 and r["plus_de_5_s"] == []
    assert "Aucune réponse de plus de 5 secondes" in "\n".join(chaine_mesure.rapport(r))


def test_une_reponse_de_plus_de_cinq_secondes_est_listee(tmp_path):
    r = _jouer(tmp_path, lente="p1")
    assert [p["id"] for p in r["plus_de_5_s"]] == ["p1"] and r["total_max_ms"] == 7100
    texte = "\n".join(chaine_mesure.rapport(r))
    assert "1 réponse de plus de 5 secondes" in texte and "7100 ms" in texte


def test_la_memoire_le_moins_de_libre_vu_et_la_ligne_la_memoire_manque(tmp_path):
    r = _jouer(tmp_path, memoire=(9.0, 6.5, 4.2, 5.0))
    assert r["memoire"]["avant_go"] == 9.0 and r["memoire"]["moins_de_libre_go"] == 4.2 and r["memoire"]["manque"] is False
    assert "La mémoire n'a pas manqué" in "\n".join(chaine_mesure.rapport(r))
    juste = _jouer(tmp_path, memoire=(9.0, 0.6, 0.6))
    assert juste["memoire"]["manque"] is True
    assert "LA MÉMOIRE MANQUE" in "\n".join(chaine_mesure.rapport(juste))


def test_une_piece_en_panne_la_phrase_est_comptee_sans_reponse_jamais_cachee(tmp_path):
    r = _jouer(tmp_path, casse="cerveau")
    assert r["sans_reponse"] == 3 and r["total_median_ms"] is None
    texte = "\n".join(chaine_mesure.rapport(r))
    assert "3 phrases sans réponse" in texte and "cerveau" in texte


def test_le_compte_rendu_dit_d_ou_viennent_les_phrases_et_qu_aucun_robot_n_a_bouge(tmp_path):
    lignes = chaine_mesure.rapport(_jouer(tmp_path))
    assert "voix de synthèse du Mac" in "\n".join(lignes) and "aucun robot" in lignes[0].lower()
    assert re.search(r"\d\d\.\d\d\.\d{4}", lignes[0])
    vide = chaine_mesure.rapport({"possible": False, "raison": "essai", "quand": "2026-11-12T13:00:00+01:00"})
    assert vide[0].startswith("LA CHAÎNE ENTIÈRE : PAS POSSIBLE") and not any(c.isdigit() for l in vide[1:] for c in l)


def test_le_resultat_est_ajoute_et_aucune_des_deux_commandes_n_efface_la_part_de_l_autre(tmp_path):
    fichier = tmp_path / "MESURE.md"
    essai = {"possible": False, "raison": "essai", "quand": "2026-11-12T13:00:00+01:00"}
    apertus_essai.ecrire(essai, fichier)
    chaine_mesure.ecrire(_jouer(tmp_path), fichier)
    texte = fichier.read_text(encoding="utf-8")
    assert "ESSAI D'APERTUS : PAS POSSIBLE" in texte and chaine_mesure.TITRE in texte and "LA CHAÎNE ENTIÈRE" in texte
    apertus_essai.ecrire({**essai, "raison": "deuxième essai"}, fichier)  # l'essai d'Apertus est refait : la chaîne reste
    texte = fichier.read_text(encoding="utf-8")
    assert "deuxième essai" in texte and texte.count(chaine_mesure.TITRE) == 1 and "LA CHAÎNE ENTIÈRE" in texte
    chaine_mesure.ecrire(_jouer(tmp_path, lente="p1"), fichier)  # la chaîne est refaite : une seule part, la nouvelle
    texte = fichier.read_text(encoding="utf-8")
    assert texte.count(chaine_mesure.TITRE) == 1 and "7100 ms" in texte and "deuxième essai" in texte


def test_la_commande_est_dans_lancer():
    assert '"chaine-mesure"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")


def test_avec_les_vraies_pieces_si_le_serveur_tourne(tmp_path):
    """L'écoute, le vrai Apertus et la voix du Mac, s'ils sont là et si le serveur tourne. Sinon : sauté."""
    import httpx

    try:
        httpx.get(chaine_mesure.URL + "/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur Apertus 8B en marche (python3 lancer.py cerveau)")
    r = chaine_mesure.mesurer_pour_de_vrai(tmp_path, limite=1)
    assert r["possible"] is True and r["phrases"][0]["total_ms"] > 0
