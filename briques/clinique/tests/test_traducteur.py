"""La clinique en boîte — L03a, le traducteur : lire les messages, tenir la vue administrative (avenant 4, L03 ; première moitié).

L03 est coupée en deux. Ici, L03a : le traducteur seul. « Fini » veut dire :
- une personne en attente, admise dans le faux logiciel, est dans la vue en moins de dix secondes, avec sa chambre ;
- une pré-admission seule : la personne est « attendue », sans chambre ;
- son changement de chambre se voit ; la correction de sa langue se voit ; sa sortie la retire des présents ;
  l'annulation de la sortie la remet ; le congé et le retour se voient ; une annulation d'admission défait l'admission ;
- le même message lu deux fois ne change rien ; deux messages inversés donnent le bon état ;
- un message abîmé va dans « messages à trier » et rien ne s'arrête ; une ligne inconnue est ignorée ;
- un message qui porte le nom de notre système ne compte pas comme une nouveauté ;
- sans aucun message, la vue est vide ; chaque message lu est noté pour la boîte noire, avec SIMULÉ.
L03b fera : la porte de lecture donne cette vue, l'accueil du hall et les écrans s'en servent.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from briques.clinique import traducteur
from commun.bus import Bus
from conftest import lancer
from faux_logiciel_admin import logiciel


@pytest.fixture
def banc(tmp_path):
    heure = {"jour": 1, "heure": "09:10"}
    faux = logiciel.FauxLogiciel(dossier=tmp_path / "faux", heure=lambda: dict(heure))
    lecteur = traducteur.Traducteur(tmp_path / "faux" / logiciel.VERS_NOUS)
    return faux, lecteur, heure


def _personne(lecteur, numero="p13"):
    return next((p for p in lecteur.vue() if p["numero_patient"] == numero), None)


def _a(heure, hhmm):
    heure["heure"] = hhmm


# ---------------------------------------------------------------------------------------------- la vue se tient à jour
def test_sans_aucun_message_la_vue_est_vide(banc):
    _, lecteur, _ = banc
    assert lecteur.lire() == {"lus": 0, "a_trier": 0, "deja_lus": 0, "de_nous": 0}
    assert lecteur.vue() == [] and lecteur.a_trier() == [] and lecteur.derniere_nouvelle() is None
    assert lecteur.compte()["texte"] == "logiciel administratif : SIMULÉ ; messages lus : 0 ; messages à trier : 0"


def test_une_personne_admise_est_dans_la_vue_en_moins_de_dix_secondes_avec_sa_chambre(banc):
    faux, lecteur, _ = banc
    faux.evenement("A01", "p13", chambre="11")
    assert lecteur.lire()["lus"] == 1
    p = _personne(lecteur)
    assert p["etat"] == "présent" and p["chambre"] == "11" and p["numero_sejour"] == "s13"
    assert p["prenom"] == "Paolo" and p["nom"] == "Monsieur Paolo V." and p["langue"] == "it"
    assert p["entree"] == {"date": "2026-11-14", "jour": 1, "heure": "09:00"}
    assert 0 <= lecteur.dernier_delai_s() < 10
    assert lecteur.derniere_nouvelle()["heure"] == "09:10" and lecteur.derniere_nouvelle()["jour"] == 1
    assert set(p) == {"numero_patient", "numero_sejour", "nom", "prenom", "langue", "date_naissance", "chambre", "etat",
                      "entree", "sortie", "assurance", "source"} and p["source"] == "ADMIN"  # que de l'administratif


def test_une_pre_admission_seule_la_personne_est_attendue_sans_chambre(banc):
    faux, lecteur, _ = banc
    faux.evenement("A05", "p13")
    lecteur.lire()
    p = _personne(lecteur)
    assert p["etat"] == "attendu" and p["chambre"] == "" and p["entree"] is None
    assert lecteur.presents() == []


def test_toute_la_vie_d_un_sejour_se_voit(banc):
    faux, lecteur, heure = banc
    etapes = [("A05", {}, "09:10", "attendu", ""), ("A01", {"chambre": "11"}, "09:20", "présent", "11"),
              ("A02", {"chambre": "13"}, "09:30", "présent", "13"), ("A21", {}, "09:40", "en congé", "13"),
              ("A22", {}, "09:50", "présent", "13"), ("A03", {}, "10:00", "sorti", "13"), ("A13", {}, "10:10", "présent", "13")]
    for sorte, plus, hhmm, etat, chambre in etapes:
        _a(heure, hhmm)
        faux.evenement(sorte, "p13", **plus)
        lecteur.lire()
        p = _personne(lecteur)
        assert (p["etat"], p["chambre"]) == (etat, chambre), sorte
        assert (p in lecteur.presents()) == (etat == "présent"), sorte  # la sortie la retire des présents ; l'annulation la remet
    assert _personne(lecteur)["sortie"] is None  # la sortie annulée n'est plus là


def test_la_correction_de_la_langue_se_voit(banc):
    faux, lecteur, heure = banc
    faux.evenement("A01", "p13", chambre="11")
    _a(heure, "09:20")
    faux.evenement("A08", "p13", champ="langue", valeur="de")
    lecteur.lire()
    assert _personne(lecteur)["langue"] == "de" and _personne(lecteur)["chambre"] == "11"


def test_une_annulation_d_admission_defait_l_admission(banc):
    faux, lecteur, heure = banc
    faux.evenement("A05", "p13")
    _a(heure, "09:20")
    faux.evenement("A01", "p13", chambre="12")
    _a(heure, "09:30")
    faux.evenement("A11", "p13")
    faux.evenement("A01", "p14", chambre="14")  # une admission sans pré-admission…
    _a(heure, "09:40")
    faux.evenement("A11", "p14")                # …annulée : la personne n'est plus attendue du tout
    lecteur.lire()
    assert _personne(lecteur, "p13")["etat"] == "attendu" and _personne(lecteur, "p13")["chambre"] == ""
    assert _personne(lecteur, "p14") is None


# ---------------------------------------------------------------------------------------------- les sept règles de lecture
def test_le_meme_message_lu_deux_fois_ne_change_rien(banc):
    faux, lecteur, _ = banc
    message = faux.evenement("A01", "p13", chambre="11")
    lecteur.lire()
    avant = lecteur.vue()
    assert lecteur.lire() == {"lus": 0, "a_trier": 0, "deja_lus": 0, "de_nous": 0}  # relire le dossier : rien de neuf
    copie = Path(message["fichier"]).with_name("9999_copie_du_meme.hl7")
    shutil.copy(message["fichier"], copie)  # le même message, arrivé une deuxième fois dans un autre fichier
    assert lecteur.lire() == {"lus": 0, "a_trier": 0, "deja_lus": 1, "de_nous": 0}
    assert lecteur.vue() == avant and lecteur.compte()["lus"] == 1


def test_deux_messages_inverses_donnent_le_bon_etat(banc, tmp_path):
    faux, lecteur, heure = banc
    admission = Path(faux.evenement("A01", "p13", chambre="11")["fichier"])
    _a(heure, "09:30")
    changement = Path(faux.evenement("A02", "p13", chambre="13")["fichier"])
    # le changement de chambre arrive le premier ; l'admission, plus vieille, arrive après
    cote = tmp_path / "plus_tard.hl7"
    admission.rename(cote)
    lecteur.lire()
    cote.rename(admission.with_name("9998_arrive_en_retard.hl7"))
    lecteur.lire()
    p = _personne(lecteur)
    assert p["etat"] == "présent" and p["chambre"] == "13"  # remis en ordre par l'heure : la chambre 13 est la dernière


def test_a_la_meme_heure_le_numero_du_message_met_en_ordre(banc):
    faux, lecteur, _ = banc
    faux.evenement("A01", "p13", chambre="11")
    faux.evenement("A02", "p13", chambre="14")  # la même minute
    faux.evenement("A02", "p13", chambre="12")
    lecteur.lire()
    assert _personne(lecteur)["chambre"] == "12"


def test_un_message_abime_va_dans_messages_a_trier_et_rien_ne_s_arrete(banc):
    faux, lecteur, _ = banc
    dossier = lecteur.dossier
    dossier.mkdir(parents=True)
    (dossier / "0000_abime.hl7").write_text("ceci n'est pas un message\n", encoding="utf-8")
    (dossier / "0000_sans_numero.hl7").write_text("MSH|^~\\&|FAUX_LOGICIEL_ADMIN|X|Y|X|202611140900||ADT^A01|ID-1|P|2.5\n"
                                                  "EVN|A01|202611140900\nPID|1||||V.^Paolo\nPV1|1|I\n", encoding="utf-8")
    (dossier / "0000_sorte_inconnue.hl7").write_text("MSH|^~\\&|FAUX_LOGICIEL_ADMIN|X|Y|X|202611140900||ADT^A99|ID-2|P|2.5\n"
                                                     "EVN|A99|202611140900\nPID|1||p13^^^X||V.^Paolo\nPV1|1|I||||||||||||||||||s13\n",
                                                     encoding="utf-8")
    (dossier / "0000_octets.hl7").write_bytes(b"\xff\xfe\x00MSH")
    faux.evenement("A01", "p13", chambre="11")
    assert lecteur.lire() == {"lus": 1, "a_trier": 4, "deja_lus": 0, "de_nous": 0}
    assert _personne(lecteur)["chambre"] == "11"  # le bon message est lu quand même
    a_trier = lecteur.a_trier()
    assert [m["fichier"] for m in a_trier] == ["0000_abime.hl7", "0000_octets.hl7", "0000_sans_numero.hl7", "0000_sorte_inconnue.hl7"]
    assert all(m["heure"] and m["raison"] for m in a_trier)
    assert "numéro du patient" in a_trier[2]["raison"] and "A99" in a_trier[3]["raison"]
    assert lecteur.lire()["a_trier"] == 0  # un message à trier n'est pas recompté à chaque lecture


def test_une_ligne_inconnue_est_ignoree(banc):
    faux, lecteur, _ = banc
    fichier = Path(faux.evenement("A01", "p13", chambre="11")["fichier"])
    fichier.write_text(fichier.read_text(encoding="utf-8") + "ZZZ|une ligne que nous ne connaissons pas|1|2\nNK1|1|quelqu'un\n",
                       encoding="utf-8")
    assert lecteur.lire() == {"lus": 1, "a_trier": 0, "deja_lus": 0, "de_nous": 0}
    assert _personne(lecteur)["chambre"] == "11"


def test_les_fins_de_ligne_du_standard_sont_lues_aussi(banc):
    faux, lecteur, _ = banc
    fichier = Path(faux.evenement("A01", "p13", chambre="11")["fichier"])
    fichier.write_bytes(fichier.read_text(encoding="utf-8").replace("\n", "\r").encode("utf-8"))  # « retour chariot »
    assert lecteur.lire()["lus"] == 1 and _personne(lecteur)["chambre"] == "11"


def test_un_message_qui_porte_le_nom_de_notre_systeme_n_est_pas_une_nouveaute(banc):
    faux, lecteur, _ = banc
    fichier = Path(faux.evenement("A01", "p13", chambre="11")["fichier"])
    fichier.write_text(fichier.read_text(encoding="utf-8").replace("|FAUX_LOGICIEL_ADMIN|", f"|{traducteur.NOTRE_SYSTEME}|", 1),
                       encoding="utf-8")
    assert lecteur.lire() == {"lus": 0, "a_trier": 0, "deja_lus": 0, "de_nous": 1}
    assert lecteur.vue() == [] and lecteur.derniere_nouvelle() is None


def test_un_message_se_relie_par_les_numeros_jamais_par_le_nom(banc):
    faux, lecteur, heure = banc
    faux.evenement("A01", "p13", chambre="11")
    faux.evenement("A01", "p14", chambre="12")
    _a(heure, "09:20")
    faux.evenement("A08", "p14", champ="nom", valeur="Monsieur Paolo V.")  # deux personnes portent maintenant le même nom
    _a(heure, "09:30")
    faux.evenement("A02", "p14", chambre="14")
    lecteur.lire()
    assert _personne(lecteur, "p13")["chambre"] == "11" and _personne(lecteur, "p14")["chambre"] == "14"
    assert _personne(lecteur, "p13")["nom"] == _personne(lecteur, "p14")["nom"] == "Monsieur Paolo V."


# ---------------------------------------------------------------------------------------------- le délai, la boîte noire
def test_le_temps_entre_l_ecriture_et_la_lecture_est_mesure(banc):
    faux, lecteur, _ = banc
    fichier = Path(faux.evenement("A01", "p13", chambre="11")["fichier"])
    il_y_a_trois_secondes = fichier.stat().st_mtime - 3
    os.utime(fichier, (il_y_a_trois_secondes, il_y_a_trois_secondes))
    lecteur.lire()
    assert 3 <= lecteur.dernier_delai_s() < 5
    assert lecteur.texte_du_delai().startswith("dernier message lu en 3") and "SIMULÉ" in lecteur.texte_du_delai()


def test_chaque_message_lu_est_note_dans_la_boite_noire_avec_simule(banc):
    faux, lecteur, _ = banc
    bus = Bus()
    faux.evenement("A01", "p13", chambre="11")
    (lecteur.dossier / "0000_abime.hl7").write_text("rien\n", encoding="utf-8")
    lecteur.lire()
    assert lancer(lecteur.noter_dans_la_boite(bus)) == 2 and lancer(lecteur.noter_dans_la_boite(bus)) == 0
    notes = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "message_lu"]
    assert [(n["issue"], n["etiquette"]) for n in notes] == [("à trier", "SIMULÉ"), ("lu", "SIMULÉ")]
    assert notes[1]["sorte"] == "A01" and notes[1]["numero_patient"] == "p13" and "Paolo" not in str(notes)


def test_le_traducteur_n_ecrit_jamais_dans_le_faux_logiciel(banc):
    faux, lecteur, _ = banc
    faux.evenement("A01", "p13", chambre="11")
    avant = {f.name: f.read_bytes() for f in faux.dossier.rglob("*") if f.is_file()}
    lecteur.lire(), lecteur.vue(), lecteur.a_trier()
    assert {f.name: f.read_bytes() for f in faux.dossier.rglob("*") if f.is_file()} == avant
    source = Path(traducteur.__file__).read_text(encoding="utf-8")
    for interdit in ("write_text", "write_bytes", "open(", "unlink", "rename"):
        assert interdit not in source, interdit
