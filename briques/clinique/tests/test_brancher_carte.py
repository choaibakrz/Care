"""La clinique en boîte — J04b, brancher un robot inconnu, chronomètre en main (avenant jury, J04).

« Fini » veut dire, pour cette seconde moitié :
- la commande reçoit une carte, lance le test de conformité de la prise, et affiche « contrôles réussis : tant sur tant » ;
- si un contrôle rate, elle dit lequel, et ce qu'il faut corriger, en une phrase ;
- le chronomètre part quand on dit « je commence », et s'arrête seul quand tous les contrôles réussissent ;
- la durée est dans la fiche de vérité, sur deux lignes séparées : FAUX ROBOT (mesuré ici), et RÉEL, qui reste
  « à mesurer avec le vrai robot » ;
- la deuxième carte (le robot à plateau) passe le test de conformité ;
- la commande ne touche jamais un vrai robot ; le guide BRANCHER_UN_ROBOT.md dit la commande et le chronomètre.
Testé sur faux robot. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from briques.b01_prise.conformite import Controle, Rapport
from briques.clinique import brancher, fiche

RACINE = Path(__file__).resolve().parents[3]


def _rapport(*rates: str) -> Rapport:
    noms = ["carte d'identité valide", "état lisible", "refuse « regarder » (absente de la carte)",
            "refuse une action sans ticket", "action « se_deplacer »", "arrêt d'urgence immédiat"]
    return Rapport(robot="Faux robot à plateau", mention="testé sur faux robot",
                   controles=[Controle(nom=n, ok=n not in rates, detail="echouee" if n in rates else "") for n in noms])


def _faux_test(monkeypatch, rapports):
    """Le test de conformité est remplacé par des rapports choisis, pour essayer l'affichage et le chronomètre."""
    file = list(rapports)

    async def verifier(fabrique, complet=True, **_):
        return file.pop(0)

    monkeypatch.setattr(brancher, "verifier_conformite", verifier)


def _lancer(arguments, tmp_path, temps=None):
    lignes: list[str] = []
    code = brancher.main(arguments, ecrire=lignes.append, dossier=tmp_path, **({"temps": temps} if temps else {}))
    return code, lignes


# ---------------------------------------------------------------------------------------------- la vraie carte
def test_la_deuxieme_carte_passe_le_test_de_conformite_de_la_prise(tmp_path):
    code, lignes = _lancer(["plateau"], tmp_path)
    texte = "\n".join(lignes)
    assert code == 0, texte
    assert "contrôles réussis : 11 sur 11" in texte and "FAUX ROBOT" in lignes[0] and "Faux robot à plateau" in texte
    assert "✘" not in texte and "testé sur faux robot" in texte
    assert "chronomètre : pas démarré" in texte  # personne n'a dit « je commence »


# ---------------------------------------------------------------------------------------------- un contrôle rate
def test_si_un_controle_rate_la_commande_dit_lequel_et_quoi_corriger(monkeypatch, tmp_path):
    _faux_test(monkeypatch, [_rapport("action « se_deplacer »", "état lisible")])
    code, lignes = _lancer(["plateau"], tmp_path)
    texte = "\n".join(lignes)
    assert code == 1 and "contrôles réussis : 4 sur 6" in texte
    rates = [l for l in lignes if "✘" in l]
    assert len(rates) == 2 and all("à corriger :" in l for l in rates)
    assert "se_deplacer" in rates[1] and "la brancher dans l'adaptateur, ou l'enlever de la carte" in rates[1]
    assert "liaison" in rates[0]
    assert all(l.count(".") <= 2 for l in (r.split("à corriger :")[1] for r in rates))  # une phrase, pas un discours


def test_chaque_controle_du_test_de_conformite_a_son_conseil():
    noms = ["carte d'identité valide", "état lisible", "refuse « saisir » (absente de la carte)", "refuse une action sans ticket",
            "action « parler »", "une action longue s'annule", "arrêt d'urgence pendant un mouvement", "bloqué tant que non réarmé",
            "arrêt d'urgence immédiat", "un contrôle que personne ne connaît"]
    conseils = [brancher.conseil(n) for n in noms]
    assert all(len(c) > 20 for c in conseils) and len(set(conseils[:9])) == 9
    assert "BRANCHER_UN_ROBOT.md" in conseils[-1]


