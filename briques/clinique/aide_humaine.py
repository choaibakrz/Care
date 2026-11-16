"""Toute aide humaine se compte (avenant 2, tâche K02 ; première moitié : K02a).

Une AIDE HUMAINE, c'est : quelqu'un appuie sur « J'ai aidé » ; un humain reprend une tâche de robot ; une tâche est
relancée à la main ; un humain fait un geste à la place du robot (poser ou prendre l'objet sur son plateau) ; un geste
est télécommandé (K02b). Chaque aide est notée, puis écrite dans la boîte noire : une note « AIDE HUMAINE ».

Quatre cases pour chaque essai, et une seule : réussi du premier coup ; réussi après une reprise automatique ; réussi
avec une aide humaine ; raté. Une aide humaine passe avant une reprise automatique. Raté reste raté.

    with compter() as compte:      # pendant un essai : tout ce qui est signalé arrive dans `compte`
        ...
    classer(reussi, len(compte.aides), compte.reprises_imprevues)

DIRE VRAI :
- La panne provoquée du scénario (scène 6) et sa reprise sont PRÉVUES : elles ne font pas « une reprise automatique ».
  Leur nombre est affiché à part. Aujourd'hui toutes les pannes sont provoquées : la case « reprise automatique » reste
  donc vide tant qu'aucune reprise imprévue n'arrive.
- L'événement est une note « AIDE HUMAINE » (type « note » de la boîte noire) : on n'a pas ajouté de type à l'ossature.
- Le troisième chiffre (plus longue durée sans arrêt) vient de la commande « endurance » (`endurance.py`, K02b).
- Un geste télécommandé porte « RÉEL · TÉLÉCOMMANDÉ » sur un vrai robot, « FAUX ROBOT · TÉLÉCOMMANDÉ » sinon.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

from pydantic import BaseModel

QUOI = "AIDE HUMAINE"
SOURCE = "clinique"
SORTES = {"bouton": "quelqu'un a appuyé sur « J'ai aidé »", "main": "un humain a repris une tâche de robot",
          "relance": "une tâche a été relancée à la main", "geste": "un humain a fait un geste à la place du robot",
          "telecommande": "un geste a été télécommandé par une personne"}
CASES = ("du premier coup", "après une reprise automatique", "avec une aide humaine", "raté")


class Compte:
    """Ce qui est signalé pendant un essai."""

    def __init__(self) -> None:
        self.aides: list[dict[str, Any]] = []
        self.taches_de_robot = 0
        self.reprises_prevues = 0
        self.reprises_imprevues = 0
        self.livraisons = 0  # avenant 2, K03 : les livraisons d'un robot, et celles qu'autre chose que sa parole a montrées
        self.constatees = 0


_ouverts: list[Compte] = []


@contextmanager
def compter():
    compte = Compte()
    _ouverts.append(compte)
    try:
        yield compte
    finally:
        _ouverts.remove(compte)


def etiquette_telecommande(vrai_robot: bool) -> str:
    """Un geste télécommandé par une personne. « RÉEL » seulement si le robot est un vrai robot."""
    return "RÉEL · TÉLÉCOMMANDÉ" if vrai_robot else "FAUX ROBOT · TÉLÉCOMMANDÉ"


def signaler(sorte: str, qui: str, tache: str | None = None, detail: str = "", **plus: Any) -> dict[str, Any]:
    """Noter une aide humaine. Rend la note ; elle sera écrite dans la boîte noire par `ecrire_dans_la_boite`."""
    if sorte not in SORTES:
        raise ValueError(f"sorte d'aide inconnue « {sorte} » (connues : {', '.join(SORTES)})")
    aide = {"quoi": QUOI, "sorte": sorte, "ce_que_c_est": SORTES[sorte], "qui": str(qui)[:60], "tache": tache,
            "detail": " ".join(str(detail or "").split())[:160], "quand": datetime.now().isoformat(timespec="seconds"), **plus}
    for compte in _ouverts:
        compte.aides.append(aide)
    return aide


def tache_de_robot() -> None:
    """Une tâche vient d'être demandée à un robot (pour le chiffre « une aide humaine pour tant de tâches »)."""
    for compte in _ouverts:
        compte.taches_de_robot += 1


