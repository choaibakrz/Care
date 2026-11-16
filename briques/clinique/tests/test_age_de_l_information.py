"""La clinique en boîte — K03b, ce qui est vieux se voit (avenant 2, K03 ; seconde moitié).

« Fini » veut dire :
- chaque écran affiche « mis à jour il y a tant de secondes » ;
- une vérification coupe les mises à jour d'un écran, et la zone se grise en moins de douze secondes, avec
  « information vieille de tant de secondes » ; quand les mises à jour reviennent, la zone redevient nette ;
- la limite est réglable (dix secondes pour commencer) ;
- sur un vrai robot, une personne peut constater : le bouton « je l'ai vu » ;
- quand un humain valide un papier, la boîte noire écrit son badge et l'heure.
Le petit programme de la page est joué par Node (le même JavaScript), avec une fausse montre.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import ecrans
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.ecrans_listes import dessiner_taches
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from commun.bus import Bus

BANC = """
const assert = require('assert');
let maintenant = 1000000;
Date.now = () => maintenant;
const elements = {};
function element(id) {
  if (!elements[id]) {
    const classes = new Set();
    elements[id] = {id, textContent: '', innerHTML: '', className: '', style: {},
                    classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c)}};
  }
  return elements[id];
}
global.document = {getElementById: element};
let lien = true;
global.fetch = async () => { if (!lien) throw new Error('coupé'); return {ok: true, text: async () => 'contenu'}; };
const minuteries = [];
global.setInterval = (f, ms) => { minuteries.push({f, ms}); return minuteries.length; };
async function avancer(secondes) {   // le temps avance, seconde par seconde ; chaque minuterie sonne à son rythme
  for (let s = 0; s < secondes; s++) {
    maintenant += 1000;
    for (const m of minuteries) if (((maintenant - 1000000) % m.ms) === 0) await m.f();
  }
}
"""

SCENARIO = """
(async () => {
  const zone = element('contenu'), age = element('age');
  await avancer(6);                                   // les mises à jour arrivent
  assert.ok(!zone.classList.contains('grise'), 'nette quand les mises à jour arrivent');
  assert.ok(/^mis à jour il y a [01] secondes?$/.test(age.textContent), age.textContent);
  lien = false;                                       // on coupe les mises à jour de cet écran
  let grise_a = null;
  for (let s = 1; s <= 15; s++) {
    await avancer(1);
    if (grise_a === null && zone.classList.contains('grise')) grise_a = s;
  }
  assert.ok(grise_a !== null && grise_a < 12, 'grisée en moins de douze secondes : ' + grise_a);
  assert.ok(grise_a > LIMITE, 'pas avant la limite : ' + grise_a);
  assert.ok(/^information vieille de 1[4-6] secondes$/.test(age.textContent), age.textContent);
  assert.strictEqual(element('vieux').style.display, 'block');
  lien = true;                                        // les mises à jour reviennent
  await avancer(2);
  assert.ok(!zone.classList.contains('grise'), 'nette quand les mises à jour reviennent');
  assert.ok(/^mis à jour il y a [01] secondes?$/.test(age.textContent), age.textContent);
  console.log('AGE : GRISE A ' + grise_a + ' S');
})().catch(e => { console.error(e); process.exit(1); });
"""


def _jouer(script: str, limite: int) -> str:
    code = script.replace("<script>", "").replace("</script>", "")
    sortie = subprocess.run(["node", "-e", BANC + code + f"\nconst LIMITE = {limite};\n" + SCENARIO], capture_output=True,
                            text=True, timeout=30)
    assert sortie.returncode == 0, sortie.stderr
    return sortie.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node absent : le petit programme de la page n'est pas essayé ici")
def test_on_coupe_les_mises_a_jour_et_la_zone_se_grise_en_moins_de_douze_secondes():
    sortie = _jouer(ecrans.script_de_mise_a_jour("/clinique/soignant/contenu"), ecrans.LIMITE_VIEUX_S)
    assert "AGE : GRISE A 11 S" in sortie  # dix secondes de limite, vérifiée chaque seconde : grisée à la onzième


def test_la_limite_est_reglable_et_vaut_dix_secondes_pour_commencer():
    assert ecrans.LIMITE_VIEUX_S == 10
    assert "const LIMITE_VIEUX_S = 10;" in ecrans.script_de_mise_a_jour("/x")
    assert "const LIMITE_VIEUX_S = 4;" in ecrans.script_de_mise_a_jour("/x", limite_s=4)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node absent")
def test_avec_une_limite_de_quatre_secondes_la_zone_se_grise_plus_tot():
    script = ecrans.script_de_mise_a_jour("/x", limite_s=4)
    code = script.replace("<script>", "").replace("</script>", "")
    scenario = """
    (async () => {
      await avancer(4); lien = false; let a = null;
      for (let s = 1; s <= 8; s++) { await avancer(1); if (a === null && element('contenu').classList.contains('grise')) a = s; }
      console.log('GRISE A ' + a);
    })();"""
    sortie = subprocess.run(["node", "-e", BANC + code + scenario], capture_output=True, text=True, timeout=30)
    assert "GRISE A 5" in sortie.stdout, sortie.stdout + sortie.stderr


# ---------------------------------------------------------------------------------------------- sur les vraies pages
@pytest.fixture
def banc():
    bus = Bus()
    horloge, app = HorlogeDeDemonstration(bus=bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="")
    return TestClient(app), clinique, bus


@pytest.mark.parametrize("chemin", ["/clinique/soignant?badge=soignant-etage-2", "/clinique/accueil", "/clinique/medecin",
                                    "/clinique/patient", "/clinique/therapeute", "/clinique/flotte"])
def test_chaque_ecran_affiche_l_age_de_ce_qu_il_montre(banc, chemin):
    client, _, _ = banc
    page = client.get(chemin).text
    assert "id='age'" in page and "mis à jour il y a" in page and "information vieille de" in page
    assert "const LIMITE_VIEUX_S = 10;" in page and ".grise{" in page


# ---------------------------------------------------------------------------------------------- « je l'ai vu »
def test_le_bouton_je_l_ai_vu_n_apparait_que_si_ce_n_est_pas_encore_constate():
    tache = {"id": "t1", "quoi": "couverture", "ou": "Chambre 12", "nom_du_patient": "Madame Exemple", "sorte": "robot",
             "etat": "livrée", "etiquette": "RÉEL", "constate": "pas encore"}
    avec = html.unescape(dessiner_taches([tache], True, "soignant-etage-2"))
    assert "Je l'ai vu" in avec and "/clinique/soignant/tache/constater?badge=soignant-etage-2&tache=t1" in avec
    assert "Je l'ai vu" not in html.unescape(dessiner_taches([{**tache, "constate": "oui"}], True, "soignant-etage-2"))


def test_une_personne_constate_et_c_est_ecrit_avec_son_badge(banc):
    client, clinique, bus = banc
    soignant = clinique.badges["soignant-etage-2"]
    tache = clinique.taches.demander(soignant, "p01", "la couverture")["tache"]
    robot = clinique.badges["robot-r1"]
    clinique.taches.changer_etat(robot, tache["id"], "livrée", etiquette="RÉEL", constate="pas encore", constat="vrai robot")
    r = client.post(f"/clinique/soignant/tache/constater?badge=soignant-etage-2&tache={tache['id']}", follow_redirects=False)
    assert r.status_code == 303
    apres = clinique.taches.tache(tache["id"])
    assert apres["etat"] == "livrée" and apres["constate"] == "oui" and "soignant-etage-2" in apres["constat"]
    notes = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "temps_d_un_geste"]
    assert notes[-1]["temps"] == "CONSTATÉ" and notes[-1]["par"] == "soignant-etage-2" and notes[-1]["tache"] == tache["id"]
    assert "une personne" in notes[-1]["comment"]
    # une deuxième fois : déjà constaté ; et un robot ne constate pas lui-même
    assert client.post(f"/clinique/soignant/tache/constater?badge=soignant-etage-2&tache={tache['id']}",
                       follow_redirects=False).status_code == 400
    assert client.post(f"/clinique/soignant/tache/constater?badge=robot-r1&tache={tache['id']}",
                       follow_redirects=False).status_code in (400, 403)


# ---------------------------------------------------------------------------------------------- qui a donné l'accord
def test_quand_un_humain_valide_un_papier_la_boite_noire_ecrit_son_badge_et_l_heure(banc):
    client, clinique, bus = banc
    pile = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    papier = pile["a_valider"][0]["id"]
    r = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": papier})
    assert r.status_code == 200, r.text
    accords = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "accord_d_un_humain"]
    assert len(accords) == 1
    accord = accords[0]
    assert accord["badge"] == "accueil" and accord["pour"] == "papier rangé" and accord["papier"] == papier and accord["heure"]
    assert "Giulia" not in json.dumps(accord, ensure_ascii=False)
