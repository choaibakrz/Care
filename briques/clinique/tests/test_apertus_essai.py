"""La clinique en boîte — R2, Apertus sur l'iMac : un essai du vrai modèle, mesuré.

« Fini » veut dire :
- la commande lance le serveur du modèle par la pièce de l'ossature (brique 6), mesure le temps de chargement, pose
  les demandes du banc de l'ossature, et éteint le serveur qu'elle a lancé, même si l'essai casse ;
- le compte rendu ne contient que des chiffres calculés depuis les réponses : bonnes réponses, temps médian, temps le
  plus long, et la liste des réponses de plus de cinq secondes ;
- l'étiquette dit vrai : « RÉEL (vrai modèle) » pour le cerveau, « FAUX ROBOT » pour le robot ;
- modèle absent, programme absent, serveur qui ne démarre pas : « PAS POSSIBLE », la raison, et aucun chiffre ;
- une panne du modèle n'est jamais une bonne réponse.
Ces essais-ci n'ont besoin d'aucun modèle : un faux serveur et de fausses réponses. L'essai avec le vrai Apertus est
à la fin ; il saute si le serveur ne tourne pas sur le port des réglages.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from briques.clinique import apertus_essai


class FauxServeur:
    def __init__(self, modele: Path, pret: bool = True, deja: bool = False) -> None:
        self.nom, self.modele, self.port, self.url = "apertus_8b", modele, 8089, "http://127.0.0.1:8089"
        self.pret, self.deja, self.lances, self.eteints, self.proc = pret, deja, 0, 0, None

    def en_marche(self) -> bool:
        return self.deja

    def commande(self) -> list[str]:
        return ["llama-server", "-m", str(self.modele)]

    def lancer(self) -> None:
        self.lances += 1

    def attendre(self, delai_s: float = 0) -> bool:
        return self.pret

    def eteindre(self) -> None:
        self.eteints += 1


def _modele(tmp_path) -> Path:
    fichier = tmp_path / "modele.gguf"
    fichier.write_bytes(b"faux")
    return fichier


def _fausses_reponses(temps_ms, mauvaises=(), erreurs=()):
    async def mesurer(cerveau, demandes, langues):
        detail = [{"id": f"d{i}", "categorie": "normal", "phrase": f"phrase {i}", "bon": i not in mauvaises and i not in erreurs,
                   "ms": ms, "erreur": "panne" if i in erreurs else None} for i, ms in enumerate(temps_ms)]
        return {lg: {"detail": detail} for lg in langues}

    return mesurer


def _jouer(serveur, mesurer, langues=("fr",)):
    return asyncio.run(apertus_essai.essai(serveur, list(langues), mesurer=mesurer, demandes=[], cerveau=object()))


def test_les_chiffres_sont_calcules_depuis_les_reponses(tmp_path):
    serveur = FauxServeur(_modele(tmp_path))
    r = _jouer(serveur, _fausses_reponses([900, 1100, 1000, 6200], mauvaises=(2,)), langues=("fr", "de"))
    assert r["possible"] is True and r["demandes"] == 8 and r["bonnes"] == 6
    assert r["temps_median_ms"] == 1050 and r["temps_max_ms"] == 6200
    assert [(l["langue"], l["phrase"], l["ms"]) for l in r["plus_de_5_s"]] == [("fr", "phrase 3", 6200), ("de", "phrase 3", 6200)]
    assert r["par_langue"]["fr"] == {"demandes": 4, "bonnes": 3, "temps_median_ms": 1050, "temps_max_ms": 6200, "erreurs": 0}
    assert isinstance(r["chargement_s"], float)
    texte = "\n".join(apertus_essai.rapport(r))
    assert "6 bonnes réponses sur 8" in texte and "2 réponses de plus de 5 secondes" in texte and "phrase 3" in texte


def test_l_etiquette_dit_vrai_modele_et_faux_robot(tmp_path):
    r = _jouer(FauxServeur(_modele(tmp_path)), _fausses_reponses([800, 900]))
    lignes = apertus_essai.rapport(r)
    assert "RÉEL (vrai modèle)" in lignes[0] and "FAUX ROBOT" in lignes[0]
    assert re.search(r"\d\d\.\d\d\.\d{4}", lignes[0])
    assert any("aucun vrai robot" in l for l in lignes)
    assert any("Aucune réponse de plus de 5 secondes" in l for l in lignes)


def test_une_panne_du_modele_n_est_jamais_une_bonne_reponse(tmp_path):
    r = _jouer(FauxServeur(_modele(tmp_path)), _fausses_reponses([500, 700, 900], erreurs=(1,)))
    assert r["bonnes"] == 2 and r["erreurs"] == 1
    assert "1 fois, le modèle n'a pas répondu" in "\n".join(apertus_essai.rapport(r))


def test_le_serveur_lance_par_l_essai_est_eteint_meme_si_l_essai_casse(tmp_path):
    serveur = FauxServeur(_modele(tmp_path))

    async def casse(cerveau, demandes, langues):
        raise RuntimeError("cassé exprès")

    r = _jouer(serveur, casse)
    assert serveur.lances == 1 and serveur.eteints == 1
    assert r["possible"] is False and "cassé exprès" in r["raison"]


def test_un_serveur_deja_en_marche_n_est_ni_relance_ni_eteint(tmp_path):
    serveur = FauxServeur(_modele(tmp_path), deja=True)
    r = _jouer(serveur, _fausses_reponses([500]))
    assert serveur.lances == 0 and serveur.eteints == 0
    assert r["chargement_s"] is None  # pas mesuré : ce n'est pas nous qui l'avons chargé
    assert "temps de chargement : non mesuré" in "\n".join(apertus_essai.rapport(r))


@pytest.mark.parametrize("cas, mot", [("modele", "modèle absent"), ("programme", "llama-server"), ("demarrage", "n'a pas démarré")])
def test_pas_possible_la_raison_et_aucun_chiffre(tmp_path, monkeypatch, cas, mot):
    serveur = FauxServeur(_modele(tmp_path), pret=cas != "demarrage")
    if cas == "modele":
        serveur.modele = tmp_path / "absent.gguf"
    if cas == "programme":
        serveur.commande = lambda: ["python", "-m", "llama_cpp.server"]
    r = _jouer(serveur, _fausses_reponses([500]))
    assert r["possible"] is False and mot in r["raison"]
    lignes = apertus_essai.rapport(r)
    assert lignes[0].startswith("ESSAI D'APERTUS : PAS POSSIBLE")
    assert not any(re.search(r"\d+ bonnes|\d+ ms|sur \d+", l) for l in lignes)
    if cas == "demarrage":
        assert serveur.eteints == 1


def test_le_fichier_de_mesure_est_ecrit_et_la_commande_est_dans_lancer(tmp_path):
    r = _jouer(FauxServeur(_modele(tmp_path)), _fausses_reponses([800, 900]))
    fichier = apertus_essai.ecrire(r, tmp_path / "MESURE.md")
    assert "RÉEL (vrai modèle)" in fichier.read_text(encoding="utf-8")
    assert '"apertus-essai"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")


def test_avec_le_vrai_apertus_si_le_serveur_tourne():
    """Le vrai Apertus 8B, s'il tourne sur le port des réglages (python3 lancer.py cerveau). Sinon : sauté."""
    import httpx

    from commun.systeme import charger_reglages, creer_serveurs

    serveur = creer_serveurs(charger_reglages()).get("apertus_8b")
    if serveur is None:
        pytest.skip("pas de serveur apertus_8b dans les réglages")
    try:
        httpx.get(serveur.url + "/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur Apertus 8B en marche (python3 lancer.py cerveau)")
    r = asyncio.run(apertus_essai.essai(serveur, ["fr"], limite=3))
    assert r["possible"] is True and r["demandes"] == 3 and r["erreurs"] == 0
