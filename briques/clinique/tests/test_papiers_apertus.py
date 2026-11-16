"""La clinique en boîte — H06a, le rangement des papiers refait avec le vrai Apertus (demande de Hiba, 12.11).

« Fini » veut dire :
- le vrai Apertus se branche sur la porte du rangement déjà écrite (`lire(texte, types, patients)`, T14), avec un
  formulaire imposé ; sa proposition est toujours vérifiée contre le papier par les règles de T14, inchangées ;
- la mesure passe tous les papiers du faux dossier, lus par la porte, et compte : « bien rangé et sûr », « je ne suis
  pas sûr » (un humain choisit), « mal rangé et dit sûr » (le cas grave), et ce que le modèle seul a répondu ;
- le temps de chaque réponse est noté, et les réponses de plus de cinq secondes sont listées ;
- les chiffres viennent des réponses : rien n'est tapé ; sans modèle, « PAS POSSIBLE » et aucun chiffre.
Ces essais prennent un cerveau de test : aucun modèle. L'essai avec le vrai Apertus saute si le serveur ne tourne pas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from briques.clinique import papiers_apertus
from briques.clinique.papiers import CerveauDeTest


def _parfait(vrais):
    """Un cerveau de test qui répond juste : le vrai type, le vrai patient, confiance haute."""
    def repondre(texte):
        genre, nom = vrais[texte]
        return {"type": genre, "date": None, "auteur": None, "patient": nom, "confiance": "haute"}

    return repondre


def _vrais():
    return {p["texte"]: (p["vrai_type"], p["vrai_nom"]) for p in papiers_apertus.papiers_du_faux_dossier()}


def test_la_mesure_passe_tous_les_papiers_du_faux_dossier_lus_par_la_porte():
    papiers = papiers_apertus.papiers_du_faux_dossier()
    assert len(papiers) >= 6 and len({p["id"] for p in papiers}) == len(papiers)
    assert any(p["vrai_patient"] is None for p in papiers)  # la feuille sans nom : elle doit rester « à trier »
    assert all(p["texte"].startswith("INVENTÉ") for p in papiers)


def test_un_cerveau_juste_tous_les_papiers_tapes_sont_bien_ranges_et_la_feuille_sans_nom_attend():
    r = papiers_apertus.mesurer(CerveauDeTest(_parfait(_vrais())), montre=iter(range(0, 100_000)).__next__)
    assert r["possible"] is True and r["papiers"] == len(papiers_apertus.papiers_du_faux_dossier())
    assert r["mal_ranges_dits_surs"] == 0
    assert r["bien_ranges_surs"] + r["pas_surs"] == r["papiers"]
    assert r["modele_seul_type_juste"] == r["papiers_avec_un_type"]
    sans_nom = next(l for l in r["detail"] if l["vrai_patient"] is None)
    assert sans_nom["patient"] is None and sans_nom["issue"] == "pas sûr"
    a_la_main = [l for l in r["detail"] if l["ecriture"] != "tapée"]
    assert all(l["issue"] == "pas sûr" for l in a_la_main)  # jamais sûr pour une écriture à la main, même si le cerveau le dit


def test_un_cerveau_qui_se_trompe_de_type_n_est_jamais_dit_sur():
    def faux(texte):
        return {"type": "rapport de radiologie", "date": "1 janvier 1900", "auteur": "Dr Inventé", "patient": "Madame Giulia B.",
                "confiance": "haute"}

    r = papiers_apertus.mesurer(CerveauDeTest(faux), montre=iter(range(0, 100_000)).__next__)
    assert r["mal_ranges_dits_surs"] == 0  # les règles de T14 ne sont pas d'accord : « je ne suis pas sûr »
    assert r["modele_seul_type_juste"] < r["papiers_avec_un_type"]
    assert all(l["date"] != "1 janvier 1900" and l["auteur"] != "Dr Inventé" for l in r["detail"])


def test_une_date_qui_n_est_pas_une_date_est_retiree_meme_si_elle_est_ecrite_sur_le_papier():
    """Vu avec le vrai Apertus le 12.11 : « Neuf séances. » dans la date d'une ordonnance, et le papier était dit sûr."""
    from briques.clinique.papiers import proposer_avec_cerveau

    papier = next(p for p in papiers_apertus.papiers_du_faux_dossier() if p["id"] == "p03-d1")
    assert "Neuf séances." in papier["texte"]
    for date, garde in (("Neuf séances.", False), ("INVENTÉ", False)):
        cerveau = CerveauDeTest(lambda texte, date=date: {"type": papier["vrai_type"], "date": date, "auteur": None,
                                                         "patient": papier["vrai_nom"], "confiance": "haute"})
        p = proposer_avec_cerveau(papier["texte"], "tapée", papier["attendus"], cerveau)
        assert p["date"] is None and p["confiance"] == "basse" and any("pas une date" in r for r in p["raisons"])


def test_le_temps_de_chaque_reponse_est_note_et_les_lentes_sont_listees():
    temps = iter([0, 1.0, 10, 16.5] + [20 + i * 0.001 for i in range(1000)])  # 1re réponse : 1 s ; 2e : 6,5 s ; puis vite
    r = papiers_apertus.mesurer(CerveauDeTest(_parfait(_vrais())), montre=temps.__next__)
    assert r["detail"][0]["ms"] == 1000 and r["detail"][1]["ms"] == 6500
    assert [l["id"] for l in r["plus_de_5_s"]] == [r["detail"][1]["id"]]
    texte = "\n".join(papiers_apertus.rapport(r))
    assert "1 réponse de plus de 5 secondes" in texte and r["detail"][1]["id"] in texte


def test_un_cerveau_en_panne_compte_comme_pas_de_reponse_et_les_regles_rangent():
    r = papiers_apertus.mesurer(CerveauDeTest(lambda texte: 1 / 0), montre=iter(range(0, 100_000)).__next__)
    assert r["sans_reponse"] == r["papiers"] and r["mal_ranges_dits_surs"] == 0
    assert "n'a pas répondu" in "\n".join(papiers_apertus.rapport(r))


def test_le_compte_rendu_dit_vrai_et_sans_modele_il_ne_donne_aucun_chiffre():
    r = papiers_apertus.mesurer(CerveauDeTest(_parfait(_vrais())), montre=iter(range(0, 100_000)).__next__)
    lignes = papiers_apertus.rapport(r)
    assert "DONNÉES INVENTÉES" in lignes[0] and re.search(r"\d\d\.\d\d\.\d{4}", lignes[0])
    assert "cerveau de test" in lignes[0] and "RÉEL" not in lignes[0]  # un cerveau de test ne s'appelle jamais « réel »
    vide = papiers_apertus.rapport({"possible": False, "raison": "essai", "quand": "2026-11-12T12:00:00+01:00"})
    assert vide[0].startswith("RANGEMENT PAR APERTUS : PAS POSSIBLE") and not any(c.isdigit() for l in vide[1:] for c in l)
    assert '"papiers-apertus"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")


def test_avec_le_vrai_apertus_si_le_serveur_tourne():
    """Le vrai Apertus 8B, s'il tourne (python3 lancer.py cerveau). Sinon : sauté."""
    import httpx

    try:
        httpx.get(papiers_apertus.URL + "/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur Apertus 8B en marche (python3 lancer.py cerveau)")
    r = papiers_apertus.mesurer(papiers_apertus.ApertusDesPapiers())
    assert r["possible"] is True and r["mal_ranges_dits_surs"] == 0
