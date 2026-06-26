import os
import shutil
import logging
import tempfile
import requests
from datetime import datetime
from pathlib import Path
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

TOKEN     = os.getenv("TELEGRAM_TOKEN")
CW_URL    = os.getenv("CALIBRE_WEB_URL", "http://calibre-web:8083")
CW_USER   = os.getenv("CALIBRE_USER", "admin")
CW_PASS   = os.getenv("CALIBRE_PASS", "admin123")
BOOKS_DIR = "/books"
WALL_DIR  = os.path.join(BOOKS_DIR, "wallpapers")

ALLOWED_BOOK_EXTS  = {".epub", ".pdf", ".mobi", ".azw3", ".cbz", ".cbr"}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

# Sony PRS-T1 screen
SONY_W, SONY_H = 600, 800
SONY_RATIO     = SONY_W / SONY_H   # 0.75 (portrait)
JPEG_QUALITY   = 65

# Pending crop decisions: user_id -> {tmp_path, dest_path, orientation, src_ext}
pending_crops: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Calibre-Web session
# ─────────────────────────────────────────────────────────────────────────────

def get_session() -> tuple:
    """Log into Calibre-Web. Returns (session, csrf_token)."""
    import re as _re
    s = requests.Session()
    login_page = s.get(f"{CW_URL}/login", timeout=10)
    csrf_token = ""
    m = _re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_page.text)
    if m:
        csrf_token = m.group(1)
    s.post(
        f"{CW_URL}/login",
        data={"username": CW_USER, "password": CW_PASS,
              "remember_me": "on", "csrf_token": csrf_token},
        timeout=10,
    )
    upload_page = s.get(f"{CW_URL}/upload", timeout=10)
    m2 = _re.search(r'name="csrf_token"[^>]*value="([^"]+)"', upload_page.text)
    if m2:
        csrf_token = m2.group(1)
    return s, csrf_token


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────

def ensure_wall_dir():
    os.makedirs(WALL_DIR, exist_ok=True)


