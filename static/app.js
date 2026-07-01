// app.js — interactions minimales (onglets, progression)

// --- Onglets de l'application ---
document.querySelectorAll('.tab').forEach(function (bouton) {
  bouton.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('actif'); });
    document.querySelectorAll('.panneau').forEach(function (p) { p.hidden = true; });
    bouton.classList.add('actif');
    var cible = document.getElementById(bouton.dataset.cible);
    if (cible) { cible.hidden = false; }
  });
});

// --- Indicateur de progression au moment de soumettre une recherche ---
document.querySelectorAll('form[data-loading]').forEach(function (form) {
  form.addEventListener('submit', function () {
    var bouton = form.querySelector('button[type="submit"]');
    var prog = form.querySelector('.progress');
    if (bouton) {
      bouton.disabled = true;
      bouton.textContent = 'Recherche en cours…';
    }
    if (prog) { prog.hidden = false; }
  });
});
