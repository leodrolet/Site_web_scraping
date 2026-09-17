"use strict";
// Améliorations facultatives : tous les formulaires fonctionnent sans JavaScript.
const filtreMandat = document.getElementById("filtre-mandat");
if (filtreMandat) {
  filtreMandat.addEventListener("change", () => {
    let visibles = 0;
    document.querySelectorAll("#mandat-organisations tbody tr").forEach(row => {
      const choix = filtreMandat.value;
      row.hidden = !(choix === "toutes" || (choix === "pilote" ? Number(row.dataset.index) <= 5 : row.dataset.statut === choix));
      if (!row.hidden) visibles++;
    });
    document.getElementById("mandat-filtre-vide").hidden = visibles > 0;
  });
}
const formulairesModifies = new Set();
document.querySelectorAll("[data-mandat-form]").forEach(form => {
  form.addEventListener("input", () => formulairesModifies.add(form));
});
window.addEventListener("beforeunload", event => {
  if (formulairesModifies.size) { event.preventDefault(); event.returnValue = ""; }
});
document.querySelectorAll("form").forEach(form => {
  form.addEventListener("submit", event => {
    const autres = [...formulairesModifies].filter(f => f !== form);
    if (autres.length && !window.confirm("Un autre formulaire contient des modifications non enregistrées. Continuer et les abandonner ?")) {
      event.preventDefault(); return;
    }
    formulairesModifies.clear();
    if (form.hasAttribute("data-mandat-submit")) {
      const bouton = form.querySelector('button[type="submit"]');
      if (bouton) { bouton.disabled = true; bouton.textContent = "Traitement en cours…"; }
    }
  });
});