# ---------------------------------------------------------------------------------------------- le chronomètre
def test_le_chronometre_part_a_je_commence_et_s_arrete_seul_quand_tout_reussit(monkeypatch, tmp_path):
    horloge = {"t": 1000.0}
    temps = lambda: horloge["t"]
    _faux_test(monkeypatch, [_rapport("action « se_deplacer »"), _rapport()])
    code, lignes = _lancer(["plateau", "--je-commence"], tmp_path, temps)
    assert code == 0 and "chronomètre : parti" in "\n".join(lignes)
    horloge["t"] += 200
    code, lignes = _lancer(["plateau"], tmp_path, temps)  # premier passage : un contrôle rate, le chronomètre continue
    assert code == 1 and "chronomètre : 3 min 20 s, il tourne encore" in "\n".join(lignes)
    horloge["t"] += 61
    code, lignes = _lancer(["plateau"], tmp_path, temps)  # second passage : tout réussit, il s'arrête seul
    texte = "\n".join(lignes)
    assert code == 0 and "chronomètre arrêté : 4 min 21 s" in texte and "2 passages du test" in texte
    note = json.loads((tmp_path / "branchements.json").read_text(encoding="utf-8"))["plateau"]
    assert note["duree_s"] == 261 and note["passages"] == 2 and note["etiquette"] == "FAUX ROBOT" and note["fin"]
    # il ne repart pas tout seul : un passage de plus ne change pas la durée
    _faux_test(monkeypatch, [_rapport()])
    horloge["t"] += 500
    _lancer(["plateau"], tmp_path, temps)
    assert json.loads((tmp_path / "branchements.json").read_text(encoding="utf-8"))["plateau"]["duree_s"] == 261


def test_la_fiche_a_deux_lignes_separees_faux_robot_et_reel(monkeypatch, tmp_path):
    lignes = {l["titre"]: l["valeur"] for l in fiche.lignes_du_branchement(tmp_path / "branchements.json")}
    assert lignes["Brancher un robot inconnu — FAUX ROBOT"].startswith("non mesuré")
    assert lignes["Brancher un robot inconnu — RÉEL"] == "à mesurer avec le vrai robot"
    horloge = {"t": 0.0}
    _faux_test(monkeypatch, [_rapport()])
    _lancer(["plateau", "--je-commence"], tmp_path, lambda: horloge["t"])
    horloge["t"] = 95.0
    _lancer(["plateau"], tmp_path, lambda: horloge["t"])
    lignes = {l["titre"]: l["valeur"] for l in fiche.lignes_du_branchement(tmp_path / "branchements.json")}
    faux = lignes["Brancher un robot inconnu — FAUX ROBOT"]
    assert "1 min 35 s" in faux and "plateau" in faux and "1 passage" in faux and "faux robot" in faux
    assert lignes["Brancher un robot inconnu — RÉEL"] == "à mesurer avec le vrai robot"  # jamais rempli par ce programme


def test_la_repetition_affiche_les_deux_lignes_du_branchement():
    from briques.clinique import chef_clinique, repetition

    controles = {n: (lambda: repetition.Resultat(True, "SIMULÉ", "essai", {"phrases_retirees": 0})) for n in range(1, 13)}
    controles[13], controles[14] = repetition.CONTROLES[13], repetition.CONTROLES[14]
    lignes: list[str] = []
    chef_clinique.jouer(controles, ecrire=lignes.append)
    texte = "\n".join(lignes)
    assert "· Brancher un robot inconnu — FAUX ROBOT : " in texte
    assert "· Brancher un robot inconnu — RÉEL : à mesurer avec le vrai robot" in texte


# ---------------------------------------------------------------------------------------------- les refus
def test_une_carte_inconnue_ou_une_carte_de_vrai_robot_est_refusee(tmp_path, monkeypatch):
    code, lignes = _lancer(["carte_qui_n_existe_pas"], tmp_path)
    assert code == 2 and "plateau" in "\n".join(lignes)  # elle donne la liste des cartes connues
    vraie = tmp_path / "vrai.yaml"
    vraie.write_text((RACINE / "briques/b02_faux_robot/cartes/plateau.yaml").read_text(encoding="utf-8")
                     .replace("vrai_robot: false", "vrai_robot: true"), encoding="utf-8")
    appels = []
    monkeypatch.setattr(brancher, "verifier_conformite", lambda *a, **k: appels.append(1))
    code, lignes = _lancer([str(vraie)], tmp_path)
    assert code == 2 and appels == [] and "vrai robot" in "\n".join(lignes) and "--vrai" in "\n".join(lignes)


def test_la_commande_est_dans_lancer_et_dans_le_guide():
    assert '"brancher-carte"' in (RACINE / "lancer.py").read_text(encoding="utf-8")
    guide = (RACINE / "BRANCHER_UN_ROBOT.md").read_text(encoding="utf-8")
    for mot in ("brancher-carte", "--je-commence", "contrôles réussis", "chronomètre", "à mesurer avec le vrai robot"):
        assert mot in guide, mot
