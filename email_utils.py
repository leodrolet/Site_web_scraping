"""
email_utils.py — Envoi des courriels transactionnels via Resend (API HTTP).

Réutilise `requests` (déjà utilisé pour Hunter/Apollo/SerpAPI) : aucune nouvelle
dépendance. Les identifiants Resend sont lus côté serveur depuis l'environnement
(RESEND_API_KEY / RESEND_FROM_EMAIL) et ne transitent jamais par le HTML/JS.
"""

import requests

import config

_URL = "https://api.resend.com/emails"
_SITE = "ProspectB2B"


def _html_confirmation(lien: str) -> str:
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#0E1524">
  <h2 style="color:#0E1524">Bienvenue sur {_SITE}</h2>
  <p>Merci de ton inscription. Confirme ton adresse courriel pour commencer à
     utiliser l'outil de prospection.</p>
  <p style="margin:28px 0">
    <a href="{lien}"
       style="background:#2F54EB;color:#fff;text-decoration:none;padding:12px 22px;
              border-radius:8px;font-weight:600;display:inline-block">
      Confirmer mon adresse
    </a>
  </p>
  <p style="color:#5A6577;font-size:14px">
    Ce lien expire dans 48 heures. Si tu n'es pas à l'origine de cette inscription,
    ignore simplement ce message.
  </p>
  <p style="color:#8A93A6;font-size:13px;word-break:break-all">
    Si le bouton ne fonctionne pas, copie ce lien dans ton navigateur :<br>{lien}
  </p>
</div>"""


def _html_reset(lien: str) -> str:
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#0E1524">
  <h2 style="color:#0E1524">Réinitialisation de mot de passe</h2>
  <p>Tu as demandé à réinitialiser ton mot de passe {_SITE}. Clique le bouton
     ci-dessous pour en choisir un nouveau.</p>
  <p style="margin:28px 0">
    <a href="{lien}"
       style="background:#2F54EB;color:#fff;text-decoration:none;padding:12px 22px;
              border-radius:8px;font-weight:600;display:inline-block">
      Choisir un nouveau mot de passe
    </a>
  </p>
  <p style="color:#5A6577;font-size:14px">
    Ce lien expire dans 1 heure. Si tu n'es pas à l'origine de cette demande,
    ignore ce message — ton mot de passe reste inchangé.
  </p>
  <p style="color:#8A93A6;font-size:13px;word-break:break-all">
    Si le bouton ne fonctionne pas, copie ce lien :<br>{lien}
  </p>
</div>"""


def _envoyer(destinataire: str, sujet: str, html: str) -> bool:
    """Envoi générique via Resend. Lève en cas d'échec (clé absente/réseau/erreur)."""
    cle = (config.RESEND_API_KEY or "").strip()
    expediteur = (config.RESEND_FROM_EMAIL or "").strip()
    if not cle or not expediteur:
        raise RuntimeError("Resend non configuré (RESEND_API_KEY / RESEND_FROM_EMAIL).")

    rep = requests.post(
        _URL,
        headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json"},
        json={"from": expediteur, "to": [destinataire], "subject": sujet, "html": html},
        timeout=config.TIMEOUT,
    )
    if rep.status_code >= 400:
        raise RuntimeError(f"Resend a répondu {rep.status_code}")
    return True


def envoyer_confirmation(destinataire: str, lien: str) -> bool:
    """Courriel de confirmation d'adresse. Lève en cas d'échec (l'appelant gère)."""
    return _envoyer(destinataire, f"Confirme ton adresse — {_SITE}",
                    _html_confirmation(lien))


def envoyer_reinitialisation(destinataire: str, lien: str) -> bool:
    """Courriel de réinitialisation de mot de passe. Lève en cas d'échec."""
    return _envoyer(destinataire, f"Réinitialise ton mot de passe — {_SITE}",
                    _html_reset(lien))