def signaler_reprise(prevue: bool) -> None:
    """Une tâche de robot passe « reprise ». `prevue` : c'est une panne provoquée, donc dans le scénario."""
    for compte in _ouverts:
        if prevue:
            compte.reprises_prevues += 1
        else:
            compte.reprises_imprevues += 1


def signaler_constat(oui: bool) -> None:
    """Un robot a confirmé une livraison. `oui` : autre chose que sa parole l'a montré (CONSTATÉ)."""
    for compte in _ouverts:
        compte.livraisons += 1
        compte.constatees += bool(oui)


def classer(reussi: bool, aides: int, reprises_imprevues: int) -> str:
    """La case de l'essai : une seule."""
    if not reussi:
        return CASES[3]
    if aides:
        return CASES[2]
    return CASES[1] if reprises_imprevues else CASES[0]


async def ecrire_dans_la_boite(bus, tableau, **plus: Any) -> int:
    """Écrire dans la boîte noire les aides du tableau des tâches qui n'y sont pas encore. Rend leur nombre."""
    if bus is None or tableau is None:
        return 0
    a_ecrire = [a for a in tableau.aides if not a.get("dans_la_boite")]
    for aide in a_ecrire:
        aide["dans_la_boite"] = True
        await bus.emettre("note", SOURCE, **{c: v for c, v in aide.items() if c != "dans_la_boite"}, **plus)
    return len(a_ecrire)


def ecouter_la_main(bus, tableau, vrai_robot=lambda: False) -> None:
    """Écouter la main humaine de l'ossature (brique 11, événement « pilotage_humain ») : un humain qui reprend la
    main, c'est une aide ; chaque ordre qu'il donne est un geste télécommandé, et c'est aussi une aide."""
    async def sur_pilotage(ev) -> None:
        d = ev.donnees
        if d.get("quoi") == "reprise":
            tableau.noter_aide("main", qui=d.get("qui") or "humain", detail="un humain a repris la main (brique 11)")
        elif d.get("quoi") == "ordre":
            tableau.noter_aide("telecommande", qui=d.get("qui") or "humain", etiquette=etiquette_telecommande(bool(vrai_robot())),
                               detail=f"geste télécommandé : {d.get('action') or '?'}")
        else:
            return
        await ecrire_dans_la_boite(bus, tableau)

    bus.abonner(sur_pilotage, "pilotage_humain")


def chiffres(cases: dict[str, int], aides: int, taches: int, etiquette: str, date: str,
             endurance: dict[str, Any] | None = None) -> list[str]:
    """Les trois chiffres, avec leur niveau de preuve, leur nombre d'essais et leur date."""
    n = sum(cases.values())
    preuve = f"[{etiquette}, {n} essais, {date}]"
    if taches == 0:
        deux = "aucune tâche de robot dans ces essais : pas de chiffre"
    elif aides == 0:
        deux = f"aucune aide sur {taches} tâches de robot"
    else:
        par = f"{taches / aides:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        deux = (f"{aides} aide{'s' if aides > 1 else ''} humaine{'s' if aides > 1 else ''} pour {taches} tâches de robot, "
                f"soit une aide pour {par} tâche{'s' if taches / aides >= 2 else ''}")
    if endurance is None:
        trois = "plus longue durée sans arrêt : non mesuré (lancer : python3 lancer.py endurance --duree 5m)"
    else:
        from .endurance import AUCUN_ARRET, texte_duree

        jour = "{2}.{1}.{0}".format(*str(endurance.get("date", "?"))[:10].split("-")) if endurance.get("date") else "?"
        fin = "" if endurance.get("arret") == AUCUN_ARRET else f" — puis : {endurance.get('arret')}"
        trois = (f"plus longue durée sans arrêt : {texte_duree(endurance['duree_tenue_s'])} "
                 f"[{endurance.get('etiquette', '?')}, {endurance.get('passages', '?')} passages du scénario, {jour}]{fin}")
    return [f"CHIFFRE 1 — réussis du premier coup : {cases[CASES[0]]} sur {n} {preuve}",
            f"CHIFFRE 2 — {deux} {preuve}", f"CHIFFRE 3 — {trois}"]


