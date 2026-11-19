"""Templates e-mail AngaPanel (HTML simple + logo inline)."""
from __future__ import annotations

import html
from email.mime.image import MIMEImage
from pathlib import Path

from django.core.mail import EmailMultiAlternatives

_ASSETS = Path(__file__).resolve().parent / "mail_assets"
_LOGO_CANDIDATES = (
    _ASSETS / "angapanel-logo-64.png",
    _ASSETS / "angapanel-logo.png",
)


def logo_png_path() -> Path | None:
    for p in _LOGO_CANDIDATES:
        if p.is_file():
            return p
    return None


def _escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def password_reset_bodies(
    *,
    username: str,
    reset_link: str,
    code_display: str,
    ttl_minutes: int,
) -> tuple[str, str]:
    """Retourne (texte brut, html)."""
    u = username.strip() or "utilisateur"
    plain = (
        f"Bonjour {u},\n\n"
        f"Une demande de réinitialisation de mot de passe a été reçue pour votre compte AngaPanel.\n\n"
        f"1) Ouvrez ce lien (valide {ttl_minutes} minutes, usage unique) :\n"
        f"{reset_link}\n\n"
        f"2) Saisissez exactement ce code de vérification :\n"
        f"RESET-CODE: {code_display}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail. "
        f"Votre mot de passe actuel reste inchangé.\n\n"
        f"Ne répondez pas à ce message automatique.\n"
        f"AngaPanel\n"
    )

    eu = _escape(u)
    elink = _escape(reset_link)
    ecode = _escape(code_display)
    html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AngaPanel — mot de passe</title>
</head>
<body style="margin:0;padding:0;background:#eef2f6;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a2f45;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f6;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:480px;background:#ffffff;border:1px solid #d7e0ea;border-radius:12px;overflow:hidden;">
          <tr>
            <td style="padding:22px 24px 12px 24px;border-bottom:1px solid #e8eef4;">
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="vertical-align:middle;padding-right:12px;">
                    <img src="cid:angapanel_logo" width="40" height="40" alt="AngaPanel" style="display:block;border:0;border-radius:8px;" />
                  </td>
                  <td style="vertical-align:middle;">
                    <div style="font-size:18px;font-weight:700;letter-spacing:0.2px;color:#1a2f45;">Anga<span style="color:#ff6c2c;">Panel</span></div>
                    <div style="font-size:12px;color:#6b7c8f;margin-top:2px;">Réinitialisation du mot de passe</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 24px 8px 24px;font-size:15px;line-height:1.55;color:#243b55;">
              Bonjour <strong>{eu}</strong>,
              <br /><br />
              Une demande de réinitialisation a été reçue pour votre compte. Utilisez le bouton ci-dessous, puis saisissez le code e-mail.
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:8px 24px 18px 24px;">
              <a href="{elink}" style="display:inline-block;background:#ff6c2c;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:8px;">
                Réinitialiser mon mot de passe
              </a>
            </td>
          </tr>
          <tr>
            <td style="padding:0 24px 8px 24px;font-size:12px;color:#6b7c8f;line-height:1.45;">
              Lien valable <strong>{int(ttl_minutes)} minutes</strong>, usage unique. Si le bouton ne fonctionne pas, copiez cette URL :
              <br />
              <a href="{elink}" style="color:#2a6fad;word-break:break-all;">{elink}</a>
            </td>
          </tr>
          <tr>
            <td style="padding:12px 24px 22px 24px;">
              <div style="font-size:12px;font-weight:600;color:#6b7c8f;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.06em;">Code de vérification</div>
              <div style="font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:22px;font-weight:700;letter-spacing:0.18em;color:#1a2f45;background:#f4f7fb;border:1px solid #d7e0ea;border-radius:8px;padding:14px 16px;text-align:center;">
                {ecode}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 24px 22px 24px;border-top:1px solid #e8eef4;font-size:12px;line-height:1.5;color:#8a9bb0;">
              Si vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail — votre mot de passe actuel reste inchangé.
              <br /><br />
              Ne répondez pas à ce message automatique.
              <br />
              <span style="color:#1a2f45;font-weight:600;">AngaPanel</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return plain, html_body


def send_branded_mail(
    *,
    subject: str,
    to: str,
    from_email: str,
    text_body: str,
    html_body: str,
) -> int:
    """Envoie texte + HTML avec logo AngaPanel en pièce jointe CID."""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[to],
    )
    msg.attach_alternative(html_body, "text/html")
    logo = logo_png_path()
    if logo is not None:
        with logo.open("rb") as fh:
            image = MIMEImage(fh.read(), _subtype="png")
        image.add_header("Content-ID", "<angapanel_logo>")
        image.add_header("Content-Disposition", "inline", filename="angapanel-logo.png")
        msg.attach(image)
        # Related multipart so CID resolves in clients
        msg.mixed_subtype = "related"
    return msg.send(fail_silently=False)
