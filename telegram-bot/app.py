import os
import logging
import tempfile
import requests
from datetime import datetime
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

TOKEN       = os.getenv("TELEGRAM_TOKEN")
CW_URL      = os.getenv("CALIBRE_WEB_URL", "http://calibre-web:8083")
CW_USER     = os.getenv("CALIBRE_USER", "admin")
CW_PASS     = os.getenv("CALIBRE_PASS", "admin123")
BOOKS_DIR   = "/books"
WALL_DIR    = os.path.join(BOOKS_DIR, "wallpapers")

ALLOWED_BOOK_EXTS  = {".epub", ".pdf", ".mobi", ".azw3", ".cbz", ".cbr"}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}


def get_session() -> tuple[requests.Session, str]:
    """Inicia sesión en Calibre-Web.
    Devuelve (session, csrf_token).
    Calibre-Web usa Flask-WTF, todos los POST necesitan CSRF."""
    s = requests.Session()
    # 1) GET /login → obtener CSRF token
    login_page = s.get(f"{CW_URL}/login", timeout=10)
    csrf_token = ""
    import re as _re
    m = _re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_page.text)
    if m:
        csrf_token = m.group(1)
    # 2) POST /login con CSRF
    s.post(
        f"{CW_URL}/login",
        data={
            "username": CW_USER,
            "password": CW_PASS,
            "remember_me": "on",
            "csrf_token": csrf_token,
        },
        timeout=10,
    )
    # 3) Refrescar CSRF para los siguientes requests (la sesión ya está activa)
    upload_page = s.get(f"{CW_URL}/upload", timeout=10)
    m2 = _re.search(r'name="csrf_token"[^>]*value="([^"]+)"', upload_page.text)
    if m2:
        csrf_token = m2.group(1)
    return s, csrf_token


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 *Bienvenido a tu biblioteca personal*\n\n"
        "📖 *Libros* — Envíame un archivo de libro y lo subiré a Calibre-Web:\n"
        "  `.epub` `.pdf` `.mobi` `.azw3` `.cbz` `.cbr`\n\n"
        "🖼️ *Fondos de pantalla* — Envíame una foto (o imagen como archivo) y\n"
        "  la guardaré para descargarla en tu Sony PRS-T1:\n"
        "  `.jpg` `.jpeg` `.png` `.gif` `.bmp`\n\n"
        "La imagen se verá mejor si tiene resolución *600 x 800 px*.",
        parse_mode="Markdown",
    )


def ensure_wall_dir():
    os.makedirs(WALL_DIR, exist_ok=True)


def unique_filename(directory: str, filename: str) -> str:
    """Retorna un nombre único añadiendo sufijo numérico si el archivo ya existe."""
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return filename
    stem = Path(filename).stem
    ext  = Path(filename).suffix
    i = 1
    while os.path.exists(os.path.join(directory, f"{stem}_{i}{ext}")):
        i += 1
    return f"{stem}_{i}{ext}"


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """El usuario envió una foto comprimida por Telegram."""
    photo = update.message.photo[-1]  # Mayor resolución disponible
    msg   = await update.message.reply_text("⏳ Descargando imagen…")
    tg_file = await ctx.bot.get_file(photo.file_id)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"fondo_{timestamp}.jpg"

    ensure_wall_dir()
    fname = unique_filename(WALL_DIR, fname)
    dest  = os.path.join(WALL_DIR, fname)

    try:
        await tg_file.download_to_drive(dest)
        await msg.edit_text(
            f"🖼️ *{fname}* guardado como fondo de pantalla.\n"
            "Ya puedes descargarlo desde la pestaña *Fondos* en tu Sony.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(e)
        await msg.edit_text(f"❌ Error guardando imagen: {e}")


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    fname = doc.file_name or "archivo"
    ext   = Path(fname).suffix.lower()

    # ── Imagen → guardar como fondo de pantalla ───────────────────────────────
    if ext in ALLOWED_IMAGE_EXTS:
        msg = await update.message.reply_text("⏳ Descargando imagen…")
        tg_file = await ctx.bot.get_file(doc.file_id)
        ensure_wall_dir()
        safe_fname = unique_filename(WALL_DIR, fname)
        dest = os.path.join(WALL_DIR, safe_fname)
        try:
            await tg_file.download_to_drive(dest)
            await msg.edit_text(
                f"🖼️ *{safe_fname}* guardado como fondo de pantalla.\n"
                "Ya puedes descargarlo desde la pestaña *Fondos* en tu Sony.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(e)
            await msg.edit_text(f"❌ Error guardando imagen: {e}")
        return

    # ── Libro → subir a Calibre-Web ───────────────────────────────────────────
    if ext not in ALLOWED_BOOK_EXTS:
        await update.message.reply_text(
            f"❌ Formato *{ext}* no reconocido.\n\n"
            f"📖 Libros: {', '.join(sorted(ALLOWED_BOOK_EXTS))}\n"
            f"🖼️ Imágenes: {', '.join(sorted(ALLOWED_IMAGE_EXTS))}",
            parse_mode="Markdown",
        )
        return

    msg = await update.message.reply_text("⏳ Descargando libro…")
    tg_file = await ctx.bot.get_file(doc.file_id)

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)
        await msg.edit_text("📤 Subiendo a Calibre-Web…")

        session, csrf_token = get_session()
        with open(tmp_path, "rb") as f:
            resp = session.post(
                f"{CW_URL}/upload",
                files={"btn-upload": (fname, f)},
                data={"csrf_token": csrf_token},
                timeout=60,
            )

        if resp.status_code in (200, 302):
            await msg.edit_text(f"✅ *{fname}* añadido a tu biblioteca.", parse_mode="Markdown")
        else:
            await msg.edit_text(f"⚠️ Error HTTP {resp.status_code} al subir.")
    except Exception as e:
        logging.error(e)
        await msg.edit_text(f"❌ Error inesperado: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    logging.info("Bot iniciado…")
    app.run_polling()


if __name__ == "__main__":
    main()