# ---------------------------------------------------------------------- la page du chef : le bouton « J'ai aidé »
SCRIPT = """<script>
document.getElementById('aide').onclick = async () => {
  const dit = document.getElementById('dit');
  const tete = {'Content-Type': 'application/json'};
  const code = document.getElementById('code').value;
  if (code) tete['X-Code-Equipe'] = code;
  const r = await fetch('/api/clinique/aide-humaine', {method: 'POST', headers: tete,
    body: JSON.stringify({qui: document.getElementById('qui').value, note: document.getElementById('note').value})});
  dit.textContent = r.ok ? 'Noté : une aide humaine.' : 'Refusé (' + r.status + ') : le code d\\'équipe ?';
  if (r.ok) document.getElementById('compte').innerHTML = await (await fetch('/clinique/aide-humaine/contenu')).text();
};
</script>"""


class Aide(BaseModel):
    qui: str = "équipe"
    note: str = ""


def dessiner(tableau) -> str:
    from .ecrans import _e

    aides = tableau.aides
    if not aides:
        return "<p><b>Dans cette séance : aucune aide humaine notée.</b></p>"
    rangs = "".join(f"<li>{_e(a['quand'][11:])} — {_e(a['ce_que_c_est'])} — {_e(a['qui'])}"
                    f"{' — tâche ' + _e(a['tache']) if a.get('tache') else ''}{' — ' + _e(a['detail']) if a['detail'] else ''}</li>"
                    for a in aides)
    return (f"<p><b>Dans cette séance : {len(aides)} aide{'s' if len(aides) > 1 else ''} humaine{'s' if len(aides) > 1 else ''}.</b></p>"
            f"<ul>{rangs}</ul>")


def brancher_aide_humaine(app, clinique, protege: list, bus=None) -> None:
    from fastapi.responses import HTMLResponse

    from .ecrans import _heure_html, _page

    @app.get("/clinique/aide-humaine", response_class=HTMLResponse)
    async def page_aide():
        tete = f"<h1>Aide humaine</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        milieu = ("<p class='ou'>Pour le chef de démonstration. Si quelqu'un touche le robot, l'objet ou le clavier pour "
                  "aider : appuyez. Une aide notée ne s'efface pas. L'essai en cours ne comptera pas comme « réussi du "
                  "premier coup ». Données inventées.</p>"
                  "<p><label>Qui <input id='qui' size='20' maxlength='60' value='chef de démonstration'></label> "
                  "<label>Note courte <input id='note' size='34' maxlength='160'></label></p>"
                  "<p><label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' "
                  "autocomplete='off'></label></p>"
                  "<p><button id='aide'>J'ai aidé</button></p><div class='dit' id='dit' role='status'></div>"
                  f"<div id='compte'>{dessiner(clinique.taches)}</div>"
                  "<p class='ou'>Les chiffres des essais comptés (réussis du premier coup, une aide pour tant de tâches) : "
                  "commande <code>python3 lancer.py essais</code>.</p>")
        return _page("Clinique — Aide humaine", tete, milieu, SCRIPT)

    @app.get("/clinique/aide-humaine/contenu", response_class=HTMLResponse)
    async def page_aide_contenu():
        return dessiner(clinique.taches)

    @app.get("/api/clinique/aide-humaine")
    async def api_lire():
        return {"marque": "données inventées", "aides": len(clinique.taches.aides),
                "liste": [{c: v for c, v in a.items() if c != "dans_la_boite"} for a in clinique.taches.aides]}

    @app.post("/api/clinique/aide-humaine", dependencies=protege)
    async def api_aider(a: Aide):
        aide = clinique.taches.noter_aide("bouton", qui=a.qui or "équipe", detail=a.note)
        await ecrire_dans_la_boite(bus, clinique.taches)
        return {"aide": {c: v for c, v in aide.items() if c != "dans_la_boite"}, "aides": len(clinique.taches.aides)}
