// Écran minimal de l'étape 1. Aucun fichier venu d'Internet : tout est servi par l'ordinateur-cerveau.
const $ = (s) => document.querySelector(s);
let monde = null, etat = null;

function themeInitial() {
  try { return localStorage.getItem("theme_ecran") || "light"; } catch (e) { return "light"; }
}
function appliquerTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const bouton = $("#theme");
  if (!bouton) return;
  const sombre = theme === "dark";
  bouton.textContent = sombre ? "☀" : "☾";
  bouton.setAttribute("aria-label", sombre ? "Passer au thème clair" : "Passer au thème sombre");
  bouton.title = bouton.getAttribute("aria-label");
}
appliquerTheme(themeInitial());

// Code d'équipe : demandé une fois sur les ordinateurs du Wi-Fi, gardé dans ce navigateur seulement.
function code() { try { return localStorage.getItem("code_equipe") || ""; } catch (e) { return ""; } }
async function api(chemin, corps) {
  const r = await fetch(chemin, corps === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Code-Equipe": code() }, body: JSON.stringify(corps) });
  if (r.status === 403 && chemin !== "/api/arret_urgence") {
    const c = prompt("Code d'équipe (demandez à la personne responsable) :");
    if (c) { try { localStorage.setItem("code_equipe", c); } catch (e) {} return api(chemin, corps); }
  }
  return r.json();
}

function texteEvenement(e) {
  const d = e.donnees || {};
  switch (e.type) {
    case "parole_entendue": return ["", `🗣 [${d.langue || "?"}] « ${d.texte} »`];
    case "demande_comprise": return ["", `🧠 ${d.genre} ${(d.action && d.action.nom) || ""} · confiance ${d.confiance} · ${d.duree_ms} ms`];
    case "gardien_decision": return [d.verdict === "oui" ? "ok" : "non", `🛡 gardien : ${d.verdict} ${(d.raisons || []).map(r => r.code).join(", ")}`];
    case "action_demarree": return ["", `🤖 démarre ${d.action.nom}`];
    case "action_terminee": return [d.statut === "reussie" ? "ok" : "non", `🤖 ${d.statut} ${d.message || ""}`];
    case "action_refusee": return ["non", `⛔ prise : ${(d.raisons || []).map(r => r.code).join(", ")}`];
    case "reponse_dite": return ["dit", `💬 [${d.langue}] ${d.texte}`];
    case "question_posee": return ["dit", `❓ ${d.question}`];
    case "arret_urgence": return ["non", `🛑 ARRÊT D'URGENCE (${d.raison})`];
    case "panne": return ["non", `⚠ panne : ${d.quoi}`];
    case "transcription": return ["", `👂 [${d.langue}] « ${d.texte} » · confiance ${d.confiance} · ${d.calcul_ms} ms`];
    case "voix_debut": return d.latence_ms ? ["", `⏱ réponse ${d.latence_ms} ms après la fin de la phrase`] : null;
    case "interruption": return ["", "✋ interruption : le robot se tait"];
    case "mot_d_appel": return ["", "👂 mot d'appel entendu"];
    case "confirmation_demandee": return ["dit", `❔ ${d.question}`];
    // Étape 4 (briques 7 et 8) : la main levée, l'aide reçue, une règle changée. Boutons : /api/aides, /api/aide/repondre.
    case "aide_demandee": return ["non", `✋ LE ROBOT LÈVE LA MAIN (${d.raison})${d.numero ? " · demande n° " + d.numero : ""} ${(d.raisons || []).map(r => r.code).join(", ")}`];
    case "aide_recue": return ["ok", `🤝 aide reçue : ${d.sorte}${d.mot ? " « " + d.mot + " » = " + d.sens : ""}${d.accepte === undefined ? "" : (d.accepte ? " (acceptée)" : " (refusée)")} · ${d.qui || ""}`];
    case "regle_changee": return ["", `📜 règle changée : ${d.regle} (${d.comment}, ${d.qui}) → ${(d.apres && d.apres.phrase) || "retirée"}`];
    case "pilotage_humain": return ["dit", `👤 main humaine : ${d.quoi} · ${d.qui || d.operateur || ""}${d.action ? " · " + d.action.nom : ""}${d.raison ? " · " + d.raison : ""}`];  // brique 11
    case "parole_finie": return null;
    case "action_progression": return null;
    default: return ["", `· ${e.type}`];
  }
}

function ajouter(e) {
  const t = texteEvenement(e);
  if (!t) return;
  const li = document.createElement("li");
  li.className = t[0];
  const h = document.createElement("span"); h.className = "h"; h.textContent = e.heure.slice(11, 19);
  li.append(h, document.createTextNode(t[1]));
  const ol = $("#journal");
  ol.prepend(li);
  while (ol.children.length > 300) ol.lastChild.remove();
}

function connecter() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (m) => ajouter(JSON.parse(m.data));
  ws.onclose = () => setTimeout(connecter, 1000);
}

