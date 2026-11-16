"""La clinique en boîte — J07b, la commande des preuves (avenant jury, J07).

« La commande des preuves. Elle joue les huit preuves l'une après l'autre sur le faux robot. Elle affiche une ligne par
preuve, avec son étiquette, puis PREUVES : RÉUSSIES ou PREUVES : RATÉES — (ce qui manque). Mêmes garde-fous que la grande
répétition : jamais « RÉUSSIES » si une preuve est sautée ; une vérification casse exprès une pièce et contrôle que la
commande dit bien « RATÉES ». »
Ici la preuve 1 joue trois essais au lieu de vingt (option --court), pour que la vérification reste courte ; la vraie
commande joue les vingt. Faux robot et robots simulés. Aucun vrai robot.
"""
from __future__ import annotations

import re

import pytest

from briques.clinique import preuves

ETIQUETTES = ("RÉEL", "FAUX ROBOT", "SIMULÉ", "JOUÉ")


@pytest.fixture(scope="module")
def jouees(tmp_path_factory):
    lignes: list[str] = []
    code = preuves.jouer(ecrire=lignes.append, court=True, dossier=tmp_path_factory.mktemp("preuves"))
    return code, lignes


def test_la_commande_joue_les_huit_preuves_et_dit_reussies(jouees):
    code, lignes = jouees
    texte = "\n".join(lignes)
    assert code == 0, texte
    assert lignes[-1] == "PREUVES : RÉUSSIES", texte
    for numero in range(1, 9):
        ligne = next((l for l in lignes if re.match(rf"\s*{numero}\. \[", l)), None)
        assert ligne is not None, (numero, texte)
        etiquette = re.search(r"\[([^\]]+)\]", ligne).group(1)
        assert all(e in ETIQUETTES for e in etiquette.split(" ET ")), ligne
        assert "réussie" in ligne, ligne
        assert preuves.PREUVES[numero - 1][0] in ligne  # la ligne porte la question du jury


def test_chaque_preuve_dit_ce_qu_elle_a_vu(jouees):
    _, lignes = jouees
    texte = "\n".join(lignes)
    assert "3 essais (version courte" in texte and "sur 3" in texte  # 1 : dit vrai sur le nombre d'essais
    assert "moments" in texte and "PANNE : TENUE" in texte and "erreurs attrapées" in texte
    assert re.search(r"contrôles réussis : (\d+) sur \1", texte)
    assert "pause" in texte and "a besoin d'internet : non" in texte


def test_une_preuve_qui_manque_ne_donne_jamais_reussies(tmp_path):
    controles = dict(preuves.CONTROLES)
    del controles[6]
    lignes: list[str] = []
    code = preuves.jouer(controles=controles, ecrire=lignes.append, court=True, dossier=tmp_path)
    assert code == 1 and lignes[-1].startswith("PREUVES : RATÉES") and "6" in lignes[-1]
    assert any(re.match(r"\s*6\. \[—\] MANQUANTE", l) for l in lignes)


def test_une_piece_cassee_expres_donne_ratees(monkeypatch, tmp_path):
    """La pièce des pannes est cassée exprès : finir une panne ne fait plus rien. La preuve 3 doit rater."""
    from briques.clinique import pannes

    async def ne_finit_rien(self, ident, attendre=False):
        return {"panne": ident, "active": True, "reparties": [], "en_attente": [], "dit": ""}

    monkeypatch.setattr(pannes.Pannes, "finir", ne_finit_rien)
    lignes: list[str] = []
    code = preuves.jouer(controles={3: preuves.CONTROLES[3]}, ecrire=lignes.append, court=True, dossier=tmp_path, toutes=False)
    assert code == 1 and lignes[-1].startswith("PREUVES : RATÉES") and "3" in lignes[-1], lignes


def test_une_preuve_qui_plante_est_ratee_et_dit_pourquoi(tmp_path):
    def plante():
        raise RuntimeError("pièce cassée exprès")

    lignes: list[str] = []
    code = preuves.jouer(controles={8: lambda contexte: plante()}, ecrire=lignes.append, dossier=tmp_path, toutes=False)
    assert code == 1 and any("RATÉE" in l and "pièce cassée exprès" in l for l in lignes)


def test_la_commande_est_dans_lancer():
    import lancer

    assert "preuves" in lancer.__doc__
