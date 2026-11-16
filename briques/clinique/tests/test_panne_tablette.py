"""La clinique en boîte — J02b, la panne « le lien tombe entre le cerveau et une tablette » (avenant jury, J02).

« Fini » veut dire :
- pendant la panne, la page de liste déjà ouverte ne reçoit plus rien du cerveau (réponse « lien coupé ») ;
- 1. aucun ordre au robot ne part de la tablette sans lien : la demande est refusée, rien n'est créé, rien ne bouge ;
- 2. la tablette affiche « HORS LIGNE » et dit quoi faire ; les autres écrans disent ce qui se passe, ce que le
     système fait, qui est prévenu ;
- 3. la boîte noire et le carnet notent le début et la fin ;
- 4. rien n'est perdu : la tablette garde ses coches dans une file et les renvoie au retour du lien, avec l'heure où
     elles ont été faites ; les coches d'avant sont toujours là ; une coche renvoyée deux fois ne compte pas double ;
- la file de la tablette (du JavaScript) est essayée pour de vrai, avec Node s'il est là.
La panne est SIMULÉ : le programme coupe les échanges de la page, pas le vrai Wi-Fi. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import pannes as piece
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from conftest import lancer

SOIGNANT = "soignant-etage-2"
TABLETTE = {"X-Tablette": "liste"}  # ce que la page de liste ajoute à chacun de ses échanges
LISTE = {"badge": SOIGNANT, "patient": "p01", "liste": "installation"}


def _clinique():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


def _points(clinique):
    return {p["numero"]: p for p in clinique.listes.liste(clinique.badges[SOIGNANT], "p01", "installation")["points"]}


def test_la_panne_est_construite_et_porte_l_etiquette_simule():
    panne = piece.PANNES["lien_tablette"]
    assert panne["construite"] is True and panne["etiquette"] == "SIMULÉ"
    assert "hors ligne" in panne["ce_que_le_systeme_fait"].lower()


def test_lien_tablette_les_quatre_choses_obligatoires():
    client, clinique = _clinique()
    assert client.post("/api/clinique/liste/cocher", headers=TABLETTE, json={**LISTE, "numero": 1}).status_code == 200
    lancer(clinique.pannes.provoquer("lien_tablette"))

    # la page déjà ouverte ne reçoit plus rien : ni son contenu, ni l'heure, ni une coche
    for chemin in ("/clinique/soignant/liste/contenu?badge=soignant-etage-2&patient=p01&liste=installation", "/clinique/heure"):
        coupe = client.get(chemin, headers=TABLETTE)
        assert coupe.status_code == 503 and "lien" in coupe.json()["detail"]
    assert client.post("/api/clinique/liste/cocher", headers=TABLETTE, json={**LISTE, "numero": 2}).status_code == 503
    assert _points(clinique)[2]["etat"] != "fait"

    # 1. aucun ordre au robot ne part de la tablette sans lien
    demande = client.post("/api/clinique/demande", headers=TABLETTE,
                          json={"badge": SOIGNANT, "patient": "p01", "texte": "il manque : couverture"})
    assert demande.status_code == 503 and clinique.carnet.lignes("tâche") == []

    # 2. les autres écrans le disent (ils ont encore le lien) : ce qui se passe, ce que le système fait, qui est prévenu
    bandeau = client.get("/clinique/heure").text
    panne = piece.PANNES["lien_tablette"]
    for morceau in (panne["ce_qui_se_passe"], panne["ce_que_le_systeme_fait"], panne["qui_est_prevenu"], "SIMULÉ", "PANNE"):
        assert morceau in bandeau, morceau

    retour = lancer(clinique.pannes.finir("lien_tablette"))
    assert retour["active"] is False

    # 4. au retour, la tablette renvoie les coches faites hors ligne, avec l'heure où elles ont été faites
    for numero in (2, 3):
        r = client.post("/api/clinique/liste/cocher", headers=TABLETTE,
                        json={**LISTE, "numero": numero, "hors_ligne_a": f"2026-11-12T10:0{numero}:00"})
        assert r.status_code == 200
    points = _points(clinique)
    assert [points[n]["etat"] for n in (1, 2, 3)] == ["fait", "fait", "fait"]  # la coche d'avant et les deux renvoyées
    lignes = {l["donnees"]["numero"]: l["donnees"] for l in clinique.carnet.lignes("point de liste")}
    assert lignes[1]["comment"] == "au doigt"
    assert lignes[2]["comment"] == "au doigt, hors ligne" and lignes[2]["hors_ligne_a"] == "2026-11-12T10:02:00"
    # une coche renvoyée deux fois ne compte pas double
    client.post("/api/clinique/liste/cocher", headers=TABLETTE, json={**LISTE, "numero": 2, "hors_ligne_a": "2026-11-12T10:02:00"})
    assert len([l for l in clinique.carnet.lignes("point de liste") if l["donnees"]["numero"] == 2]) == 1

    # 3. le carnet note le début et la fin (la boîte noire : même écriture que pour la panne du robot, essayée là-bas)
    assert [(l["donnees"]["panne"], l["donnees"]["etat"]) for l in clinique.carnet.lignes("panne")] == [
        ("lien_tablette", "début"), ("lien_tablette", "fin")]
    assert "PANNE" not in client.get("/clinique/heure").text
    assert client.get("/clinique/heure", headers=TABLETTE).status_code == 200  # le lien est revenu


def test_la_boite_noire_note_la_panne_de_la_tablette(tmp_path, reglages):
    from briques.b12_boite_noire.journal import BoiteNoire, lire
    from commun.bus import Bus

    bus = Bus()
    boite = BoiteNoire(bus, tmp_path)
    pannes = piece.Pannes(Carnet(), bus=bus)
    lancer(pannes.provoquer("lien_tablette"))
    lancer(pannes.finir("lien_tablette"))
    boite.fermer()
    notes = [e for e in lire(boite.fichier) if e.type == "panne" and e.source == piece.SOURCE]
    assert [(e.donnees["quoi"], e.donnees["etat"], e.donnees["etiquette"]) for e in notes] == [
        ("lien_tablette", "début", "SIMULÉ"), ("lien_tablette", "fin", "SIMULÉ")]


def test_sans_panne_rien_n_est_coupe_et_les_autres_ecrans_ne_sont_jamais_coupes():
    client, clinique = _clinique()
    assert client.get("/clinique/heure", headers=TABLETTE).status_code == 200
    lancer(clinique.pannes.provoquer("lien_tablette"))
    assert client.get("/clinique/heure").status_code == 200  # un écran sans la marque de la tablette garde le lien
    assert client.get("/clinique/medecin").status_code == 200
    # le bouton qui finit la panne n'est jamais coupé, même depuis la tablette
    assert client.post("/api/clinique/pannes/lien_tablette/finir", headers={**TABLETTE, "X-Code-Equipe": "code-d-essai"}).status_code == 200


def test_une_heure_hors_ligne_trop_longue_ou_bizarre_est_refusee():
    client, clinique = _clinique()
    r = client.post("/api/clinique/liste/cocher", json={**LISTE, "numero": 4, "hors_ligne_a": "x" * 80})
    assert r.status_code == 422 and _points(clinique)[4]["etat"] != "fait"
    r = client.post("/api/clinique/liste/cocher", json={**LISTE, "numero": 4, "hors_ligne_a": "<script>"})
    assert r.status_code in (400, 422) and _points(clinique)[4]["etat"] != "fait"


def test_la_page_de_liste_porte_la_file_hors_ligne_et_le_dit():
    client, _ = _clinique()
    page = client.get("/clinique/soignant/liste", params=LISTE).text
    for morceau in ("HORS LIGNE", "X-Tablette", "fileHorsLigne", "Vous pouvez continuer à cocher", "hors_ligne_a"):
        assert morceau in page, morceau
    autre = client.get("/clinique/medecin").text
    assert "X-Tablette" not in autre  # seule la page de liste se dit « tablette »


@pytest.mark.skipif(shutil.which("node") is None, reason="Node absent : la file hors ligne n'est pas essayée ici")
def test_la_file_hors_ligne_de_la_tablette_essayee_avec_node():
    """La vraie file de la page (le même JavaScript), jouée par Node : on coche sans lien, puis le lien revient."""
    from briques.clinique.ecrans_listes import FILE_HORS_LIGNE_JS

    scenario = FILE_HORS_LIGNE_JS + """
    const assert = require('assert');
    const memoire = {};
    const stockage = {getItem: k => (k in memoire ? memoire[k] : null), setItem: (k, v) => { memoire[k] = String(v); }};
    (async () => {
      const file = fileHorsLigne(stockage, 'essai');
      assert.strictEqual(file.taille(), 0);
      file.ajouter({patient: 'p01', liste: 'installation', numero: 2}, '2026-11-12T10:02:00');
      file.ajouter({patient: 'p01', liste: 'installation', numero: 3}, '2026-11-12T10:03:00');
      file.ajouter({patient: 'p01', liste: 'installation', numero: 2}, '2026-11-12T10:04:00');  // deux fois le même point
      assert.strictEqual(file.taille(), 2);                      // pas de doublon
      assert.ok(file.contient('p01', 'installation', 3));
      // la page est rechargée : la file est toujours là (elle est gardée dans le navigateur)
      const apres = fileHorsLigne(stockage, 'essai');
      assert.strictEqual(apres.taille(), 2);
      // le lien n'est pas revenu : rien ne part, rien n'est perdu
      let envois = [];
      let reste = await apres.vider(async coche => { envois.push(coche.numero); return false; });
      assert.strictEqual(reste, 2); assert.deepStrictEqual(envois, [2]);   // elle s'arrête au premier refus
      // le lien revient au milieu : la première part, la seconde attend
      envois = [];
      reste = await apres.vider(async coche => { envois.push(coche.numero); return envois.length === 1; });
      assert.strictEqual(reste, 1); assert.deepStrictEqual(envois, [2, 3]);
      // puis tout part, dans l'ordre, avec l'heure d'origine
      envois = [];
      reste = await apres.vider(async coche => { envois.push([coche.numero, coche.hors_ligne_a]); return true; });
      assert.strictEqual(reste, 0); assert.deepStrictEqual(envois, [[3, '2026-11-12T10:03:00']]);
      assert.strictEqual(fileHorsLigne(stockage, 'essai').taille(), 0);
      // un envoi qui casse (erreur) ne perd rien
      apres.ajouter({patient: 'p01', liste: 'installation', numero: 5}, '2026-11-12T10:05:00');
      reste = await apres.vider(async () => { throw new Error('réseau'); });
      assert.strictEqual(reste, 1);
      console.log('FILE HORS LIGNE : TENUE');
    })().catch(e => { console.error(e); process.exit(1); });
    """
    sortie = subprocess.run(["node", "-e", scenario], capture_output=True, text=True, timeout=30)
    assert sortie.returncode == 0 and "FILE HORS LIGNE : TENUE" in sortie.stdout, sortie.stderr
