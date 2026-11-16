"""La clinique en boîte — J06b, le fichier des paroles de soignants (réponse de Hiba à Q7 : oui, aux conditions écrites).

Conditions : des phrases de vrais soignants sur leur travail, écrites à la main par l'ÉQUIPE, sans nom, avec leur accord,
jamais un mot sur un patient ; le fichier reste sur l'ordinateur, jamais envoyé vers GitHub.
« Fini » veut dire, pour cette première moitié (la page n'est pas encore branchée : question Q26) :
- le fichier a sa place dans un dossier qui ne part jamais vers GitHub, et git refuse son nom partout ;
- un modèle à remplir existe ; il ne contient AUCUNE parole, même en exemple ;
- la lecture ne garde qu'une parole complète : une phrase, un métier, une date, « accord : oui » ;
- une ligne qui nomme une personne ou parle d'un patient est mise de côté, et son texte n'est jamais rendu ;
- aucune fonction du programme n'écrit une parole : seule une personne de l'équipe le fait, à la main ;
- aujourd'hui, aucune parole n'existe : rien n'est inventé.
"""
from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

from briques.clinique import paroles_fichier

RACINE = Path(__file__).resolve().parents[3]
BONNE = "- « (phrase d'essai du programme, pas une parole) » — métier : soignante — date : 14.11.2026 — accord : oui"


def test_le_fichier_est_dans_un_dossier_qui_ne_part_jamais_et_git_refuse_son_nom_partout():
    assert paroles_fichier.FICHIER == RACINE / "journal" / "clinique" / "PAROLES_DES_SOIGNANTS.md"
    for chemin in ("journal/clinique/PAROLES_DES_SOIGNANTS.md", "PAROLES_DES_SOIGNANTS.md", "briques/clinique/PAROLES_DES_SOIGNANTS.md"):
        refuse = subprocess.run(["git", "check-ignore", "-q", chemin], cwd=RACINE)
        assert refuse.returncode == 0, f"git accepterait {chemin}"
    suivis = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True).stdout
    assert "PAROLES_DES_SOIGNANTS.md" not in suivis.replace("PAROLES_DES_SOIGNANTS.modele.md", "")


def test_le_modele_a_remplir_existe_et_ne_contient_aucune_parole():
    modele = (RACINE / "PAROLES_DES_SOIGNANTS.modele.md").read_text(encoding="utf-8")
    assert "Pas de nom" in modele and "patient" in modele and "accord" in modele and "à la main" in modele
    assert "journal/clinique/PAROLES_DES_SOIGNANTS.md" in modele and "GitHub" in modele
    assert "Un agent d'IA n'écrit jamais" in modele
    assert paroles_fichier.lire_le_texte(modele)["paroles"] == []  # le modèle lui-même ne compte pour aucune parole


def test_sans_le_fichier_de_l_equipe_aucune_parole(tmp_path):
    """Adapté au tour 104 avec l'accord de Hiba : disait « aucun fichier n'existe », ce qui raterait dès que l'équipe
    écrit une vraie parole. Il dit maintenant : tant que le fichier n'existe pas, zéro parole."""
    lu = paroles_fichier.lire(tmp_path / "absent.md")
    assert lu == {"paroles": [], "mises_de_cote": 0, "incompletes": 0, "fichier": False}


def test_la_lecture_ne_garde_qu_une_parole_complete_avec_accord():
    texte = "\n".join([
        "# titre", "", BONNE,
        "- « (essai) sans accord » — métier : soignant — date : 14.11.2026 — accord : non",
        "- « (essai) sans date » — métier : soignant — accord : oui",
        "- « (essai) sans métier » — date : 14.11.2026 — accord : oui",
        "- une ligne sans guillemets — métier : soignant — date : 14.11.2026 — accord : oui",
        "- « (écrire ici la phrase) » — métier : (à remplir) — date : (à remplir) — accord : oui",
        "du texte libre qui n'est pas une parole"])
    lu = paroles_fichier.lire_le_texte(texte)
    assert lu["paroles"] == [{"phrase": "(phrase d'essai du programme, pas une parole)", "metier": "soignante", "date": "14.11.2026"}]
    assert lu["incompletes"] == 5 and lu["mises_de_cote"] == 0


def test_une_ligne_qui_nomme_une_personne_ou_parle_d_un_patient_est_mise_de_cote_sans_son_texte():
    lignes = ["- « (essai) Madame Dupont dit que… » — métier : soignante — date : 14.11.2026 — accord : oui",
              "- « (essai) le patient de la chambre 12… » — métier : soignante — date : 14.11.2026 — accord : oui",
              "- « (essai) rien de spécial » — métier : soignante, Marie — date : 14.11.2026 — accord : oui",
              BONNE]
    lu = paroles_fichier.lire_le_texte("\n".join(lignes))
    assert len(lu["paroles"]) == 1 and lu["mises_de_cote"] == 3
    assert "Dupont" not in str(lu) and "chambre 12" not in str(lu) and "Marie" not in str(lu)


def test_le_dessin_de_la_page_est_pret_et_ne_montre_que_les_paroles_gardees():
    lu = paroles_fichier.lire_le_texte(BONNE + "\n- « (essai) Monsieur X… » — métier : soignant — date : 14.11.2026 — accord : oui")
    page = paroles_fichier.dessiner(lu)
    assert "DIT PAR UN SOIGNANT" in page and "(phrase d&#x27;essai du programme, pas une parole)" in page
    assert "soignante" in page and "14.11.2026" in page and "Monsieur" not in page
    assert "1 ligne mise de côté" in page
    assert "Aucune parole recueillie" in paroles_fichier.dessiner(paroles_fichier.lire_le_texte(""))


def test_aucune_fonction_du_programme_n_ecrit_une_parole():
    source = inspect.getsource(paroles_fichier)
    for interdit in ("write_text", "open(", ".write(", "\"a\"", "'w'"):
        assert interdit not in source, interdit
    assert not [nom for nom in dir(paroles_fichier) if nom.startswith(("ecrire", "ajouter", "noter"))]


def test_la_page_est_branchee_par_la_piece_de_lecture_depuis_la_reponse_a_q26():
    """Adapté au tour 104 avec l'accord de Hiba (Q26 A) : disait « la page n'est pas encore branchée »."""
    from briques.clinique import paroles

    source = inspect.getsource(paroles)
    assert "paroles_fichier" in source and "open(" not in source and "read_text" not in source
    assert "Q26" in (RACINE / "docs/projet/QUESTIONS_POUR_HIBA.md").read_text(encoding="utf-8")
