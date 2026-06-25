import os
import time
import logging
import tempfile
import requests
from pathlib import Path
from imap_tools import MailBox, AND

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

IMAP_HOST     = os.getenv("IMAP_HOST")
IMAP_USER     = os.getenv("IMAP_USER")
IMAP_PASS     = os.getenv("IMAP_PASS")
IMAP_PORT     = int(os.getenv("IMAP_PORT", "993"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "120"))   # segundos

CW_URL  = os.getenv("CALIBRE_WEB_URL", "http://calibre-web:8083")
CW_USER = os.getenv("CALIBRE_USER", "admin")
CW_PASS = os.getenv("CALIBRE_PASS", "admin123")

ALLOWED_EXTS = {".epub", ".pdf", ".mobi", ".azw3"}


def get_session() -> requests.Session:
    s = requests.Session()
    s.post(
        f"{CW_URL}/login",
        data={"username": CW_USER, "password": CW_PASS, "remember_me": "on"},
        timeout=10,
    )
    return s


def upload_to_calibre(session: requests.Session, fname: str, data: bytes) -> bool:
    ext = Path(fname).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            resp = session.post(
                f"{CW_URL}/upload",
                files={"btn-upload": (fname, f)},
                timeout=60,
            )
        success = resp.status_code in (200, 302)
        logging.info(f"Upload '{fname}': HTTP {resp.status_code} → {'OK' if success else 'FAIL'}")
        return success
    finally:
        os.unlink(tmp_path)


def process_inbox() -> int:
    """Revisa el buzón y sube los adjuntos nuevos. Devuelve el número de libros subidos."""
    uploaded = 0
    with MailBox(IMAP_HOST, port=IMAP_PORT).login(IMAP_USER, IMAP_PASS, "INBOX") as mbox:
        msgs = list(mbox.fetch(AND(seen=False)))
        if not msgs:
            return 0

        session = get_session()

        for msg in msgs:
            for att in msg.attachments:
                ext = Path(att.filename).suffix.lower()
                if ext not in ALLOWED_EXTS:
                    logging.info(f"Ignorando adjunto '{att.filename}' (formato no soportado)")
                    continue
                if upload_to_calibre(session, att.filename, att.payload):
                    uploaded += 1

            # Marcar el correo como leído para no procesarlo dos veces
            mbox.flag([msg.uid], ["\\Seen"], True)

    return uploaded


def main() -> None:
    if not all([IMAP_HOST, IMAP_USER, IMAP_PASS]):
        raise RuntimeError("Faltan variables de entorno: IMAP_HOST, IMAP_USER, IMAP_PASS")

    logging.info(
        f"Mail-receiver iniciado. "
        f"Buzón: {IMAP_USER}@{IMAP_HOST} | "
        f"Intervalo: {POLL_INTERVAL}s"
    )

    while True:
        try:
            n = process_inbox()
            if n:
                logging.info(f"✅ {n} libro(s) subido(s) a Calibre-Web.")
        except Exception as e:
            logging.error(f"Error al revisar buzón: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
