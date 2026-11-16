"""La clinique en boîte — T13, le résumé écrit par Apertus (cahier 5.7).

« Fini » veut dire :
- un cerveau écrit les lignes du résumé, à partir des seules sources que les règles ont choisies pour cette ligne ;
- sources obligatoires : une phrase sans source, ou avec une source qui n'est pas dans la liste, est retirée ;
- le verrou des chiffres : un chiffre qui n'est pas dans la source citée fait retirer la phrase ;
- une phrase qui raconte autre chose que ses sources est retirée ;
- « je ne suis pas sûr » : si le cerveau le dit, ou si une phrase est retirée, la ligne revient à la version simple,
  et l'écran le dit ;
- les questions de la patiente et un désaccord entre deux sources ne sont jamais réécrits par le cerveau ;
- cerveau en panne, hors formulaire ou trop lent : tout le résumé revient à la version simple, et l'écran le dit ;
- sans cerveau branché, rien ne change.
Ces essais prennent un cerveau de test à réponses fixes : aucun modèle. L'essai avec le vrai Apertus est à la fin ;
il saute si le serveur ne tourne pas.
"""
from __future__ import annotations

import pytest

from briques.clinique import resume_apertus
from briques.clinique.resume import RIEN, VERSION
from briques.clinique.tests.test_resume_medecin import MEDECIN, _client, _ligne, _pieces


def _avec(repondre, **kw):
    resume, badges, carnet, porte, horloge = _pieces(**kw)
    vus: list[tuple[str, dict[str, str]]] = []

    def noter(titre, sources):
        vus.append((titre, dict(sources)))
        return repondre(titre, sources)

    resume.cerveau = resume_apertus.CerveauDeTest(noter)
    return resume, badges[MEDECIN], carnet, vus


SAGES = {"Pourquoi il est là": "Raison du séjour : réadaptation après une opération de la hanche, pour 18 jours ; sortie prévue le jour 19.",
         "Ce qui a changé depuis hier": "Arrivée le jour 1 à 09:00 ; chambre 12.",
         "Prévu aujourd'hui": "10:00 installation en chambre (Chambre 12), 11:00 physiothérapie (Salle 2), 14:00 bain accompagné (Bassin)."}


def _recopie(titre, sources):
    """Un cerveau sage, pour Madame B. (p01) : les faits de la version simple, écrits autrement, avec la source."""
    return {"sur": True, "phrases": [{"texte": SAGES.get(titre, "?"), "sources": list(sources)[:1]}]}


def test_sans_cerveau_rien_ne_change():
    resume, badges, *_ = _pieces()
    r = resume.resume(badges[MEDECIN], "p01")
    assert r["version"] == VERSION and not any(l.get("ecrit_par") for l in r["lignes"])


def test_le_cerveau_ecrit_les_lignes_et_chaque_phrase_garde_sa_source():
    resume, badge, carnet, vus = _avec(_recopie)
    r = resume.resume(badge, "p01")
    pourquoi = _ligne(r, "pourquoi")
    assert pourquoi["ecrit_par"] == "cerveau" and pourquoi["texte"] == SAGES["Pourquoi il est là"]
    assert [s["ref"] for s in pourquoi["sources"]] == ["sejour"]
    assert "cerveau de test" in r["version"] and "vérifié" in r["version"]
    assert isinstance(r["temps_cerveau_ms"], int)
    # le cerveau n'a reçu, pour cette ligne, que les sources choisies par les règles
    assert next(sources for titre, sources in vus if titre == pourquoi["titre"]).keys() == {"sejour"}
    # le carnet garde la version et le texte tels qu'affichés
    ligne = [l for l in carnet.lignes() if l["genre"] == "résumé du médecin"][-1]
    assert ligne["donnees"]["version"] == r["version"]


def test_une_phrase_sans_source_ou_avec_une_source_inconnue_fait_revenir_la_ligne_a_la_version_simple():
    simple = _pieces()[0]
    attendu = _ligne(simple.resume(_pieces()[1][MEDECIN], "p01"), "pourquoi")["texte"]
    for sources in ([], ["p99-d9"], ["programme"]):  # rien ; inconnue ; pas donnée pour cette ligne
        def repondre(titre, donnees, sources=sources):
            if titre == "Pourquoi il est là":
                return {"sur": True, "phrases": [{"texte": "Séjour de rééducation.", "sources": sources}]}
            return _recopie(titre, donnees)

        resume, badge, _, _ = _avec(repondre)
        r = resume.resume(badge, "p01")
        ligne = _ligne(r, "pourquoi")
        assert ligne["texte"] == attendu and ligne["ecrit_par"] == "règles simples"
        assert "je ne suis pas sûr" in ligne["pas_sur"] and "source" in ligne["pas_sur"]
        assert len(r["ecartees_du_cerveau"]) >= 1 and r["retirees"] == 0  # écartée, pas « retirée faute de source »


