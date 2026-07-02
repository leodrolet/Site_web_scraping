// app.js — interactions minimales (onglets, progression, révélations au scroll)

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
      // On garde une éventuelle icône : on ne remplace que le texte.
      var libelle = bouton.querySelector('.btn-libelle');
      if (libelle) { libelle.textContent = 'Recherche en cours…'; }
      else { bouton.textContent = 'Recherche en cours…'; }
    }
    if (prog) { prog.hidden = false; }
  });
});

// --- Révélations douces au scroll (respecte prefers-reduced-motion) ---
(function () {
  var cibles = document.querySelectorAll('.reveal');
  if (!cibles.length) { return; }

  var reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduit || !('IntersectionObserver' in window)) {
    cibles.forEach(function (el) { el.classList.add('vu'); });
    return;
  }

  var obs = new IntersectionObserver(function (entrees) {
    entrees.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add('vu');
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  cibles.forEach(function (el) { obs.observe(el); });
})();
