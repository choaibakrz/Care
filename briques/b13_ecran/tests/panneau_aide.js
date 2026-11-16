// Test sans navigateur (Node seulement) : jury.js reçoit une demande d'aide du gardien, et le panneau « J'ai besoin
// d'aide » montre l'action et les raisons (pas le mot « gardien »). Lancé par test_jury.py ; rien n'est installé.
// La page est chargée avec un faux « document » : chaque élément est un objet vide qui accepte tout.
"use strict";
const fs = require("fs");
const vm = require("vm");

process.on("unhandledRejection", () => {});  // le démarrage de la page échoue sans serveur : c'est voulu
const rien = new Proxy(function () {}, {
  get: (_cible, cle) => {
    if (cle === Symbol.iterator) return function* () {};
    if (cle === Symbol.toPrimitive) return () => "";
    if (cle === "then") return undefined;  // pas une promesse
    return rien;
  },
  set: () => true,
  apply: () => rien,
});
const contexte = {
  document: rien, window: rien, localStorage: { getItem: () => null, setItem: () => {} },
  fetch: () => Promise.reject(new Error("pas de serveur")), WebSocket: function () { return rien; },
  setInterval: () => 0, setTimeout: () => 0, clearTimeout: () => {}, requestAnimationFrame: () => 0,
  console: { log() {}, warn() {}, error() {} }, location: { host: "test", protocol: "http:" },
  matchMedia: () => ({ matches: false, addEventListener() {} }), navigator: {},
};
vm.createContext(contexte);
vm.runInContext(fs.readFileSync(process.argv[2], "utf-8"), contexte, { filename: "jury.js" });
vm.runInContext(`monde = { lieux: [], objets: [{ id: "tasse", noms: { fr: ["tasse"] } }] };`, contexte);
const evenements = JSON.parse(process.argv[3]);
const panneaux = evenements.map((e) => vm.runInContext(
  `nouvelleDemande(null); surEvenement(${JSON.stringify(e)}); JSON.stringify(etat.panneaux.aide || null)`, contexte));
console.log(JSON.stringify(panneaux.map((p) => JSON.parse(p))));