def unique_filename(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return filename
    stem = Path(filename).stem
    ext  = Path(filename).suffix
    i = 1
    while os.path.exists(os.path.join(directory, f"{stem}_{i}{ext}")):
        i += 1
    return f"{stem}_{i}{ext}"


def needs_crop(img: Image.Image) -> str | None:
    """
    Returns crop orientation if ratio differs from Sony 0.75 by >15%/30%.
    'horizontal' -> image wider than Sony -> ask left/center/right
    'vertical'   -> image much taller    -> ask top/center/bottom
    None         -> ratio close enough, just thumbnail-resize
    """
    w, h  = img.size
    ratio = w / h
    if ratio > SONY_RATIO * 1.15:
        return "horizontal"
    if ratio < SONY_RATIO * 0.70:
        return "vertical"
    return None


def apply_crop_and_resize(img: Image.Image, orientation: str,
                          position: str) -> Image.Image:
    """Crops to 600:800 ratio then resizes to 600x800."""
    w, h = img.size
    if orientation == "horizontal":
        new_w = int(h * SONY_RATIO)
        offsets = {"left": 0, "right": w - new_w, "center": (w - new_w) // 2}
        left = offsets.get(position, (w - new_w) // 2)
        img  = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / SONY_RATIO)
        offsets = {"top": 0, "bottom": h - new_h, "center": (h - new_h) // 2}
        top = offsets.get(position, (h - new_h) // 2)
        img = img.crop((0, top, w, top + new_h))
    return img.resize((SONY_W, SONY_H), Image.LANCZOS)


def save_wallpaper(tmp_path: str, dest_path: str, src_ext: str,
                   orientation: str | None = None,
                   position: str = "center") -> tuple:
    """Processes and saves wallpaper. Returns (orig_kb, comp_kb)."""
    orig_kb = os.path.getsize(tmp_path) // 1024

    if src_ext == ".gif":
        shutil.copy2(tmp_path, dest_path)
        return orig_kb, os.path.getsize(dest_path) // 1024

    with Image.open(tmp_path) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if orientation:
            img = apply_crop_and_resize(img, orientation, position)
        else:
            img.thumbnail((SONY_W, SONY_H), Image.LANCZOS)
        img.save(dest_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    return orig_kb, os.path.getsize(dest_path) // 1024


# ─────────────────────────────────────────────────────────────────────────────
# Telegram handlers
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📚 *Bienvenido a tu biblioteca personal*\n\n"
        "📖 *Libros* — Envíame un archivo y lo subiré a Calibre-Web:\n"
        "  `.epub`  `.pdf`  `.mobi`  `.azw3`  `.cbz`  `.cbr`\n\n"
        "🖼️ *Fondos de pantalla* — Envíame una foto o imagen:\n"
        "  `.jpg`  `.jpeg`  `.png`  `.gif`  `.bmp`\n"
        "  La recortaré y optimizaré para tu Sony PRS-T1 (600×800 px).",
        parse_mode="Markdown",
    )


async def process_image(update: Update, tg_file,
                        fname: str, src_ext: str, msg) -> None:
    """Downloads image, checks ratio, crops or asks user, saves wallpaper."""
    ensure_wall_dir()

    with tempfile.NamedTemporaryFile(suffix=src_ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await tg_file.download_to_drive(tmp_path)

        # GIF: save as-is
        if src_ext == ".gif":
            dest_fname = unique_filename(WALL_DIR, Path(fname).stem + ".gif")
            dest_path  = os.path.join(WALL_DIR, dest_fname)
            orig_kb, comp_kb = save_wallpaper(tmp_path, dest_path, ".gif")
            await msg.edit_text(
                f"🖼️ *{dest_fname}* guardado.\n"
                f"📦 {orig_kb} KB\n"
                "Ya puedes descargarlo desde la pestaña *Fondos* en tu Sony.",
                parse_mode="Markdown",
            )
            os.unlink(tmp_path)
            return

        # Check if crop is needed
        with Image.open(tmp_path) as img:
            orientation = needs_crop(img)

        dest_fname = unique_filename(WALL_DIR, Path(fname).stem + ".jpg")
        dest_path  = os.path.join(WALL_DIR, dest_fname)

        if orientation:
            # Ask user which part to keep
            user_id = update.effective_user.id
            pending_crops[user_id] = {
                "tmp_path":    tmp_path,
                "dest_path":   dest_path,
                "orientation": orientation,
                "src_ext":     src_ext,
            }
            if orientation == "horizontal":
                caption = (f"📐 *{fname}* es horizontal.\n"
                           "¿Qué parte de la imagen conservar?")
                buttons = [
                    InlineKeyboardButton("⬅️ Izquierda", callback_data="crop:left"),
                    InlineKeyboardButton("⬛ Centro",     callback_data="crop:center"),
                    InlineKeyboardButton("➡️ Derecha",   callback_data="crop:right"),
                ]
            else:
                caption = (f"📐 *{fname}* es muy alta.\n"
                           "¿Qué parte de la imagen conservar?")
                buttons = [
                    InlineKeyboardButton("⬆️ Arriba", callback_data="crop:top"),
                    InlineKeyboardButton("⬛ Centro",  callback_data="crop:center"),
                    InlineKeyboardButton("⬇️ Abajo",  callback_data="crop:bottom"),
                ]
            await msg.edit_text(
                caption, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([buttons]),
            )
            # tmp_path kept; cleaned up in callback
        else:
            # Good ratio -> just resize
            orig_kb, comp_kb = save_wallpaper(tmp_path, dest_path, src_ext)
            await msg.edit_text(
                f"🖼️ *{dest_fname}* guardado como fondo de pantalla.\n"
                f"📦 {orig_kb} KB → {comp_kb} KB (e-ink 600×800 px)\n"
                "Ya puedes descargarlo desde la pestaña *Fondos* en tu Sony.",
                parse_mode="Markdown",
            )
            os.unlink(tmp_path)

    except Exception as e:
        logging.error(e)
        await msg.edit_text(f"❌ Error procesando imagen: {e}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def handle_crop_callback(update: Update,
                               ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when user taps a crop position button."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in pending_crops:
        await query.edit_message_text(
            "⚠️ No hay imagen pendiente. Envíame una imagen primero.")
        return

    pending  = pending_crops.pop(user_id)
    position = query.data.split(":")[1]

    try:
        orig_kb, comp_kb = save_wallpaper(
            tmp_path    = pending["tmp_path"],
            dest_path   = pending["dest_path"],
            src_ext     = pending["src_ext"],
            orientation = pending["orientation"],
            position    = position,
        )
        fname  = os.path.basename(pending["dest_path"])
        labels = {"left": "Izquierda ⬅️", "center": "Centro ⬛",
                  "right": "Derecha ➡️", "top": "Arriba ⬆️", "bottom": "Abajo ⬇️"}
        await query.edit_message_text(
            f"✅ *{fname}* guardado.\n"
            f"✂️ Recortado: {labels.get(position, position)}\n"
            f"📦 {orig_kb} KB → {comp_kb} KB (e-ink 600×800 px)\n"
            "Ya puedes descargarlo desde la pestaña *Fondos* en tu Sony.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(e)
        await query.edit_message_text(f"❌ Error al recortar: {e}")
    finally:
        try:
            os.unlink(pending["tmp_path"])
        except Exception:
            pass


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User sent a compressed photo."""
    photo     = update.message.photo[-1]
    msg       = await update.message.reply_text("⏳ Analizando imagen…")
    tg_file   = await ctx.bot.get_file(photo.file_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    await process_image(update, tg_file, f"fondo_{timestamp}.jpg", ".jpg", msg)


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    fname = doc.file_name or "archivo"
    ext   = Path(fname).suffix.lower()

    # ── Image ─────────────────────────────────────────────────────────────────
    if ext in ALLOWED_IMAGE_EXTS:
        msg     = await update.message.reply_text("⏳ Analizando imagen…")
        tg_file = await ctx.bot.get_file(doc.file_id)
        await process_image(update, tg_file, fname, ext, msg)
        return

    # ── Book ──────────────────────────────────────────────────────────────────
    if ext not in ALLOWED_BOOK_EXTS:
        await update.message.reply_text(
            f"❌ *{ext}* no es compatible con el Sony PRS-T1.\n\n"
            f"📖 *Formatos de libro aceptados:*\n"
            f"  `{chr(10).join(sorted(ALLOWED_BOOK_EXTS))}`\n\n"
            f"🖼️ *Formatos de imagen aceptados:*\n"
            f"  `{chr(10).join(sorted(ALLOWED_IMAGE_EXTS))}`",
            parse_mode="Markdown",
        )
        return

    msg     = await update.message.reply_text("⏳ Descargando libro…")
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
            await msg.edit_text(
                f"✅ *{fname}* añadido a tu biblioteca.", parse_mode="Markdown")
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


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not TOKEN:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_crop_callback, pattern="^crop:"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    logging.info("Bot iniciado…")
    app.run_polling()


if __name__ == "__main__":
    main()