def test_le_verrou_des_chiffres_un_chiffre_invente_fait_retirer_la_phrase():
    def repondre(titre, sources):
        if titre == "Pourquoi il est là":
            return {"sur": True, "phrases": [{"texte": "Séjour de 81 jours.", "sources": ["sejour"]}]}
        return _recopie(titre, sources)

    resume, badge, _, _ = _avec(repondre)
    r = resume.resume(badge, "p01")
    ligne = _ligne(r, "pourquoi")
    assert "81" not in ligne["texte"] and ligne["ecrit_par"] == "règles simples" and "chiffre" in ligne["pas_sur"]
    assert any("81" in d["texte"] for d in r["ecartees_du_cerveau"])


def test_une_phrase_qui_raconte_autre_chose_que_ses_sources_est_retiree():
    def repondre(titre, sources):
        if titre == "Pourquoi il est là":
            return {"sur": True, "phrases": [{"texte": "La patiente souffre probablement d'une infection grave et inquiétante.",
                                             "sources": ["sejour"]}]}
        return _recopie(titre, sources)

    resume, badge, _, _ = _avec(repondre)
    ligne = _ligne(resume.resume(badge, "p01"), "pourquoi")
    assert "infection" not in ligne["texte"] and "mots" in ligne["pas_sur"]


@pytest.mark.parametrize("texte, mot", [("Prévu aujourd'hui", "répète le titre"), ("Physiothérapie à 11:00 en Salle 2.", "il manque un chiffre"),
                                        ("Jour 1, 10:00 : installation en chambre (Chambre 12) ; 11:00 physiothérapie (Salle 2) ; 14:00 bain accompagné "
                                         "(Bassin).", "n'est pas dans la version simple")])  # « Jour 1 » : vrai, mais les règles ne l'ont pas choisi
def test_une_ligne_qui_repete_son_titre_ou_perd_un_chiffre_revient_a_la_version_simple(texte, mot):
    """Vu avec le vrai Apertus le 12.11 : il écrivait « Prévu aujourd'hui » à la place du programme, et la ligne passait."""
    def repondre(titre, sources):
        if titre == "Prévu aujourd'hui":
            return {"sur": True, "phrases": [{"texte": texte, "sources": ["programme"]}]}
        return _recopie(titre, sources)

    resume, badge, _, _ = _avec(repondre)
    ligne = _ligne(resume.resume(badge, "p01"), "aujourdhui")
    assert "10:00 installation en chambre" in ligne["texte"] and "14:00" in ligne["texte"]
    assert ligne["ecrit_par"] == "règles simples" and mot in ligne["pas_sur"]


def test_je_ne_suis_pas_sur_la_ligne_revient_a_la_version_simple():
    def repondre(titre, sources):
        return {"sur": False, "phrases": []} if titre == "Prévu aujourd'hui" else _recopie(titre, sources)

    resume, badge, _, _ = _avec(repondre)
    r = resume.resume(badge, "p01")
    ligne = _ligne(r, "aujourdhui")
    assert ligne["ecrit_par"] == "règles simples" and "le cerveau dit qu'il n'est pas sûr" in ligne["pas_sur"]
    assert _ligne(r, "pourquoi")["ecrit_par"] == "cerveau"  # les autres lignes restent écrites par le cerveau


def test_les_questions_un_desaccord_et_rien_de_nouveau_ne_passent_jamais_par_le_cerveau():
    resume, badge, carnet, vus = _avec(_recopie)
    carnet.ecrire(badge, "question du soir", {"patient": "p07", "texte": "Quando torno a casa?", "langue": "it"},
                  valide_par_un_humain=False)
    r = resume.resume(badge, "p07")
    titres = {titre for titre, _ in vus}
    assert "Ses questions" not in titres and "Ce qui attend une décision" not in titres
    assert "Quando torno a casa?" in _ligne(r, "questions")["texte"]
    assert _ligne(r, "decision")["desaccord"] and "ne choisit pas" in _ligne(r, "decision")["texte"]
    cinq = resume.resume(badge, "p05")
    assert any(l["texte"] == RIEN and not l.get("ecrit_par") for l in cinq["lignes"])


