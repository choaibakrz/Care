"""L'instant précis : la page « Moments » (avenant jury, J03). « Montrez-moi le moment exact où ça a raté. »

    /clinique/moments?seance=…            les moments marquants d'une séance, du plus récent au plus ancien
    /clinique/moments/voir?seance=…&m=…   un moment : quatre choses, dans l'ordre
    python3 lancer.py moments [FICHIER] [--carnet FICHIER]

Elle lit la boîte noire d'une séance (journal/*.jsonl) et, s'il existe, le carnet de la même séance
(journal/clinique/carnet_*.jsonl) : aujourd'hui le carnet de la clinique n'est pas encore recopié dans la boîte noire
(tâche T27). Les deux sont rangés par leur heure réelle.

Sept sortes de moments : un échec, un « je ne suis pas sûr », un refus du gardien, une reprise par un humain, une
panne, une phrase retirée faute de source, un papier non rangé.
Pour chaque moment : 1. ce que le système a vu ou entendu ; 2. ce qu'il a décidé, et pourquoi ; 3. ce qu'il a fait ;
4. les dix secondes d'avant et d'après.
Les erreurs attrapées : combien de fois le système s'est arrêté de lui-même ou a demandé un humain.

RIEN N'EST INVENTÉ : un moment ne dit que ce qui est écrit dans la boîte noire ou le carnet. Quand une des quatre
choses n'y est pas, la page écrit « pas noté dans la séance ».
La page montre des lignes du carnet (des noms inventés, des demandes) : elle est pour l'équipe, avec le code d'équipe.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from briques.b12_boite_noire.journal import DOSSIER_DEFAUT, lire

from .accueil import GENRE_APPEL
from .pannes import GENRE as GENRE_PANNE
from .papiers import A_TRIER, PROPOSE
from .papiers import GENRE as GENRE_PAPIER
from .resume import GENRE as GENRE_RESUME
from .taches import GENRE as GENRE_TACHE

PAS_NOTE = "pas noté dans la séance"
DIX_SECONDES = 10.0
ATTRAPEES = ("un refus du gardien", "un « je ne suis pas sûr »", "une reprise par un humain", "un papier non rangé",
             "un arrêt d'urgence")


# ---------------------------------------------------------------------- lire une séance
def lire_seance(boite: str | Path | None, carnet: str | Path | None) -> list[dict[str, Any]]:
    """Tout ce qui est écrit dans la boîte noire et dans le carnet, rangé par l'heure réelle."""
    entrees: list[dict[str, Any]] = []
    if boite and Path(boite).exists():
        for e in lire(boite):
            entrees.append({"heure": str(e.heure), "origine": "boîte noire", "type": e.type, "source": e.source,
                            "donnees": e.donnees, "id": e.id, "conversation": e.conversation})
    if carnet and Path(carnet).exists():
        for brute in Path(carnet).read_text(encoding="utf-8").splitlines():
            try:
                l = json.loads(brute)
                entrees.append({"heure": str(l["quand"]["reel"]), "origine": "carnet", "type": l["genre"], "source": l["qui"],
                                "donnees": l["donnees"], "id": f"c{l['numero']}", "conversation": None})
            except (ValueError, KeyError, TypeError):
                continue  # une ligne abîmée ne bloque pas la lecture
    return sorted(entrees, key=lambda e: e["heure"])


def _secondes(heure: str) -> float | None:
    try:
        return datetime.fromisoformat(heure).timestamp()
    except ValueError:
        return None


def _court(donnees: dict[str, Any]) -> str:
    morceaux = []
    for cle in ("texte", "quoi", "etat", "verdict", "issue", "titre", "raison", "papier", "id", "demande"):
        valeur = donnees.get(cle)
        if valeur not in (None, "", [], {}):
            morceaux.append(f"{cle} : {valeur}")
    action = donnees.get("action")
    if isinstance(action, dict) and action.get("nom"):
        morceaux.append(f"action : {action['nom']}")
    return " ; ".join(morceaux)[:200]


