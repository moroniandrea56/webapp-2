"""
email_sender.py
================
Invio via email del quadro BrainArt al partecipante — la finalità che
l'informativa privacy dichiara ("l'eventuale invio successivo del file")
ma che finora non esisteva come funzione reale.

Configurazione (variabili d'ambiente):
    BRAINART_SMTP_HOST
    BRAINART_SMTP_PORT      (default 587)
    BRAINART_SMTP_USER
    BRAINART_SMTP_PASSWORD
    BRAINART_SMTP_FROM      (default: uguale a BRAINART_SMTP_USER)

Se non configurato, smtp_configured() restituisce False e
send_artwork_email() solleva EmailNotConfiguredError invece di fallire
in modo silenzioso o bloccare l'avvio del server.
"""

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.environ.get("BRAINART_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("BRAINART_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("BRAINART_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("BRAINART_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("BRAINART_SMTP_FROM", SMTP_USER)


class EmailNotConfiguredError(RuntimeError):
    """Nessun server SMTP configurato: impossibile inviare l'email."""


def smtp_configured():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_artwork_email(to_email, to_first_name, personal_url, stimulus_label, png_bytes, filename):
    """Invia un'email con il quadro allegato e il link alla pagina personale.

    Solleva EmailNotConfiguredError se le variabili SMTP non sono impostate,
    così il chiamante può restituire un errore chiaro invece di un crash.
    """
    if not smtp_configured():
        raise EmailNotConfiguredError(
            "Invio email non configurato: imposta BRAINART_SMTP_HOST, "
            "BRAINART_SMTP_USER e BRAINART_SMTP_PASSWORD."
        )

    msg = MIMEMultipart()
    msg["Subject"] = "Il tuo quadro BrainArt è pronto"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    body = (
        f"Ciao {to_first_name},\n\n"
        f"in allegato trovi il tuo quadro BrainArt, generato dalla tua esperienza "
        f"({stimulus_label}).\n\n"
        f"Puoi rivedere la tua pagina personale, con tutti i dettagli della sessione, qui:\n"
        f"{personal_url}\n\n"
        f"— BrainArt"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    attachment = MIMEApplication(png_bytes, _subtype="png")
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())