@pytest.mark.parametrize("panne, mot", [("casse", "RuntimeError"), ("formulaire", "hors formulaire"), ("lent", "trop long")])
def test_cerveau_en_panne_hors_formulaire_ou_trop_lent_tout_revient_a_la_version_simple(panne, mot):
    def repondre(titre, sources):
        if panne == "casse":
            raise RuntimeError("éteint")
        return "n'importe quoi" if panne == "formulaire" else _recopie(titre, sources)

    resume, badge, _, _ = _avec(repondre)
    if panne == "lent":
        temps = iter(range(0, 10_000, 40))  # chaque regard à la montre : 40 secondes de plus
        resume.montre = lambda: next(temps)
    r = resume.resume(badge, "p01")
    simple = _pieces()[0].resume(_pieces()[1][MEDECIN], "p01")
    assert [l["texte"] for l in r["lignes"]] == [l["texte"] for l in simple["lignes"]]
    assert r["version"].startswith("règles simples") and mot in r["version"] and "n'a pas" in r["version"]
    assert not any(l.get("ecrit_par") == "cerveau" for l in r["lignes"])


def test_l_ecran_dit_la_version_et_la_ligne_pas_sure():
    client, clinique = _client()

    def repondre(titre, sources):
        return {"sur": False, "phrases": []} if titre == "Prévu aujourd'hui" else _recopie(titre, sources)

    clinique.resume.cerveau = resume_apertus.CerveauDeTest(repondre)
    page = client.get(f"/clinique/medecin?badge={MEDECIN}").text
    assert "cerveau de test" in page and "je ne suis pas sûr" in page and "version simple pour cette ligne" in page
    clinique.resume.cerveau = resume_apertus.CerveauDeTest(lambda *a: 1 / 0)
    clinique.resume._prets.clear()
    page = client.get(f"/clinique/medecin?badge={MEDECIN}").text
    assert "règles simples (le cerveau n&#x27;a pas répondu" in page or "règles simples (le cerveau n'a pas répondu" in page


def test_la_commande_est_dans_lancer_et_sans_serveur_elle_ne_donne_aucun_chiffre(capsys):
    from pathlib import Path

    assert '"resume-apertus"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    lignes = resume_apertus.rapport({"possible": False, "raison": "essai", "quand": "2026-11-12T12:00:00+01:00"})
    assert lignes[0].startswith("RÉSUMÉ PAR APERTUS : PAS POSSIBLE") and not any(c.isdigit() for l in lignes[1:] for c in l)


def test_avec_le_vrai_apertus_si_le_serveur_tourne():
    """Le vrai Apertus 8B, s'il tourne (python3 lancer.py cerveau). Sinon : sauté. Rien d'inventé ne doit rester."""
    import httpx

    from briques.clinique.resume import garder_les_phrases_sures

    try:
        httpx.get(resume_apertus.URL + "/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur Apertus 8B en marche (python3 lancer.py cerveau)")
    resume, badges, *_ = _pieces()
    resume.cerveau = resume_apertus.ApertusDuResume()
    r = resume.resume(badges[MEDECIN], "p01")
    simple = _pieces()[0].resume(_pieces()[1][MEDECIN], "p01")
    textes = {ref: s["texte"] for ref, s in resume._sources(resume.porte.patient(badges[MEDECIN], "p01")).items()}
    # le modèle a vraiment répondu, dans le formulaire (sinon la version dirait « règles simples (le cerveau n'a pas… »)
    assert r["version"].startswith("écrit par Apertus 8B pour "), r["version"]
    assert len(r["temps_par_ligne_ms"]) == 3 and all(ms > 0 for ms in r["temps_par_ligne_ms"])  # trois lignes confiées pour p01
    for ligne, de_la_simple in zip(r["lignes"], simple["lignes"]):
        if ligne.get("ecrit_par") == "cerveau":
            assert garder_les_phrases_sures(ligne["phrases"], textes) == ligne["phrases"]
        else:  # tout ce qui n'est pas gardé du cerveau est, mot pour mot, la version simple
            assert ligne["texte"] == de_la_simple["texte"]
