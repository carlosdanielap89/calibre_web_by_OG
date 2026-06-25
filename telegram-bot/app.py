import os
import logging
import tempfile
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

TOKEN    = os.getenv("TELEGRAM_TOKEN")
CW_URL   = os.getenv("CALIBRE_WEB_URL", "http://calibre-web:8083")
CW_USER  = os.getenv("CALIBRE_USER", "admin")
CW_PASS  = os.getenv("CALIBRE_PASS", "admin123")

ALLOWED_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".cbz", ".cbr"}


def get_session() -> requests.Session:
    """Inicia sesión en Calibre-Web y devuelve la sesión autenticada."""
    s = requests.Session()
    s.post(
        f"{CW_URL}/login",
        data={"username": CW_USER, "password": CW_PASS, "remember_me": "on"},
        timeout=10,
    )
    return s


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 *Bienvenido a tu biblioteca personal*\n\n"
        "Envíame cualquier libro y lo añadiré automáticamente a Calibre-Web.\n\n"
        "Formatos aceptados: `.epub` `.pdf` `.mobi` `.azw3` `.cbz` `.cbr`",
        parse_mode="Markdown",
    )


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    fname = doc.file_name or "libro.epub"
    ext   = Path(fname).suffix.lower()

    if ext not in ALLOWED_EXTS:
        await update.message.reply_text(
            f"❌ Formato *{ext}* no soportado.\n"
            f"Formatos válidos: {', '.join(sorted(ALLOWED_EXTS))}",
            parse_mode="Markdown",
        )
        return

    msg = await update.message.reply_text("⏳ Descargando…")

    tg_file = await ctx.bot.get_file(doc.file_id)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        await msg.edit_text("📤 Subiendo a Calibre-Web…")

        session = get_session()
        with open(tmp_path, "rb") as f:
            resp = session.post(
                f"{CW_URL}/upload",
                files={"btn-upload": (fname, f)},
                timeout=60,
            )

        if resp.status_code in (200, 302):
            await msg.edit_text(f"✅ *{fname}* añadido a tu biblioteca.", parse_mode="Markdown")
        else:
            await msg.edit_text(
                f"⚠️ Calibre-Web respondió HTTP {resp.status_code}. "
                "Verifica que el usuario tenga permisos de subida."
            )
    except Exception as e:
        logging.error(e)
        await msg.edit_text(f"❌ Error inesperado: {e}")
    finally:
        os.unlink(tmp_path)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    logging.info("Bot iniciado…")
    app.run_polling()


if __name__ == "__main__":
    main()
