"""H19a — Dessiner un code QR pour chaque écran de la page des téléphones (réponse de Hiba à Q29 : A ; « oui » à Q30).

Le module « segno » 1.6.6 (licence BSD, lue dans son fichier LICENSE) dessine les codes. Pour ne pas croire segno sur
parole, chaque code est relu par le Mac lui-même (CoreImage, par `outils/lire_code_qr.swift`) : le texte relu doit être
l'adresse exacte. Le dessin montré (SVG) et l'image relue (PNG) viennent du même code.
Pas encore branché sur la page des téléphones : un essai établi y demande « Codes QR : pas encore » (question Q35).
Pas essayé avec un vrai téléphone.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from briques.clinique import codes_qr

AVEC_SEGNO = pytest.mark.skipif(not codes_qr.disponible(), reason="segno n'est pas installé sur cette machine")
RACINE = Path(__file__).resolve().parents[3]
LECTEUR = RACINE / "outils" / "lire_code_qr.swift"
ADRESSES = ["http://192.168.1.43:8000/clinique/invite", "http://192.168.1.43:8000/clinique/soignant",
            "http://10.0.0.7:8123/clinique/avis/donner",
            "http://AUTRE/"]  # très court : segno ferait un « micro code QR » si on le laissait choisir


def _relire(png: Path) -> list[str]:
    essai = subprocess.run(["swift", "--version"], capture_output=True, text=True) if shutil.which("swift") else None
    if essai is None or essai.returncode != 0:  # sur un Mac sans les outils d'Apple, /usr/bin/swift existe mais ne marche pas
        pytest.skip("pas de swift qui marche sur cette machine : le code ne peut pas être relu")
    sortie = subprocess.run(["swift", str(LECTEUR), str(png)], capture_output=True, text=True, timeout=120)
    assert sortie.returncode == 0, sortie.stderr
    return [l for l in sortie.stdout.splitlines() if l]


@AVEC_SEGNO
def test_segno_est_la_version_acceptee():
    import segno

    assert segno.__version__ == "1.6.6"


@AVEC_SEGNO
@pytest.mark.parametrize("adresse", ADRESSES)
def test_le_mac_relit_exactement_l_adresse_dans_le_code(tmp_path, adresse):
    png = tmp_path / "code.png"
    codes_qr.enregistrer_png(adresse, png)
    assert _relire(png) == [adresse]


@AVEC_SEGNO
def test_le_dessin_est_un_svg_sur_place_avec_un_texte_pour_les_lecteurs_d_ecran():
    svg = codes_qr.dessin_svg(ADRESSES[0])
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "<script" not in svg.lower()
    assert f"Code QR : {ADRESSES[0]}" in svg  # role='img' + aria-label : ce que lit un lecteur d'écran


@AVEC_SEGNO
def test_toujours_un_code_qr_normal_jamais_un_micro_code():
    for adresse in ADRESSES:
        assert codes_qr.fabriquer(adresse).is_micro is False, adresse


@AVEC_SEGNO
def test_le_svg_montre_est_fait_du_meme_code_que_le_png_relu():
    code = codes_qr.fabriquer(ADRESSES[1])  # dessin_svg et enregistrer_png passent tous deux par fabriquer()
    assert codes_qr.fabriquer(ADRESSES[1]).matrix == code.matrix  # le même texte donne toujours le même code
    attendu = code.svg_inline(scale=5, dark="#000", light="#fff", omitsize=False)
    assert codes_qr.dessin_svg(ADRESSES[1]).split(">", 1)[1] == attendu.split(">", 1)[1]  # mêmes points, seule l'étiquette change
    assert code.error in ("M", "Q", "H")  # correction d'erreur au moins « M » : un écran un peu sale se lit encore


@AVEC_SEGNO
def test_une_marge_blanche_de_quatre_points_autour_du_code():
    # Le lecteur du Mac relit même un code sans marge ; un téléphone, pas toujours : on vérifie la marge à part.
    code = codes_qr.fabriquer(ADRESSES[0])
    assert code.default_border_size >= 4
    assert "#fff" in codes_qr.dessin_svg(ADRESSES[0])  # le fond blanc est dessiné : une page sombre ne gêne pas


@AVEC_SEGNO
def test_une_adresse_avec_des_caracteres_html_ne_casse_pas_le_dessin():
    svg = codes_qr.dessin_svg("http://x/<b>\"'")
    assert "<b>" not in svg and "&lt;b&gt;" in svg


def test_sans_segno_le_programme_le_dit_au_lieu_de_planter(monkeypatch):
    monkeypatch.setattr(codes_qr, "_segno", lambda: None)
    assert codes_qr.disponible() is False and codes_qr.dessin_svg(ADRESSES[0]) is None