function dessiner() {
  const c = $("#monde"), g = c.getContext("2d");
  if (!monde) return;
  const sx = c.width / monde.taille.largeur, sy = c.height / monde.taille.hauteur;
  const X = (x) => x * sx, Y = (y) => c.height - y * sy;
  const css = getComputedStyle(document.documentElement);
  g.clearRect(0, 0, c.width, c.height);
  g.font = "14px system-ui"; g.fillStyle = css.getPropertyValue("--doux");
  for (const l of monde.lieux) {
    g.strokeStyle = css.getPropertyValue("--bord"); g.strokeRect(X(l.position.x) - 30, Y(l.position.y) - 20, 60, 40);
    g.fillText(l.noms.fr[0], X(l.position.x) - 28, Y(l.position.y) - 24);
  }
  if (etat) {
    const objets = (etat.extra && etat.extra.objets) || {};
    for (const [id, p] of Object.entries(objets)) {
      g.fillStyle = css.getPropertyValue("--attention");
      g.beginPath(); g.arc(X(p[0]), Y(p[1]), 6, 0, 7); g.fill();
      g.fillText(id, X(p[0]) + 8, Y(p[1]) + 4);
    }
    g.strokeStyle = css.getPropertyValue("--info"); g.beginPath();
    (etat.trace || []).forEach((p, i) => i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1])));
    g.stroke();
    const p = etat.position || {};
    if (p.x !== undefined) {
      g.fillStyle = etat.arret_urgence_actif ? "#c1121f" : css.getPropertyValue("--texte");
      g.beginPath(); g.arc(X(p.x), Y(p.y), 12, 0, 7); g.fill();
      const a = (p.cap || 0) * Math.PI / 180;
      g.strokeStyle = g.fillStyle; g.beginPath(); g.moveTo(X(p.x), Y(p.y));
      g.lineTo(X(p.x) + 22 * Math.cos(a), Y(p.y) - 22 * Math.sin(a)); g.stroke();
    }
  }
}

async function rafraichir() {
  try {
    etat = await api("/api/etat");
    const ex = etat.extra || {};
    $("#etat").textContent = `Batterie ${etat.batterie_pct ?? "?"} % · tient : ${etat.objet_tenu || "rien"} · ` +
      `geste : ${ex.dernier_geste || "—"} · pannes : ${(ex.pannes || []).join(", ") || "aucune"}` +
      (etat.arret_urgence_actif ? " · ARRÊT D'URGENCE ACTIF" : "");
    const l = $("#liaison"); l.textContent = etat.liaison_ok ? "liaison ok" : "liaison perdue";
    l.className = "pastille " + (etat.liaison_ok ? "ok" : "non");
    dessiner();
  } catch (e) { /* le serveur redémarre */ }
}

async function rafraichirFiche() {
  const f = await api("/api/fiche");
  const lignes = [["Mention", f.mention], ["Demandes", f.demandes], ["Réussites", f.reussites_pilotees ? `${f.reussites} (dont ${f.reussites_pilotees} par l'humain)` : f.reussites], ["Ratés", f.rates],
    ["Refus du gardien", f.refus_gardien], ["Questions posées", f.questions_posees], ["Aides demandées", f.aides_demandees], ["Aides reçues", f.aides_recues],
    ["Part de l'humain", f.part_humain_pct + " %" + (f.part_humain_simulee_pct ? ` (+ ${f.part_humain_simulee_pct} % simulée)` : "")],
    ["Ordres de l'humain", f.ordres_humains],
    ["Arrêts d'urgence", f.arrets_urgence],
    ["1re réponse (médiane)", (f.temps_premiere_reponse.mediane_ms ?? "—") + " ms"],
    ["Fin de phrase → réponse parlée", (f.temps_fin_de_phrase_a_reponse.mediane_ms ?? "—") + " ms"],
    ["Interruptions", f.interruptions], ["Confirmations demandées", f.confirmations_demandees]];
  for (const [lg, v] of Object.entries(f.par_langue)) lignes.push([`Non compris [${lg}]`, `${v.non_comprises}/${v.demandes}`]);
  const t = $("#fiche"); t.replaceChildren();
  for (const [a, b] of lignes) { const tr = t.insertRow(); tr.insertCell().textContent = a; tr.insertCell().textContent = b; }
}

$("#formulaire").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const texte = $("#texte").value.trim(); if (!texte) return;
  $("#texte").value = "";
  await api("/api/dire", { texte, langue: $("#langue").value || null });
});
$("#theme").addEventListener("click", () => {
  const prochain = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  appliquerTheme(prochain);
  try { localStorage.setItem("theme_ecran", prochain); } catch (e) { /* navigateur sans mémoire */ }
});
$("#arret").addEventListener("click", () => api("/api/arret_urgence", {}));
$("#rearmer").addEventListener("click", () => api("/api/rearmer", {}));
$("#reparer").addEventListener("click", () => api("/api/reparer", {}));
document.querySelectorAll("[data-panne]").forEach(b => b.addEventListener("click", () => api("/api/panne", { nom: b.dataset.panne })));

(async () => {
  const m = await api("/api/micro");
  if (m.micro) {
    const b = $("#je-parle"); b.hidden = false;
    // Les requêtes partent l'une après l'autre (jamais « relâcher » avant « appuyer »).
    let file = Promise.resolve(), appuye = false;
    const envoyer = (v) => { if (v === appuye) return; appuye = v; file = file.then(() => api("/api/je_parle", { appui: v })); };
    b.addEventListener("pointerdown", (e) => { e.preventDefault(); b.setPointerCapture(e.pointerId); envoyer(true); });
    for (const ev of ["pointerup", "pointercancel", "lostpointercapture"]) b.addEventListener(ev, () => envoyer(false));
    // Sécurité en plus : le serveur relâche tout seul après 15 s.
  }
  const carte = await api("/api/carte");
  $("#nom-robot").textContent = `${carte.nom} (${carte.genre})`;
  $("#mention").textContent = carte.mention;
  monde = await api("/api/monde");
  connecter();
  setInterval(rafraichir, 200);
  setInterval(rafraichirFiche, 1000);
})();
