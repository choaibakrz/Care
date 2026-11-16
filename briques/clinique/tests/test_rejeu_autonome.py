"""La clinique en boîte — T29, le rejeu autonome (cahier 5.11 ; avenant J03).

« Après une répétition, une commande produit un dossier de pages simples qui rejouent la séance, sans serveur, sans
cerveau, sans robot. On l'ouvre par un double-clic. En haut : « Rejeu d'une séance enregistrée le (date) — données
inventées ». Ce dossier ne contient ni mot de passe, ni chemin de nos ordinateurs, ni rien d'autre que la séance. »
« Fini quand : les pages du rejeu ne chargent rien depuis l'extérieur ; une vérification prouve qu'elles ne contiennent
que la séance, sans chemin de nos ordinateurs ; le mode d'emploi du rejeu tient en trois lignes. »
J03 : « Quand tu feras T29, mets-y aussi la liste des moments. »
Le dossier n'est jamais mis en ligne : c'est Hiba qui décide. Faux robot et robots simulés.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from briques.clinique import fiche, rejeu_autonome

RACINE = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def rejeu(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("rejeu")
    bilan = rejeu_autonome.fabriquer(dossier / "rejeu", ecrire=lambda _: None)
    return dossier / "rejeu", bilan


def _pages(dossier: Path) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in dossier.iterdir() if f.suffix == ".html"}


def test_le_dossier_a_une_page_d_entree_avec_la_date_et_la_marque(rejeu):
    dossier, bilan = rejeu
    index = (dossier / "index.html").read_text(encoding="utf-8")
    assert re.search(r"Rejeu d’une séance enregistrée le \d{2}\.\d{2}\.\d{4} à \d{1,2} h \d{2} — données inventées", index), index[:600]
    assert bilan["repetition"] == "RÉUSSIE" and "RÉPÉTITION : RÉUSSIE" in index


def test_les_pages_rejouent_la_seance_les_etapes_la_fiche_et_les_moments(rejeu):
    dossier, bilan = rejeu
    index = (dossier / "index.html").read_text(encoding="utf-8")
    for numero in range(1, 15):
        assert f"<td>{numero}</td>" in index, numero
    import html

    for titre in fiche.LIGNES_DU_CAHIER + fiche.LIGNES_EN_PLUS:
        assert titre in html.unescape(index), titre
    assert "Les moments" in index and "erreurs attrapées" in index
    assert bilan["moments"] >= 1  # la répétition a au moins un moment marquant (un papier non rangé, une panne…)
    liens = re.findall(r'href="([^"]+)"', index)
    moments = [l for l in liens if l.startswith("moment_")]
    assert len(moments) == bilan["moments"]
    for lien in moments:  # chaque moment a sa page, avec les quatre choses (J03)
        page = (dossier / lien).read_text(encoding="utf-8")
        for chose in ("1. Ce que le système a vu ou entendu", "2. Ce qu’il a décidé, et pourquoi", "3. Ce qu’il a fait",
                      "4. Les dix secondes d’avant et d’après"):
            assert chose in page, (lien, chose)
        assert 'href="index.html"' in page


def test_les_pages_ne_chargent_rien_depuis_l_exterieur(rejeu):
    dossier, _ = rejeu
    for nom, page in _pages(dossier).items():
        assert "http://" not in page and "https://" not in page and "//" not in re.sub(r"<!--.*?-->", "", page).replace("://", ""), nom
        assert "<script" not in page and "<link" not in page and "@import" not in page and "url(" not in page, nom
        assert "<img" not in page and "<iframe" not in page and "fetch(" not in page, nom
        for lien in re.findall(r'(?:href|src)="([^"]+)"', page):
            assert (dossier / lien).exists(), (nom, lien)  # chaque lien mène à une page du dossier


def test_le_dossier_ne_contient_que_la_seance_sans_chemin_de_nos_ordinateurs(rejeu):
    dossier, _ = rejeu
    noms = sorted(f.name for f in dossier.iterdir())
    assert all(re.fullmatch(r"index\.html|moment_\d+\.html|LISEZ_MOI\.txt", n) for n in noms), noms
    assert not any(f.is_dir() for f in dossier.iterdir())
    interdits = [str(RACINE), str(Path.home()), "/Users/", "/private/", "/var/folders", "/tmp/", "C:\\\\", ".venv", "site-packages"]
    for f in dossier.iterdir():
        texte = f.read_text(encoding="utf-8")
        for mot in interdits:
            assert mot not in texte, (f.name, mot)
        assert rejeu_autonome.verifier(dossier) == [], rejeu_autonome.verifier(dossier)


def test_la_verification_trouve_un_chemin_ou_un_lien_glisse_expres(rejeu, tmp_path):
    dossier, _ = rejeu
    copie = tmp_path / "copie"
    copie.mkdir()
    for f in dossier.iterdir():
        (copie / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (copie / "index.html").write_text((copie / "index.html").read_text(encoding="utf-8")
                                      + f"<p>{RACINE}/journal</p><script src='https://exemple.invalid/x.js'></script>",
                                      encoding="utf-8")
    (copie / "notes.json").write_text("{}", encoding="utf-8")
    trouve = " ; ".join(rejeu_autonome.verifier(copie))
    assert "chemin" in trouve and "extérieur" in trouve and "notes.json" in trouve


def test_un_chemin_de_l_ordinateur_est_retire_avant_d_ecrire():
    texte = f"erreur dans {RACINE}/briques/clinique/x.py et {Path.home()}/Desktop, puis /private/var/folders/ab/T/tmp1"
    propre = rejeu_autonome.nettoyer(texte)
    assert str(RACINE) not in propre and str(Path.home()) not in propre and "/private/" not in propre
    assert "[chemin retiré]" in propre and "erreur dans" in propre


def test_le_mode_d_emploi_tient_en_trois_lignes(rejeu):
    dossier, _ = rejeu
    lignes = [l for l in (dossier / "LISEZ_MOI.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lignes) <= 3 and any("index.html" in l for l in lignes) and any("double" in l for l in lignes)
    assert "à part" in (dossier / "index.html").read_text(encoding="utf-8")  # « ne le mettez pas en ligne », dit sur la page


def test_l_enregistrement_ne_change_rien_apres_lui():
    from briques.clinique.carnet import Carnet
    from commun.bus import Bus

    avant = (Bus.publier, Carnet.ecrire)
    with rejeu_autonome.enregistrer() as entrees:
        assert (Bus.publier, Carnet.ecrire) != avant
    assert (Bus.publier, Carnet.ecrire) == avant and isinstance(entrees, list)


def test_par_defaut_le_dossier_va_dans_le_journal_qui_ne_part_jamais_vers_github():
    assert RACINE / "journal" in rejeu_autonome.DOSSIER_DEFAUT.parents
    sortie = subprocess.run(["git", "check-ignore", str(rejeu_autonome.DOSSIER_DEFAUT / "x" / "index.html")], cwd=RACINE,
                            capture_output=True, text=True)
    assert sortie.returncode == 0, sortie


def test_la_commande_est_dans_lancer():
    import lancer

    assert "rejeu-autonome" in lancer.__doc__
