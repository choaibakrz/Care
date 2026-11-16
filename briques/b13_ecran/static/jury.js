// Écran du jury (étape 4). Aucun fichier venu d'Internet : tout est servi par l'ordinateur-cerveau.
// Il lit les événements (WebSocket /ws_simple?complet=1) et montre ce que le robot entend, comprend, décide et fait.
"use strict";
const $ = (s, r = document) => r.querySelector(s);

// ---------------------------------------------------------------- petits outils
function lire(cle, defaut) { try { const v = localStorage.getItem(cle); return v === null ? defaut : v; } catch (e) { return defaut; } }
function garder(cle, v) { try { localStorage.setItem(cle, v); } catch (e) { /* navigateur sans mémoire : tant pis */ } }
function code() { return lire("code_equipe", ""); }

// Les boutons qui changent quelque chose demandent le code d'équipe (une fois, gardé dans ce navigateur).
async function api(chemin, corps) {
  const r = await fetch(chemin, corps === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Code-Equipe": code() }, body: JSON.stringify(corps) });
  if (r.status === 403 && chemin !== "/api/arret_urgence") {
    const c = prompt("Code d'équipe (demandez à la personne responsable) :");
    if (c) { garder("code_equipe", c); return api(chemin, corps); }
    return { ok: false, refuse: true };
  }
  if (!r.ok) return { ok: false, statut: r.status };
  return r.json();
}

const COURT = { fr: "FR", de: "DE", gsw: "CH-DE", it: "IT", en: "EN", zh: "中文" };
const REPONSE = { gsw: "de" }; // le robot répond en allemand au suisse allemand

// Étiquettes de l'écran dans la deuxième langue (le français reste toujours affiché).
const ETIQUETTES = {
  entendu: { de: "Ich habe gehört", it: "Ho sentito", en: "I heard", zh: "我听到了" },
  compris: { de: "Ich habe verstanden", it: "Ho capito", en: "I understood", zh: "我明白了" },
  faire: { de: "Das mache ich", it: "Ora faccio", en: "I will do", zh: "我要做" },
  refus: { de: "Ich lehne ab, weil …", it: "Rifiuto perché…", en: "I refuse because…", zh: "我拒绝，因为……" },
  question: { de: "Ich stelle eine Frage", it: "Faccio una domanda", en: "I ask a question", zh: "我提一个问题" },
  aide: { de: "Ich brauche Hilfe", it: "Ho bisogno di aiuto", en: "I need help", zh: "我需要帮助" },
  personne: { de: "Person", it: "Persona", en: "Person", zh: "人" },
  robot: { de: "Roboter", it: "Robot", en: "Robot", zh: "机器人" },
  demandes: { de: "Anfragen", it: "Richieste", en: "Requests", zh: "请求" },
  reussites: { de: "Erfolge", it: "Riuscite", en: "Successes", zh: "成功" },
  rates: { de: "Fehlschläge", it: "Fallite", en: "Failures", zh: "失败" },
  refusees: { de: "Ablehnungen", it: "Rifiuti", en: "Refusals", zh: "拒绝" },
  questions: { de: "Fragen", it: "Domande", en: "Questions", zh: "提问" },
  aides: { de: "Hilferufe", it: "Richieste di aiuto", en: "Help requests", zh: "求助" },
  humain: { de: "Anteil Mensch", it: "Parte umana", en: "Human share", zh: "人工占比" },
  temps: { de: "Antwortzeit", it: "Tempo di risposta", en: "Response time", zh: "响应时间" },
  internet: { de: "Internet getrennt — alles läuft weiter", it: "Internet staccato — tutto continua",
              en: "Internet cut — everything keeps working", zh: "已断网——一切照常" },
  pilote: { de: "Ein Mensch steuert", it: "Una persona guida", en: "A human is driving", zh: "有人在操控" },  // brique 11
};
const TONS = { refus: "ton-non", rate: "ton-non", arret: "ton-non", panne: "ton-non", aide: "ton-non",
               fait: "ton-ok", question: "ton-attention", internet: "ton-info", silence: "ton-info" };
const IMPORTANTS = new Set(["parole_entendue", "demande_comprise", "gardien_decision", "reponse_dite", "action_demarree",
  "action_terminee", "action_refusee", "aide_demandee", "arret_urgence", "panne", "internet_coupe", "mode_silence",
  "question_posee", "confirmation_demandee"]);
const PANNEAUX = ["entendu", "compris", "faire", "refus", "question", "aide"];

let monde = { lieux: [], objets: [] };
let PICTOS = {};
let langue2 = lire("langue2_jury", "en");
let jury = { internet_coupe: false, silence: false };
// Brique 11 : qui a la main (écran de l'équipe), ou une main humaine annoncée par le chef de démonstration.
let pilote = { qui: null, depuis: null, consigne: null, annoncee: null };
let etat = nouvelEtat();
const traductions = new Map(); // "id|langue" -> {ok, texte, message, comment}
let compteurCoupure = { demandes: 0, reponses: 0 };

function nouvelEtat() { return { conv: null, panneaux: {}, personne: null, robot: null, situation: null }; }

// ---------------------------------------------------------------- textes en français pour l'équipe et le jury
function nomChose(id) {
  if (!id) return "";
  const c = [...monde.lieux, ...monde.objets].find((x) => x.id === id);
  return c ? ((c.noms && c.noms.fr) || [id])[0] : id;
}
function decrire(a) {
  if (!a) return "";
  const p = a.parametres || {};
  const v = p.vitesse != null ? ` · ${p.vitesse} m/s` : "";
  switch (a.nom) {
    case "se_deplacer":
      if (p.lieu) return `aller à : ${nomChose(p.lieu)}${v}`;
      return `me déplacer de ${Math.round(Math.hypot(+p.dx || 0, +p.dy || 0) * 10) / 10} m${v}`;
    case "saisir": return `prendre : ${nomChose(p.objet)}` + (p.force != null ? ` · ${p.force} N` : "");
    case "poser": return "poser l'objet";
    case "regarder": return `regarder : ${nomChose(p.cible)}`;
    case "montrer": return `montrer : ${nomChose(p.cible)}`;
    case "rejouer_geste": return `faire le geste : ${p.nom || "?"}`;
    case "arreter": return "m'arrêter";
    case "etat": return "dire mon état (batterie)";
    case "ecouter": return "écouter";
    case "parler": return "parler";
    default: return a.nom || "";
  }
}
function compris(d) {
  switch (d.genre) {
    case "action": return decrire(d.action);
    case "question": return "Ce n'est pas assez clair : je demande.";
    case "inconnu": return d.confiance_basse ? "Pas sûr d'avoir bien compris : je fais répéter." : "Je n'ai pas compris.";
    case "hors_carte": return "Une action que ce robot ne sait pas faire.";
    case "discussion": return "Une discussion, pas une action.";
    case "confirmation": return d.confirme ? `Oui, vous confirmez : ${decrire(d.action)}` : "Non : j'annule.";
    default: return d.genre || "";
  }
}
const codes = (raisons) => (raisons || []).map((r) => r.code).join(", ");
function raisonsLisibles(raisons) {  // « objet fragile (tasse), humain requis (verser) »
  return (raisons || []).map((r) => {
    const det = r.details || {};
    const noms = det.objet_noms || det.zone_noms || {};
    const quoi = noms.fr || nomChose(det.objet || det.lieu) || det.geste || "";
    const code = String(r.code || "").replace(/_/g, " ");
    return quoi ? `${code} (${quoi})` : code;
  }).join(", ");
}
function ms(x) { return x == null ? "—" : `${Math.round(x)} ms`; }
function statutFr(d) {
  return { reussie: "réussi", ratee: "raté", annulee: "annulé (stop)", refusee: "refusé" }[d.statut] || d.statut || "";
}

// ---------------------------------------------------------------- deuxième langue
function memeLangue(item) {
  if (!item.langue) return false;
  return item.langue === langue2 || (item.sorte === "robot" && (REPONSE[item.langue] || item.langue) === langue2);
}
function deuxieme(item) {
  if (!langue2 || !item || !item.texte) return { texte: "", classe: "" };
  if (memeLangue(item)) return { texte: "(même langue)", classe: "meme" };
  if (!item.id) return { texte: "", classe: "" };
  const cle = `${item.id}|${langue2}|${item.langue || ""}`;
  const t = traductions.get(cle);
  if (!t) { demander(item, cle); return { texte: "…", classe: "attente" }; }
  if (t.attente) return { texte: "…", classe: "attente" };
  if (t.ok) return { texte: t.texte || "—", classe: t.comment === "phrase_connue" || t.comment === "meme_langue" ? "" : "modele" };
  return { texte: t.message || "traduction indisponible hors ligne", classe: "indispo" };
}
function demander(item, cle) {
  traductions.set(cle, { attente: true });
  const de = item.langue ? `&de=${encodeURIComponent(item.langue)}` : "";
  fetch(`/api/traduire/${encodeURIComponent(item.id)}?langue=${encodeURIComponent(langue2)}${de}`)
    .then((r) => (r.ok ? r.json() : { ok: false, message: "traduction indisponible hors ligne" }))
    .then((t) => { traductions.set(cle, t); planifierRendu(); })
    .catch(() => { traductions.delete(cle); });
  if (traductions.size > 400) traductions.delete(traductions.keys().next().value);
}

// ---------------------------------------------------------------- les événements
function suivre(e) {
  if (!e.conversation) return true;
  if (!etat.conv) etat.conv = e.conversation;
  return e.conversation === etat.conv;
}
function poser(nom, p) { etat.panneaux[nom] = p; }
function fusion(nom, p) { etat.panneaux[nom] = { ...(etat.panneaux[nom] || {}), ...p }; }
function nouvelleDemande(conv) {
  etat.conv = conv || null;
  etat.panneaux = {};
}

function surEvenement(e) {
  const d = e.donnees || {};
  const s = e.simple || {};
  switch (e.type) {
    case "session_debut":
      if (d.mention) mention(d.mention);
      break;
    case "transcription":
      if (d.texte) etat.personne = { id: e.id, texte: d.texte, langue: d.langue, sorte: "personne", nouveau: true };
      break;
    case "parole_entendue":
      nouvelleDemande(e.conversation);
      etat.personne = { id: e.id, texte: d.texte, langue: d.langue, sorte: "personne", nouveau: true };
      poser("entendu", { picto: "entendu", item: etat.personne,
        detail: d.confiance != null && d.confiance < 1 ? `confiance de l'écoute : ${d.confiance}` : `par ${e.source}` });
      if (jury.internet_coupe) compteurCoupure.demandes += 1;
      break;
    case "demande_comprise":
      if (!suivre(e)) break;
      if (d.langue && etat.personne && !etat.personne.langue) {  // langue devinée par le cerveau
        etat.personne = { ...etat.personne, langue: d.langue, nouveau: false };
        if (etat.panneaux.entendu) etat.panneaux.entendu.item = etat.personne;
      }
      poser("compris", { picto: s.picto || "compris", texte: compris(d),
        detail: [`cerveau : ${e.source}`, d.confiance != null ? `confiance ${d.confiance}` : "", d.duree_ms != null ? ms(d.duree_ms) : ""]
          .filter(Boolean).join(" · ") });
      break;
    case "gardien_decision":
      if (!suivre(e)) break;
      if (d.verdict === "oui") poser("faire", { picto: s.picto || "faire", texte: decrire(d.action), detail: "vérifié par le gardien" });
      else if (d.verdict === "non") fusion("refus", { picto: "refus", detail: `gardien : ${codes(d.raisons)}` });
      else fusion("aide", { picto: "aide", texte: "Le gardien demande qu'un humain décide.", detail: `gardien : ${d.verdict}` });
      break;
    case "question_posee":
      if (!suivre(e)) break;
      fusion("question", { picto: "question", detail: (d.options || []).length ? `choix : ${(d.options || []).map(decrire).join(" / ")}` : "" });
      break;
    case "confirmation_demandee":
      if (!suivre(e)) break;
      fusion("question", { picto: "question", detail: `action à risque, je demande d'abord : ${decrire(d.action)}` });
      fusion("faire", { second: "seulement après votre « oui »" });
      break;
    case "reponse_dite": {
      etat.robot = { id: e.id, texte: d.texte, langue: d.langue, sorte: "robot", nouveau: true };
      if (jury.internet_coupe) compteurCoupure.reponses += 1;
      if (!suivre(e)) break;
      if (d.cle === "humain_pilote") fusion("compris", { picto: "geste", texte: "Ordre non pris : un humain pilote le robot.",
        detail: "la voix, la tablette et les agents attendent ; seul « stop » passe" });  // brique 11
      else if (d.cle === "confirmation_annulee") fusion("faire", { picto: "parle", texte: "rien : la personne a dit non", item: null });
      else if (d.genre === "refus") fusion("refus", { picto: "refus", item: etat.robot });
      else if (d.genre === "question") fusion("question", { picto: "question", item: etat.robot });
      break;
    }
    case "action_demarree":
      if (!suivre(e)) break;
      fusion("faire", { picto: s.picto || "faire", texte: (etat.panneaux.faire || {}).texte || decrire(d.action),
        second: "en cours…", progression: 0 });
      break;
    case "action_progression":
      if (!suivre(e)) break;
      fusion("faire", { progression: d.progression });
      break;
    case "action_terminee":
      if (!suivre(e)) break;
      fusion("faire", { second: statutFr(d) + (d.message ? ` : ${d.message}` : ""), progression: d.statut === "reussie" ? 1 : null,
        detail: `vérifié par le gardien · ${d.duree_ms != null ? ms(d.duree_ms) : ""}` });
      break;
    case "action_refusee":
      if (!suivre(e)) break;
      fusion("refus", { picto: "refus", detail: `la prise refuse : ${codes(d.raisons)}` });
      break;
    case "aide_demandee":
      if (!d.texte && d.action) {  // venue du gardien : l'action qui attend, et pourquoi (pas le mot « gardien »)
        poser("aide", { picto: "aide", texte: `En attente d'un humain : ${decrire(d.action)}`,
          detail: [`pourquoi : ${raisonsLisibles(d.raisons) || "?"}`, d.numero ? `demande ${d.numero}` : ""]
            .filter(Boolean).join(" · ") });
        break;
      }
      poser("aide", { picto: "aide", texte: String(d.texte || d.raison || d.question || "J'ai besoin qu'un humain m'aide."),
        detail: d.qui ? `demandé à : ${d.qui}` : "" });
      break;
    case "panne":
      poser("aide", { picto: "panne", texte: `Panne : ${d.quoi}`, detail: d.provoquee ? "panne d'entraînement (provoquée exprès)" : (d.consigne || "") });
      break;
    case "reparation":
      if (d.quoi === "rearmement") montrerArret(false);
      if (etat.panneaux.aide && etat.panneaux.aide.picto === "panne") fusion("aide", { second: `réparé : ${d.quoi}` });
      break;
    case "arret_urgence":
      montrerArret(true);
      break;
    case "internet_coupe":
      if (d.coupe) compteurCoupure = { demandes: 0, reponses: 0 };
      jury = { ...jury, internet_coupe: !!d.coupe, preuve: d.preuve || null, etages_eteints: d.etages_eteints || [] };
      montrerJury();
      break;
    case "mode_silence":
      jury = { ...jury, silence: !!d.actif };
      montrerJury();
      break;
    case "pilotage_humain":  // brique 11 : la main humaine (honnêteté : le jury voit quand un humain pilote)
      surPilotage(e, d);
      break;
    default:
      break;
  }
  if (s.picto && IMPORTANTS.has(e.type)) etat.situation = { picto: s.picto, type: e.type };
  planifierRendu();
}

// ---------------------------------------------------------------- brique 11 : la main humaine
function surPilotage(e, d) {
  const ecran = e.source === "main_humaine";  // sinon : annoncée par le chef de démonstration (opérateur simulé, clavier)
  if (d.quoi === "reprise") {
    if (ecran) pilote = { ...pilote, qui: d.qui || "?", depuis: e.heure, consigne: d.consigne || null };
    else pilote = { ...pilote, annoncee: { qui: d.qui || d.operateur || e.source, consigne: d.consigne || null, depuis: e.heure } };
  } else if (d.quoi === "rendu") {
    if (ecran) pilote = { ...pilote, qui: null, depuis: null, consigne: null }; else pilote = { ...pilote, annoncee: null };
  } else if (d.quoi === "ordre") {
    // Un bouton de l'humain qui pilote : pas une phrase, pas de cerveau. La suite (gardien, robot) a la même conversation.
    nouvelleDemande(e.conversation);
    poser("entendu", { picto: "geste", texte: `Ordre de l'humain qui pilote (${d.qui || "?"}) : ${decrire(d.action)}`,
      detail: "bouton de l'écran de l'équipe — pas une phrase" });
    poser("compris", { picto: "compris", texte: decrire(d.action), detail: "pas de cerveau : un formulaire, puis le gardien" });
  } else if (d.quoi === "demande") {
    poser("aide", { picto: "aide", texte: "Le chef de démonstration demande qu'un humain prenne la main.", detail: d.consigne || "" });
  } else if (d.quoi === "demande_retiree") {
    fusion("aide", { second: `demande retirée : ${d.raison || ""}` });
  }
  montrerPilote();
}
function montrerPilote() {
  const b = $("#bandeau-pilote");
  if (!b) return;
  const p = pilote, a = p.annoncee;
  b.hidden = !p.qui && !a;
  document.body.classList.toggle("pilote", !b.hidden);
  if (b.hidden) return;
  let titre, qui, detail;
  if (p.qui) {
    titre = "UN HUMAIN PILOTE";
    qui = p.qui;
    detail = [p.depuis ? `depuis ${heureLocale(p.depuis)}` : "", "la voix et les agents ne commandent pas le robot (seul « stop » passe)",
      "chaque ordre passe par le gardien", p.consigne ? `consigne : ${p.consigne}` : ""].filter(Boolean).join(" · ");
  } else {
    const simulee = /simul/i.test(String(a.qui));
    titre = simulee ? "MAIN HUMAINE SIMULÉE" : "MAIN HUMAINE";
    qui = simulee ? "répétition : personne ne pilote vraiment" : String(a.qui);
    detail = ["annoncée par le chef de démonstration", a.consigne ? `consigne : ${a.consigne}` : ""].filter(Boolean).join(" · ");
  }
  $("#pilote-titre").textContent = titre;
  $("#pilote-qui").textContent = qui;
  $("#pilote-detail").textContent = detail;
}
function heureLocale(iso) { try { return new Date(iso).toLocaleTimeString(); } catch (e) { return ""; } }

// ---------------------------------------------------------------- dessin
let renduPrevu = false;
function planifierRendu() { if (!renduPrevu) { renduPrevu = true; setTimeout(() => { renduPrevu = false; rendre(); }, 30); } }
function picto(svg, nom) { const u = svg.querySelector("use"); if (u) u.setAttribute("href", `#p-${nom || "parle"}`); }
function texte(el, t, classe) { el.textContent = t || ""; if (classe !== undefined) el.className = `txt ${classe}`; }

function rendreSousTitre(id, item) {
  const bloc = $(id);
  const l1 = $(".l1", bloc), l2 = $(".l2", bloc);
  if (!item) {
    texte($(".txt", l1), id === "#st-personne" ? "En attente d'une phrase…" : "");
    texte($(".txt", l2), "", "");
    $(".lg", l1).textContent = ""; $(".lg", l2).textContent = "";
    return;
  }
  $(".lg", l1).textContent = COURT[item.langue] || (item.langue || "").toUpperCase();
  texte($(".txt", l1), item.sorte === "personne" ? `« ${item.texte} »` : item.texte);
  const t = deuxieme(item);
  $(".lg", l2).textContent = langue2 && t.texte ? (COURT[langue2] || langue2.toUpperCase()) : "";
  texte($(".txt", l2), t.texte, t.classe);
  if (item.nouveau) {
    item.nouveau = false;
    bloc.classList.remove("nouveau"); void bloc.offsetWidth; bloc.classList.add("nouveau");
  }
}

function rendre() {
  rendreSousTitre("#st-personne", etat.personne);
  rendreSousTitre("#st-robot", etat.robot);
  for (const nom of PANNEAUX) {
    const el = $(`#pan-${nom}`);
    const p = etat.panneaux[nom];
    el.dataset.actif = p ? "1" : "0";
    picto($(".grand", el), (p && p.picto) || { entendu: "entendu", compris: "compris", faire: "faire", refus: "refus",
      question: "question", aide: "aide" }[nom]);
    let principal = "", second = "";
    if (p && p.item) {
      principal = p.item.sorte === "personne" ? `« ${p.item.texte} »` : p.item.texte;
      const t = deuxieme(p.item);
      second = t.texte && t.classe !== "meme" ? `${COURT[langue2] || ""} ${t.texte}` : "";
    } else if (p) {
      principal = p.texte || "";
    }
    if (p && p.second) second = second ? `${second} · ${p.second}` : p.second;
    $(".principal", el).textContent = principal;
    $(".second", el).textContent = second;
    $(".detail", el).textContent = (p && p.detail) || "";
    const barre = $(".barre", el);
    if (barre) {
      const montrer = p && p.progression != null;
      barre.hidden = !montrer;
      if (montrer) $("span", barre).style.width = `${Math.round(Math.max(0, Math.min(1, p.progression)) * 100)}%`;
    }
  }
  const sit = $("#situation");
  const nom = etat.situation ? etat.situation.picto : (jury.silence ? "silence" : "entendu");
  picto($("svg", sit), nom);
  $("svg", sit).setAttribute("aria-label", PICTOS[nom] || nom);
  $("figcaption", sit).textContent = etat.situation ? (PICTOS[nom] || nom) : "en attente";
  sit.className = `situation ${TONS[nom] || ""}`;
}

function remplirEtiquettes() {
  document.querySelectorAll("[data-etiquette]").forEach((el) => {
    const t = ETIQUETTES[el.dataset.etiquette] || {};
    el.textContent = langue2 && langue2 !== "fr" ? (t[langue2] || "") : "";
  });
}

function mention(m) {
  for (const el of [$("#mention-haut"), $("#f-mention")]) el.textContent = m;
}

function montrerArret(actif) { $("#bandeau-arret").hidden = !actif; }

function montrerJury() {
  document.body.classList.toggle("silence", !!jury.silence);
  document.body.classList.toggle("coupe", !!jury.internet_coupe);
  $("#b-silence").setAttribute("aria-pressed", jury.silence ? "true" : "false");
  $("#b-internet").setAttribute("aria-pressed", jury.internet_coupe ? "true" : "false");
  $("#pastille-silence").hidden = !jury.silence;
  $("#bandeau-internet").hidden = !jury.internet_coupe;
  if (jury.internet_coupe) {
    const morceaux = [];
    if (jury.depuis) morceaux.push(`depuis ${jury.depuis}`);
    morceaux.push(`${compteurCoupure.demandes} demande(s) traitée(s), ${compteurCoupure.reponses} réponse(s)`);
    if (jury.connexions_refusees != null) morceaux.push(`${jury.connexions_refusees} sortie(s) vers Internet refusée(s)`);
    if ((jury.etages_eteints || []).length) morceaux.push(`éteint : ${jury.etages_eteints.join(", ")}`);
    if (jury.preuve) morceaux.push(jury.preuve);
    (jury.limites || []).forEach((l) => morceaux.push(`limite : ${l}`));
    $("#preuve-internet").textContent = morceaux.join(" · ");
  }
}

// ---------------------------------------------------------------- fiche de vérité et état
function mettre(id, v) { const el = $(id); if (el) el.textContent = v; }
async function rafraichirFiche() {
  let f;
  try { f = await api("/api/fiche"); } catch (e) { return; }
  if (!f || f.ok === false) return;
  mettre("#f-demandes", f.demandes);
  mettre("#f-reussites", f.reussites);
  mettre("#f-reussites-d", f.reussites_pilotees ? `dont ${f.reussites_pilotees} par l'humain` : "");  // brique 11
  mettre("#f-rates", f.rates);
  mettre("#f-refus", f.refus_gardien + f.refus_prise);
  mettre("#f-refus-d", `gardien ${f.refus_gardien} · prise ${f.refus_prise}`);
  mettre("#f-questions", f.questions_posees);
  mettre("#f-questions-d", f.confirmations_demandees ? `+ ${f.confirmations_demandees} confirmation(s)` : "");
  mettre("#f-aides", f.aides_demandees);
  mettre("#f-humain", f.part_humain_pct);
  mettre("#f-humain-d", [f.ordres_humains ? `${f.ordres_humains} ordre(s) de l'humain` : "",
    f.part_humain_simulee_pct ? `+ ${f.part_humain_simulee_pct} % simulée (répétition)` : ""].filter(Boolean).join(" · "));
  const t = f.temps_premiere_reponse || {};
  mettre("#f-temps", t.mediane_ms == null ? "—" : Math.round(t.mediane_ms));
  const voix = f.temps_fin_de_phrase_a_reponse || {};
  mettre("#f-temps-d", ["médiane", t.max_ms != null ? `max ${ms(t.max_ms)}` : "", voix.mediane_ms != null ? `voix ${ms(voix.mediane_ms)}` : ""]
    .filter(Boolean).join(" · "));
  mention(f.mention);
  mettre("#f-mention-d", `fiche de vérité · arrêts d'urgence : ${f.arrets_urgence}`);
}
async function rafraichirEtat() {
  try {
    const e = await api("/api/etat");
    montrerArret(!!e.arret_urgence_actif);
    const l = $("#liaison");
    l.textContent = e.liaison_ok ? `liaison ok · batterie ${e.batterie_pct ?? "?"} %` : "liaison perdue";
    l.className = `pastille ${e.liaison_ok ? "ok" : "non"}`;
  } catch (err) { /* le serveur redémarre */ }
}
async function rafraichirJury() {
  try { const j = await api("/api/jury/etat"); jury = { ...jury, ...j }; PICTOS = j.pictos || PICTOS; montrerJury(); } catch (e) { /* idem */ }
  try {  // brique 11 : la vérité du serveur sur qui a la main (si un événement a été manqué)
    const m = await api("/api/main_humaine?court=1");
    if (m && m.ok !== false) { pilote = { qui: m.qui, depuis: m.depuis, consigne: (m.consigne || {}).texte || null, annoncee: m.annoncee }; montrerPilote(); }
  } catch (e) { /* idem */ }
}

// ---------------------------------------------------------------- liaison en direct
function connecter() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws_simple?complet=1&historique=200`);
  ws.onopen = () => { etat = nouvelEtat(); };
  ws.onmessage = (m) => { try { surEvenement(JSON.parse(m.data)); } catch (err) { console.warn("événement illisible", err); } };
  ws.onclose = () => setTimeout(connecter, 1000);
}

// ---------------------------------------------------------------- boutons
function theme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  const bouton = $("#b-theme");
  const sombre = t === "dark" || (!t && matchMedia("(prefers-color-scheme: dark)").matches);
  bouton.setAttribute("aria-pressed", String(sombre));
  bouton.setAttribute("aria-label", sombre ? "Passer au mode clair" : "Passer au mode sombre");
  bouton.title = bouton.getAttribute("aria-label");
  bouton.querySelector(".theme-label").textContent = sombre ? "Clair" : "Sombre";
}
$("#b-theme").addEventListener("click", () => {
  const sombre = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const t = sombre ? "light" : "dark";
  theme(t); garder("theme_jury", t);
});
$("#langue2").addEventListener("change", (ev) => {
  langue2 = ev.target.value; garder("langue2_jury", langue2); remplirEtiquettes(); planifierRendu();
});
$("#b-internet").addEventListener("click", async () => {
  const r = await api("/api/internet_coupe", { coupe: !jury.internet_coupe });
  if (r && r.ok !== false) { jury = { ...jury, ...r }; montrerJury(); }
});
$("#b-silence").addEventListener("click", async () => {
  const r = await api("/api/mode_silence", { actif: !jury.silence });
  if (r && r.ok !== false) { jury = { ...jury, ...r }; montrerJury(); planifierRendu(); }
});
$("#arret").addEventListener("click", () => api("/api/arret_urgence", {}));
$("#rearmer").addEventListener("click", async () => { await api("/api/rearmer", {}); rafraichirEtat(); });
$("#ecrire").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const t = $("#texte").value.trim();
  if (!t) return;
  $("#texte").value = "";
  await api("/api/dire", { texte: t, langue: $("#langue-dite").value || null });
});

// ---------------------------------------------------------------- démarrage
(async () => {
  theme(lire("theme_jury", ""));
  $("#langue2").value = langue2;
  if ($("#langue2").value !== langue2) { langue2 = ""; }
  remplirEtiquettes();
  try {
    const [carte, j, m] = await Promise.all([api("/api/carte"), api("/api/jury/etat"), api("/api/monde")]);
    $("#nom-robot").textContent = `${carte.nom} (${carte.genre})`;
    mention(carte.mention);
    monde = m; PICTOS = j.pictos || {}; jury = { ...jury, ...j };
    montrerJury();
  } catch (e) { console.warn("démarrage : serveur injoignable", e); }
  connecter();
  await Promise.all([rafraichirFiche(), rafraichirEtat(), rafraichirJury()]);
  setInterval(rafraichirFiche, 1000);
  setInterval(rafraichirEtat, 1000);
  setInterval(rafraichirJury, 2000);
  rendre();
  document.body.dataset.pret = "1";
})();
