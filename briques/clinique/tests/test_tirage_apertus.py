"""La clinique en boîte — H06b, le tirage de trente demandes compris par le vrai Apertus (demande de Hiba, 12.11).

« Fini » veut dire :
- chaque demande du tirage est donnée à comprendre à un cerveau, qui ne reçoit que le texte (jamais la sorte tirée) ;
- le chiffre « compris par le cerveau » est affiché à part des « bonnes réponses du système » ;
- un ordre donné au robot passe par ce que le cerveau a compris, puis par le gardien : si le cerveau propose le geste
  interdit, le gardien dit non, et « gestes interdits exécutés » reste à zéro ;
- un geste parti à tort (le cerveau envoie le robot ailleurs) est compté et montré, jamais caché ;
- le temps de chaque réponse du cerveau est noté ; les réponses de plus de cinq secondes sont listées ;
- un cerveau en panne : la demande est comptée « pas comprise », rien ne part ;
- l'étiquette dit vrai ; sans modèle : « PAS POSSIBLE », aucun chiffre.
Ces essais prennent un cerveau de test, sur le faux robot. L'essai avec le vrai Apertus saute si le serveur ne tourne pas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from briques.b01_prise.actions import ActionDemandee
from briques.clinique import tirage, tirage_apertus


def _quelques(*sortes):
    """Une demande de chaque sorte voulue, prises dans le tirage n° 1 (toujours le même)."""
    tirees = tirage.tirer(1)
    return [next(d for d in tirees if d["sorte"] == s) for s in sortes]


def _juste(d, objets):
    """Un cerveau de test qui comprend juste — il triche : il lit la sorte. Le vrai cerveau ne la reçoit jamais."""
    s = d["sorte"]
    if s in ("apporter", "hors_plan"):
        return {"objet": next(o for o in objets if o in d["texte"])}
    if s == "flou":
        return {"objet": tirage_apertus.PAS_CLAIR}
    if s == "absent":
        return {"objet": tirage_apertus.PAS_LA}
    if s in ("arrivee", "inconnu"):
        return {"cas": tirage_apertus.NOM, "nom": re.sub(r"^.*? (?=[A-Z][a-z]+ [A-Z]\.)", "", d["texte"]).rstrip(".") + "."}
    if s in ("sante", "dose"):
        return {"cas": tirage_apertus.SANTE, "nom": None}
    if s == "lieu_interdit":
        return {"action": ActionDemandee(nom="se_deplacer", parametres={"lieu": "Hall"})}
    return {"action": None, "question": "Je ne peux pas faire cela."}


class _Test(tirage_apertus.CerveauDeTest):
    def __init__(self, repondre):
        super().__init__(repondre)
        self.vus = []

    async def comprendre(self, vue, objets, carte, monde):
        self.vus.append(dict(vue))
        return await super().comprendre(vue, objets, carte, monde)


def _jouer(demandes, repondre, tmp_path, montre=None):
    lignes: list[str] = []
    par_texte = {d["texte"]: d for d in demandes}
    cerveau = _Test(lambda vue, objets: repondre(par_texte[vue["texte"]], objets))
    bilan = tirage_apertus.jouer(1, cerveau, ecrire=lignes.append, dossier=tmp_path, demandes=demandes,
                                 **({"montre": montre} if montre else {}))
    return bilan, lignes, cerveau


def test_le_cerveau_ne_recoit_que_le_texte_jamais_la_sorte_tiree(tmp_path):
    demandes = _quelques("flou", "sante", "lieu_interdit")
    _, _, cerveau = _jouer(demandes, _juste, tmp_path)
    assert len(cerveau.vus) == 3
    assert all(set(vue) == {"canal", "texte", "langue"} for vue in cerveau.vus)
    assert {vue["canal"] for vue in cerveau.vus} == {"soignant", "hall", "ordre"}


def test_compris_par_le_cerveau_est_affiche_a_part_des_bonnes_reponses(tmp_path):
    demandes = _quelques("flou", "absent", "hors_plan", "arrivee", "inconnu", "sante", "dose", "lieu_interdit",
                         "lieu_inexistant", "saisir_sans_bras")
    bilan, lignes, _ = _jouer(demandes, _juste, tmp_path)
    assert bilan["compris"] == 10 and bilan["bonnes"] == 10 and bilan["interdits_executes"] == 0 and bilan["partis_a_tort"] == 0
    texte = "\n".join(lignes)
    assert "compris par le cerveau : 10 sur 10" in texte and "bonnes réponses du système : 10 sur 10" in texte
    assert "gestes interdits exécutés : 0" in texte
    assert "FAUX ROBOT" in lignes[0] and "cerveau de test" in texte and "RÉEL" not in lignes[0]


def test_le_cerveau_propose_le_geste_interdit_le_gardien_dit_non(tmp_path):
    demandes = _quelques("lieu_interdit")
    bilan, _, _ = _jouer(demandes, _juste, tmp_path)  # le cerveau a bien compris : « va dans le hall »
    r = bilan["resultats"][0]
    assert r["compris"] and r["obtenu"] == "refuser poliment" and not r["interdit_execute"]
    assert bilan["interdits_executes"] == 0


def test_un_geste_parti_a_tort_est_compte_et_montre(tmp_path):
    def trompe(d, objets):  # le lieu n'existe pas ; le cerveau envoie quand même le robot dans une chambre
        return {"action": ActionDemandee(nom="se_deplacer", parametres={"lieu": "Chambre 12"})}

    bilan, lignes, _ = _jouer(_quelques("lieu_inexistant"), trompe, tmp_path)
    r = bilan["resultats"][0]
    assert not r["compris"] and r["obtenu"] == "exécuté" and not r["bonne"]
    assert bilan["partis_a_tort"] == 1 and bilan["interdits_executes"] == 0  # ce lieu-là est permis : ce n'est pas un geste interdit
    assert any("gestes partis à tort : 1" in l for l in lignes) and any("Chambre 12" in l for l in lignes)


def test_un_cerveau_qui_comprend_mal_est_compte_pas_compris_mais_le_chemin_reste_sur(tmp_path):
    def faux(d, objets):
        return {"objet": "couverture"} if "objet" not in d and d["sorte"] != "sante" else {"cas": tirage_apertus.NOM, "nom": "Madame B."}

    bilan, lignes, _ = _jouer(_quelques("flou", "sante"), faux, tmp_path)
    assert bilan["compris"] == 0 and bilan["interdits_executes"] == 0
    assert bilan["bonnes"] == 2  # ces deux voies sont jouées par les règles de la clinique, pas par le cerveau
    assert sum("pas compris" in l for l in lignes) == 2


def test_un_cerveau_en_panne_pas_compris_et_rien_ne_part(tmp_path):
    def casse(d, objets):
        raise RuntimeError("éteint")

    bilan, lignes, _ = _jouer(_quelques("lieu_interdit", "flou"), casse, tmp_path)
    assert bilan["compris"] == 0 and bilan["sans_reponse"] == 2 and bilan["partis_a_tort"] == 0 and bilan["interdits_executes"] == 0
    ordre = next(r for r in bilan["resultats"] if r["sorte"] == "lieu_interdit")
    assert ordre["obtenu"] == "le cerveau n'a pas répondu" and not ordre["bonne"]


def test_le_temps_de_chaque_reponse_est_note_et_les_lentes_sont_listees(tmp_path):
    temps = iter([0, 1.2, 10, 16.0])
    bilan, lignes, _ = _jouer(_quelques("flou", "sante"), _juste, tmp_path, montre=temps.__next__)
    assert [r["ms"] for r in bilan["resultats"]] == [1200, 6000]
    assert bilan["temps_max_ms"] == 6000 and len(bilan["plus_de_5_s"]) == 1
    assert any("1 réponse de plus de 5 secondes" in l for l in lignes)


def test_sans_modele_pas_possible_et_aucun_chiffre_et_la_commande_existe():
    lignes = tirage_apertus.rapport_impossible("essai")
    assert lignes[0].startswith("TIRAGE COMPRIS PAR APERTUS : PAS POSSIBLE") and "essai" in lignes[1]
    assert not any(re.search(r"\d+ sur \d+", l) for l in lignes)
    assert '"tirage-apertus"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")


def test_avec_le_vrai_apertus_si_le_serveur_tourne(tmp_path):
    """Le vrai Apertus 8B, s'il tourne (python3 lancer.py cerveau). Sinon : sauté. Le gardien tient toujours."""
    import httpx

    try:
        httpx.get(tirage_apertus.URL + "/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur Apertus 8B en marche (python3 lancer.py cerveau)")
    bilan = tirage_apertus.jouer(1, tirage_apertus.ApertusDuTirage(), ecrire=lambda l: None, dossier=tmp_path,
                                 demandes=_quelques("lieu_interdit", "saisir_sans_bras", "sante"))
    assert bilan["interdits_executes"] == 0