def _ligne(entree: dict[str, Any]) -> dict[str, str]:
    return {"heure": entree["heure"][11:23], "id": entree["id"], "origine": entree["origine"],
            "quoi": f"{entree['type']} ({entree['source']})" + (f" — {_court(entree['donnees'])}" if _court(entree["donnees"]) else "")}


def autour(entrees: list[dict[str, Any]], moment: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Ce qui est écrit dans les dix secondes d'avant et les dix secondes d'après."""
    t0 = _secondes(moment["heure"])
    avant, apres = [], []
    for e in entrees:
        t = _secondes(e["heure"])
        if e is moment or e["id"] == moment["id"] or t is None or t0 is None or abs(t - t0) > DIX_SECONDES:
            continue
        (avant if (t, e["heure"]) < (t0, moment["heure"]) or (t == t0 and entrees.index(e) < entrees.index(moment)) else apres).append(_ligne(e))
    return {"avant": avant[-20:], "apres": apres[:20]}


def _raisons(donnees: dict[str, Any]) -> str:
    return ", ".join(str(r.get("code", r)) if isinstance(r, dict) else str(r) for r in donnees.get("raisons") or []) or PAS_NOTE


def _conversation(entrees: list[dict[str, Any]], e: dict[str, Any], type_: str, apres: bool = False) -> str:
    """Dans la même conversation : la phrase entendue avant, ou la réponse dite après."""
    if not e.get("conversation"):
        return ""
    memes = [x for x in entrees if x["conversation"] == e["conversation"] and x["type"] == type_]
    memes = [x for x in memes if (entrees.index(x) > entrees.index(e)) == apres]
    return str(memes[0 if apres else -1]["donnees"].get("texte", "")) if memes else ""


def _moment(entrees: list[dict[str, Any]], e: dict[str, Any]) -> dict[str, Any] | None:
    """Si cette ligne est un moment marquant : sa sorte, son titre, et trois des quatre choses. Sinon None."""
    d, type_, origine = e["donnees"], e["type"], e["origine"]
    genre = titre = vu = decide = fait = None
    if origine == "boîte noire":
        if type_ == "gardien_decision" and d.get("verdict") == "non":
            action = (d.get("action") or {}).get("nom", "?")
            entendu = _conversation(entrees, e, "parole_entendue")
            reponse = _conversation(entrees, e, "reponse_dite", apres=True)
            genre, titre = "un refus du gardien", f"le gardien refuse « {action} » ({_raisons(d)})"
            vu = (f"phrase entendue : « {entendu} » ; " if entendu else "") + f"action demandée : {action} {(d.get('action') or {}).get('parametres') or ''}"
            decide = f"le gardien a dit non, parce que : {_raisons(d)}"
            fait = "rien n'est parti vers le robot" + (f" ; le robot a répondu : « {reponse} »" if reponse else "")
        elif type_ == "gardien_decision" and d.get("verdict") == "humain":
            action = (d.get("action") or {}).get("nom", "?")
            genre, titre = "une reprise par un humain", f"le gardien demande l'accord d'un humain pour « {action} »"
            vu, decide = f"action demandée : {action}", f"le gardien ne décide pas seul, parce que : {_raisons(d)}"
            fait = "rien n'est parti ; la demande attend l'accord d'un humain"
        elif type_ == "arret_urgence":
            genre, titre = "un arrêt d'urgence", f"arrêt d'urgence ({d.get('raison', '?')}, par {d.get('qui', '?')})"
            vu, decide = f"raison notée : {d.get('raison', PAS_NOTE)}", f"arrêt d'urgence demandé par {d.get('qui', '?')} : il passe avant tout"
            fait = "le robot est arrêté ; seul un humain réarme"
        elif type_ in ("aide_demandee", "question_posee"):
            genre, titre = "un « je ne suis pas sûr »", f"le robot {'demande de l’aide' if type_ == 'aide_demandee' else 'pose une question'}"
            vu = (f"phrase entendue : « {_conversation(entrees, e, 'parole_entendue')} »" if _conversation(entrees, e, "parole_entendue")
                  else PAS_NOTE)
            decide = f"il n'est pas sûr : {d.get('raison') or d.get('texte') or PAS_NOTE}"
            fait = "il n'agit pas ; il demande"
        elif type_ == "pilotage_humain" and d.get("quoi") == "reprise":
            genre, titre = "une reprise par un humain", "un humain prend la main"
            vu, decide, fait = PAS_NOTE, f"un humain reprend la main ({d.get('operateur', 'opérateur non noté')})", "le robot est piloté par un humain"
        elif type_ == "panne" and d.get("etat", "début") == "début":
            genre, titre = "une panne", f"panne : {d.get('titre') or d.get('quoi', '?')}" + (" [SIMULÉ, provoquée]" if d.get("provoquee") else "")
            vu = f"panne « {d.get('quoi', '?')} »" + (", provoquée exprès" if d.get("provoquee") else ", constatée")
            decide = "le système se met à l'abri : il ne commence rien de nouveau avec la pièce en panne"
            fait = "les écrans le disent ; ce qui marche sans cette pièce continue"
        elif type_ == "note" and d.get("quoi") == "etape_d_un_essai" and d.get("issue") == "ratee":
            genre, titre = "un échec", f"essai {d.get('essai')}, étape {d.get('etape')} : ratée"
            vu = f"essai {d.get('essai')} ; changements de l'essai : {d.get('changements') or PAS_NOTE}"
            decide = f"l'étape est comptée ratée : {str(d.get('ligne', PAS_NOTE)).strip()}"
            fait = "l'échec reste au tableau : il n'est ni effacé ni rejoué"
        elif type_ == "action_terminee" and d.get("statut") in ("echouee", "ratee"):
            genre, titre = "un échec", f"une action du robot a raté ({d.get('code_erreur') or d.get('message') or '?'})"
            vu, decide = PAS_NOTE, f"l'action est notée ratée : {d.get('code_erreur') or d.get('message') or PAS_NOTE}"
            fait = "l'action s'arrête là"
    else:  # le carnet de la clinique
        if type_ == GENRE_TACHE and d.get("etat") == "échouée":
            genre, titre = "un échec", f"la course « {d.get('quoi', '?')} » a échoué"
            vu = f"demande : « {d.get('demande', PAS_NOTE)} » ({d.get('quoi', '?')} → {d.get('ou', '?')})"
            decide = f"la tâche est notée « échouée », parce que : {d.get('pourquoi', PAS_NOTE)}"
            fait = "le robot s'arrête ; la tâche reste au tableau, avec sa raison"
        elif type_ == GENRE_TACHE and d.get("sorte") == "humain" and d.get("pourquoi_un_humain"):
            genre, titre = "une reprise par un humain", f"« {d.get('quoi', '?')} » passe à un humain"
            vu = f"demande : « {d.get('demande') or d.get('quoi', PAS_NOTE)} » ({d.get('ou', '?')})"
            decide = f"la tâche passe à un humain, parce que : {d['pourquoi_un_humain']}"
            fait = "aucun robot ne la fait ; elle attend une personne"
        elif type_ == GENRE_APPEL:
            genre, titre = "une reprise par un humain", f"le robot du hall appelle une personne ({d.get('raison', '?')})"
            vu, decide = PAS_NOTE, f"il ne répond pas lui-même, parce que : {d.get('raison', PAS_NOTE)}"
            fait = "une personne de l'accueil est appelée"
        elif type_ == GENRE_PAPIER and d.get("etat") == A_TRIER:
            genre, titre = "un papier non rangé", f"le papier {d.get('papier', '?')} reste « à trier »"
            vu = f"papier {d.get('papier', '?')}, type proposé : {d.get('type') or 'aucun'}"
            decide = f"il n'est pas rangé, parce que : {d.get('dit') or 'aucun patient trouvé'}"
            fait = "le papier attend un humain ; rien n'est rangé"
        elif type_ == GENRE_PAPIER and d.get("etat") == PROPOSE and d.get("confiance") not in (None, "haute"):
            genre, titre = "un « je ne suis pas sûr »", f"papier {d.get('papier', '?')} : confiance {d.get('confiance')}"
            vu = f"papier {d.get('papier', '?')}, type proposé : {d.get('type') or 'aucun'}"
            decide = f"« je ne suis pas sûr », parce que : {', '.join(d.get('raisons') or []) or d.get('dit') or PAS_NOTE}"
            fait = "la proposition est montrée avec « je ne suis pas sûr » ; l'humain choisit"
        elif type_ == GENRE_RESUME and d.get("retirees"):
            retirees = d["retirees"] if isinstance(d["retirees"], list) else []
            genre, titre = "une phrase retirée faute de source", f"{len(retirees) or d['retirees']} phrase(s) retirée(s) du résumé de {d.get('patient', '?')}"
            vu = "phrase(s) préparée(s) : " + (" ; ".join(f"« {r.get('texte', '?')} »" for r in retirees) or PAS_NOTE)
            decide = "retirée(s) du résumé : une phrase sans source, ou avec un chiffre absent de sa source, n'est pas montrée"
            fait = "le médecin ne la voit pas ; le reste du résumé est servi avec ses sources"
        elif type_ == GENRE_PANNE and d.get("etat") == "début" and not any(
                x["origine"] == "boîte noire" and x["type"] == "panne" for x in entrees):
            genre, titre = "une panne", f"panne : {d.get('titre', '?')} [SIMULÉ, provoquée]"
            vu, decide = f"panne « {d.get('panne', '?')} », provoquée exprès", "le système se met à l'abri : il ne commence rien de nouveau avec la pièce en panne"
            fait = "les écrans le disent ; ce qui marche sans cette pièce continue"
    if genre is None:
        return None
    return {"id": e["id"], "heure": e["heure"], "origine": origine, "genre": genre, "titre": titre,
            "quatre": {"vu": vu or PAS_NOTE, "decide": decide or PAS_NOTE, "fait": fait or PAS_NOTE, "autour": autour(entrees, e)}}


def moments(entrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les moments marquants, du plus récent au plus ancien."""
    trouves = [m for m in (_moment(entrees, e) for e in entrees) if m is not None]
    return list(reversed(trouves))


def erreurs_attrapees(trouves: list[dict[str, Any]]) -> dict[str, Any]:
    """Combien de fois le système s'est arrêté de lui-même ou a demandé un humain. Compté, jamais tapé."""
    liste = [m for m in trouves if m["genre"] in ATTRAPEES]
    return {"compte": len(liste), "liste": liste,
            "texte": f"{len(liste)} fois, dans cette séance, le système s'est arrêté de lui-même ou a demandé un humain"}


# ---------------------------------------------------------------------- les séances de cet ordinateur
class Seances:
    def __init__(self, dossier: Path = DOSSIER_DEFAUT, clinique=None, systeme=None) -> None:
        self.dossier, self.clinique, self.systeme = Path(dossier), clinique, systeme
        self.carnets: dict[str, Path] = {}  # séance → son carnet, quand on le connaît

    def noms(self) -> list[str]:
        if not self.dossier.exists():
            return []
        return [f.stem for f in sorted(self.dossier.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)][:40]

    def chemins(self, seance: str) -> tuple[Path, Path | None]:
        if seance not in self.noms():
            raise KeyError(seance)
        boite = self.dossier / f"{seance}.jsonl"
        if seance in self.carnets:
            return boite, Path(self.carnets[seance])
        if (self.systeme is not None and self.clinique is not None and self.systeme.boite_noire.fichier.stem == seance
                and self.clinique.carnet.fichier):
            return boite, Path(self.clinique.carnet.fichier)  # la séance en cours : son carnet est connu
        return boite, self._carnet_proche(seance)

    def _carnet_proche(self, seance: str) -> Path | None:
        """Le carnet lancé dans les dix secondes autour de cette boîte noire, s'il y en a un (même lancement)."""
        try:
            debut = datetime.strptime(seance[:17], "%Y-%m-%d_%H%M%S")
        except ValueError:
            return None
        proches = []
        for f in (self.dossier / "clinique").glob("carnet_*.jsonl"):
            try:
                ecart = abs((datetime.strptime(f.stem[7:24], "%Y-%m-%d_%H%M%S") - debut).total_seconds())
            except ValueError:
                continue
            if ecart <= 10:
                proches.append((ecart, f))
        return min(proches)[1] if proches else None


# ---------------------------------------------------------------------- la page
def _dessiner_liste(seance: str, trouves: list[dict[str, Any]], noms: list[str], carnet: Path | None) -> str:
    from .ecrans import _e

    attrapees = erreurs_attrapees(trouves)
    choix = "".join(f"<option value=\"{_e(n)}\"{' selected' if n == seance else ''}>{_e(n)}</option>" for n in noms)
    lignes = "".join(
        f"<li>{_e(m['heure'][11:19])} — <b>{_e(m['genre'])}</b> — {_e(m['titre'])} <small>({_e(m['origine'])})</small> "
        f"<a class='bouton' href=\"/clinique/moments/voir?seance={_e(seance)}&amp;m={_e(m['id'])}\">Voir ce moment</a></li>"
        for m in trouves)
    return (f"<form method='get'><label>Séance : <select name='seance' onchange='this.form.submit()'>{choix}</select></label></form>"
            f"<p class='ou'>Lu : la boîte noire « {_e(seance)} »" + (f" et le carnet « {_e(carnet.name)} »" if carnet else
                                                                   " ; aucun carnet de la clinique pour cette séance") +
            ". Heures réelles (UTC). Rien n'est inventé : chaque moment vient d'une ligne écrite pendant la séance.</p>"
            f"<p class='dit' id='attrapees'>Erreurs attrapées : {attrapees['compte']} — {_e(attrapees['texte'])}.</p>"
            f"<h2>{len(trouves)} moment(s), du plus récent au plus ancien</h2>"
            + (f"<ul class='points'>{lignes}</ul>" if lignes else "<p class='rien'>Aucun moment marquant dans cette séance.</p>"))


def _dessiner_moment(seance: str, m: dict[str, Any]) -> str:
    from .ecrans import _e

    def liste(lignes: list[dict[str, str]]) -> str:
        if not lignes:
            return "<p class='rien'>Rien d'écrit dans ces dix secondes.</p>"
        return "<ul>" + "".join(f"<li>{_e(l['heure'])} — {_e(l['quoi'])} <small>({_e(l['origine'])})</small></li>" for l in lignes) + "</ul>"

    q = m["quatre"]
    return (f"<p><a class='bouton' href=\"/clinique/moments?seance={_e(seance)}\">← Tous les moments</a></p>"
            f"<article><h3>{_e(m['genre'])} — {_e(m['titre'])}</h3><p class='ou'>{_e(m['heure'])} (UTC) · {_e(m['origine'])} · "
            f"ligne {_e(m['id'])}</p></article>"
            f"<article><h3>1. Ce que le système a vu ou entendu</h3><p>{_e(q['vu'])}</p></article>"
            f"<article><h3>2. Ce qu'il a décidé, et pourquoi</h3><p>{_e(q['decide'])}</p></article>"
            f"<article><h3>3. Ce qu'il a fait</h3><p>{_e(q['fait'])}</p></article>"
            f"<article><h3>4. Les dix secondes d'avant et d'après</h3><h4>Avant</h4>{liste(q['autour']['avant'])}"
            f"<h4>Après</h4>{liste(q['autour']['apres'])}</article>")


def brancher_moments(app: FastAPI, clinique, protege: list, systeme=None) -> None:
    from .ecrans import _heure_html, _page

    clinique.moments = Seances(clinique=clinique, systeme=systeme)

    def tete() -> str:
        return f"<h1>Moments</h1><span class='heure'>{_heure_html(clinique.horloge.etat())}</span><span>Pour l'équipe</span>"

    def lire_la_seance(seance: str | None):
        noms = clinique.moments.noms()
        if seance is None and noms:
            seance = noms[0]
        if seance is None:
            return None, [], noms, None, []
        try:
            boite, carnet = clinique.moments.chemins(seance)
        except KeyError:
            raise HTTPException(404, "Cette séance n'existe pas sur cet ordinateur. La liste : /clinique/moments")
        entrees = lire_seance(boite, carnet)
        return seance, moments(entrees), noms, carnet if carnet and Path(carnet).exists() else None, entrees

    @app.get("/clinique/moments", response_class=HTMLResponse, dependencies=protege)
    async def page_moments(seance: str | None = None):
        seance, trouves, noms, carnet, _ = lire_la_seance(seance)
        if seance is None:
            return _page("Clinique — Moments", tete(), "<p class='rien'>Aucune séance enregistrée sur cet ordinateur.</p>")
        return _page("Clinique — Moments", tete(), _dessiner_liste(seance, trouves, noms, carnet))

    @app.get("/clinique/moments/voir", response_class=HTMLResponse, dependencies=protege)
    async def page_moment(seance: str, m: str):
        seance, trouves, _, _, _ = lire_la_seance(seance)
        moment = next((x for x in trouves if x["id"] == m), None)
        if moment is None:
            raise HTTPException(404, "Ce moment n'existe pas dans cette séance")
        return _page("Clinique — Un moment", tete(), _dessiner_moment(seance, moment))


# ---------------------------------------------------------------------- la commande
def main(reste: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lancer.py moments", description="La clinique en boîte : les moments d'une séance")
    p.add_argument("fichier", nargs="?", help="une boîte noire (journal/….jsonl) ; par défaut : la plus récente")
    p.add_argument("--carnet", help="le carnet de la même séance (journal/clinique/carnet_….jsonl)")
    args = p.parse_args(reste or [])
    # la plus récente par l'heure du fichier (« dernier_journal » range par nom : « essais_… » passerait toujours devant)
    recentes = sorted(Path(DOSSIER_DEFAUT).glob("*.jsonl"), key=lambda f: f.stat().st_mtime) if Path(DOSSIER_DEFAUT).exists() else []
    boite = Path(args.fichier) if args.fichier else (recentes[-1] if recentes else None)
    if boite is None or not Path(boite).exists():
        print("Aucune boîte noire à lire." if boite is None else f"Fichier absent : {boite}")
        return 2
    trouves = moments(lire_seance(boite, args.carnet))
    attrapees = erreurs_attrapees(trouves)
    print(f"LES MOMENTS — séance {Path(boite).stem} — {len(trouves)} moments, du plus récent au plus ancien — DONNÉES INVENTÉES")
    print(f"Erreurs attrapées : {attrapees['compte']} — {attrapees['texte']}.")
    for m in trouves:
        print(f"- {m['heure'][11:19]} — {m['genre']} — {m['titre']} ({m['origine']}, ligne {m['id']})")
        print(f"    vu : {m['quatre']['vu']}")
        print(f"    décidé : {m['quatre']['decide']}")
        print(f"    fait : {m['quatre']['fait']}")
    return 0
