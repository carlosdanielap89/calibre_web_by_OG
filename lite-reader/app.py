import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, send_file, abort, request, redirect, url_for

app = Flask(__name__)

BOOKS_DIR    = "/books"
DB_PATH      = os.path.join(BOOKS_DIR, "metadata.db")
LITE_DB_PATH = os.path.join(BOOKS_DIR, "lite_reader.db")
CALIBRE_APP_DB = "/config/app.db"
WALL_DIR     = os.path.join(BOOKS_DIR, "wallpapers")

IMAGE_MIMES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
}

# MIME types que el Sony Reader PRS-T1 entiende
MIME_TYPES = {
    ".epub": "application/epub+zip",
    ".pdf":  "application/pdf",
    ".mobi": "application/x-mobipocket-ebook",
}

HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mis Libros - Lite Reader</title>
<style>
  body {
    background: #ffffff;
    color: #000000;
    font-family: sans-serif;
    padding: 10px;
    margin: 0;
  }
  h1 {
    font-size: 22px;
    margin: 0 0 10px 0;
    padding-bottom: 5px;
    border-bottom: 2px solid #000000;
  }
  
  /* Navegacion */
  .nav-bar {
    margin-bottom: 12px;
  }
  .nav-link {
    display: inline-block;
    padding: 6px 12px;
    margin-right: 5px;
    margin-bottom: 5px;
    color: #000000;
    text-decoration: none;
    border: 1px solid #777777;
    background-color: #eeeeee;
    font-size: 15px;
  }
  .nav-link.active {
    background-color: #000000;
    color: #ffffff;
    border-color: #000000;
    font-weight: bold;
  }
  .filter-bar {
    margin-bottom: 15px;
    font-size: 14px;
    border-bottom: 1px solid #cccccc;
    padding-bottom: 8px;
  }
  .filter-link {
    color: #000000;
    text-decoration: underline;
    font-weight: bold;
  }

  /* Grupos */
  .group-title {
    font-size: 16px;
    font-weight: bold;
    background-color: #e5e5e5;
    padding: 5px 8px;
    margin: 15px 0 8px 0;
    border-left: 4px solid #000000;
  }

  /* Listado de libros */
  ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  li {
    border-bottom: 1px solid #dddddd;
    padding: 10px 4px;
  }
  .book-table {
    width: 100%;
    border-collapse: collapse;
    border: 0;
  }
  .book-title {
    font-size: 18px;
    font-weight: bold;
    display: block;
    margin-bottom: 2px;
  }
  .book-author {
    font-size: 13px;
    color: #555555;
    display: block;
    margin-bottom: 6px;
  }
  
  /* Botones de accion */
  .actions {
    margin-top: 4px;
  }
  .btn {
    display: inline-block;
    padding: 6px 12px;
    margin-right: 8px;
    font-size: 14px;
    color: #000000;
    border: 1px solid #000000;
    background-color: #ffffff;
    text-decoration: none;
  }
  .btn-download {
    background-color: #000000;
    color: #ffffff;
    font-weight: bold;
  }
  .btn-hide {
    color: #555555;
    border-color: #888888;
  }
  .btn-show {
    background-color: #dddddd;
    border-color: #555555;
  }
  .btn-delete {
    background-color: #333333;
    color: #ffffff;
    border-color: #222222;
  }

  .empty-msg {
    color: #666666;
    font-style: italic;
    margin: 15px 0;
  }
</style>
</head>
<body>
<h1>&#128218; Biblioteca Lite</h1>

<div class="nav-bar">
  Ver por:
  <a href="/?view=date&show_hidden={{ show_hidden }}" class="nav-link {% if view == 'date' %}active{% endif %}">Fecha Subida</a>
  <a href="/?view=shelves&show_hidden={{ show_hidden }}" class="nav-link {% if view == 'shelves' %}active{% endif %}">Estanterías</a>
  <a href="/?view=all&show_hidden={{ show_hidden }}" class="nav-link {% if view == 'all' %}active{% endif %}">Todos</a>
  <a href="/?view=wallpapers&show_hidden={{ show_hidden }}" class="nav-link {% if view == 'wallpapers' %}active{% endif %}">&#128444; Fondos</a>
</div>

<div class="filter-bar">
  {% if show_hidden %}
    Mostrando todos los libros (incluidos ocultos). 
    <a href="/?view={{ view }}&show_hidden=0" class="filter-link">Ocultar ya descargados</a>
  {% else %}
    Ocultando libros ya descargados/ocultados.
    <a href="/?view={{ view }}&show_hidden=1" class="filter-link">Ver todos</a>
  {% endif %}
</div>

{% if view == 'wallpapers' %}
  {% if groups %}
    {% for group in groups %}
      <div class="group-title">{{ group.name }}</div>
      <ul>
      {% for w in group.books %}
        <li>
          <table class="book-table">
            <tr>
              <td valign="top" style="width: 70px; padding-right: 10px;">
                <img src="/wallpaper-thumb/{{ w.filename }}" width="60" height="60" alt="" style="border: 1px solid #999999; display: block; object-fit: cover;" />
              </td>
              <td valign="top">
                <span class="book-title" style="font-size:16px;">{{ w.name }}</span>
                <span class="book-author">{{ w.info }}</span>
                <div class="actions">
                  <a href="/download-wallpaper/{{ w.filename }}?view=wallpapers&show_hidden={{ show_hidden }}" class="btn btn-download">Descargar</a>
                  {% if w.is_hidden %}
                    <a href="/unhide-wallpaper/{{ w.filename }}?view=wallpapers&show_hidden={{ show_hidden }}" class="btn btn-show">Mostrar</a>
                  {% else %}
                    <a href="/hide-wallpaper/{{ w.filename }}?view=wallpapers&show_hidden={{ show_hidden }}" class="btn btn-hide">Ocultar</a>
                  {% endif %}
                  <a href="/delete-wallpaper/{{ w.filename }}?view=wallpapers&show_hidden={{ show_hidden }}" class="btn btn-delete">Eliminar</a>
                </div>
              </td>
            </tr>
          </table>
        </li>
      {% endfor %}
      </ul>
    {% endfor %}
  {% else %}
    <p class="empty-msg">No hay fondos de pantalla todavía.<br>Envía una foto o imagen al bot de Telegram.</p>
  {% endif %}
{% else %}
{% if groups %}
  {% for group in groups %}
    <div class="group-title">{{ group.name }}</div>
    <ul>
    {% for b in group.books %}
      <li>
        <table class="book-table">
          <tr>
            {% if b.has_cover %}
            <td valign="top" style="width: 55px; padding-right: 10px;">
              <img src="/cover/{{ b.id }}" width="45" height="65" alt="" style="border: 1px solid #999999; display: block;" />
            </td>
            {% endif %}
            <td valign="top">
              <span class="book-title">{{ b.title }}</span>
              <span class="book-author">{{ b.author }}</span>
              <div class="actions">
                <a href="/download/{{ b.id }}/{{ b.filename }}?view={{ view }}&show_hidden={{ show_hidden }}" class="btn btn-download">Descargar</a>
                {% if b.is_hidden %}
                  <a href="/unhide/{{ b.id }}?view={{ view }}&show_hidden={{ show_hidden }}" class="btn btn-show">Mostrar</a>
                {% else %}
                  <a href="/hide/{{ b.id }}?view={{ view }}&show_hidden={{ show_hidden }}" class="btn btn-hide">Ocultar</a>
                {% endif %}
                <a href="/delete-book/{{ b.id }}?view={{ view }}&show_hidden={{ show_hidden }}" class="btn btn-delete">Eliminar</a>
              </div>
            </td>
          </tr>
        </table>
      </li>
    {% endfor %}
    </ul>
  {% endfor %}
{% else %}
  <p class="empty-msg">No se encontraron libros para esta vista.</p>
{% endif %}
{% endif %}

</body>
</html>"""


def init_lite_db():
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hidden_books (
                book_id INTEGER PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hidden_wallpapers (
                filename TEXT PRIMARY KEY
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error initializing lite_reader.db: {e}")


def get_hidden_books():
    if not os.path.exists(LITE_DB_PATH):
        return set()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT book_id FROM hidden_books")
        ids = {row[0] for row in cur.fetchall()}
        conn.close()
        return ids
    except Exception as e:
        print(f"Error reading hidden books: {e}")
        return set()


def hide_book(book_id):
    init_lite_db()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO hidden_books (book_id) VALUES (?)", (book_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error hiding book {book_id}: {e}")


def unhide_book(book_id):
    init_lite_db()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM hidden_books WHERE book_id = ?", (book_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error unhiding book {book_id}: {e}")


def get_shelves_map():
    if not os.path.exists(CALIBRE_APP_DB):
        return {}
    try:
        conn = sqlite3.connect(CALIBRE_APP_DB)
        cur = conn.cursor()
        cur.execute("""
            SELECT s.name, bsl.book_id
            FROM shelf s
            JOIN book_shelf_link bsl ON bsl.shelf = s.id
        """)
        rows = cur.fetchall()
        conn.close()
        
        shelves = {}
        for shelf_name, book_id in rows:
            if shelf_name not in shelves:
                shelves[shelf_name] = []
            shelves[shelf_name].append(book_id)
        return shelves
    except Exception as e:
        print(f"Error querying calibre-web app.db: {e}")
        return {}


def format_date(timestamp_str):
    try:
        # timestamp format: "2026-06-25 04:50:57.635427"
        date_part = timestamp_str.split(" ")[0]
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", 
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"
    except Exception:
        return "Fecha desconocida"


def get_books():
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT b.id, b.title, b.path, b.timestamp,
                   COALESCE(a.name, 'Autor desconocido') as author
            FROM books b
            LEFT JOIN books_authors_link bal ON bal.book = b.id
            LEFT JOIN authors a ON a.id = bal.author
            ORDER BY b.timestamp DESC, b.title ASC
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error reading calibre metadata.db: {e}")
        return []

    books = []
    for row in rows:
        book_path = os.path.join(BOOKS_DIR, row["path"])
        if not os.path.isdir(book_path):
            continue
        for fname in sorted(os.listdir(book_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in MIME_TYPES:
                has_cover = os.path.exists(os.path.join(book_path, "cover.jpg"))
                books.append({
                    "id": row["id"],
                    "title": row["title"],
                    "author": row["author"],
                    "timestamp": row["timestamp"],
                    "filename": fname,
                    "has_cover": has_cover,
                })
                break
    return books


@app.route("/")
def index():
    view = request.args.get("view", "date")
    show_hidden = request.args.get("show_hidden", "0") == "1"

    all_books = get_books()
    hidden_ids = get_hidden_books()

    # Annotate book hidden status
    for b in all_books:
        b["is_hidden"] = b["id"] in hidden_ids

    # Filter books if not showing hidden
    if not show_hidden:
        books_to_show = [b for b in all_books if not b["is_hidden"]]
    else:
        books_to_show = all_books

    groups = []

    if view == "date":
        by_date = {}
        for b in books_to_show:
            date_key = b["timestamp"].split(" ")[0] if b["timestamp"] else "1970-01-01"
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(b)

        # Sort dates descending (newest first)
        for date_key in sorted(by_date.keys(), reverse=True):
            groups.append({
                "name": format_date(date_key) if date_key != "1970-01-01" else "Sin fecha",
                "books": by_date[date_key]
            })

    elif view == "shelves":
        shelves_map = get_shelves_map() # name -> list of book_ids
        books_by_id = {b["id"]: b for b in books_to_show}
        placed_book_ids = set()

        shelf_groups = []
        for shelf_name, book_ids in shelves_map.items():
            shelf_books = []
            for bid in book_ids:
                if bid in books_by_id:
                    shelf_books.append(books_by_id[bid])
                    placed_book_ids.add(bid)
            if shelf_books:
                shelf_books.sort(key=lambda x: x["title"].lower())
                shelf_groups.append({
                    "name": shelf_name,
                    "books": shelf_books
                })
        
        # Sort shelves alphabetically
        shelf_groups.sort(key=lambda x: x["name"].lower())

        # Find books not in any shelf
        unshelved_books = [b for b in books_to_show if b["id"] not in placed_book_ids]
        if unshelved_books:
            unshelved_books.sort(key=lambda x: x["title"].lower())
            shelf_groups.append({
                "name": "Sin estantería",
                "books": unshelved_books
            })

        groups = shelf_groups

    else:
        # view == "all"
        sorted_books = sorted(books_to_show, key=lambda x: x["title"].lower())
        if sorted_books:
            groups.append({
                "name": "Todos los libros",
                "books": sorted_books
            })

    if view == "wallpapers":
        walls = get_wallpapers(show_hidden)
        groups = [{"name": "Fondos de pantalla", "books": walls}] if walls else []

    return render_template_string(
        HTML,
        groups=groups,
        view=view,
        show_hidden=1 if show_hidden else 0
    )


def get_wallpapers(show_hidden: bool) -> list:
    """Returns wallpaper files from WALL_DIR, sorted newest-first."""
    if not os.path.isdir(WALL_DIR):
        return []

    hidden = get_hidden_wallpapers()
    walls  = []
    for fname in sorted(os.listdir(WALL_DIR), reverse=True):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_MIMES:
            continue
        is_hidden = fname in hidden
        if not show_hidden and is_hidden:
            continue
        try:
            size_kb = os.path.getsize(os.path.join(WALL_DIR, fname)) / 1024
        except Exception:
            size_kb = 0
        fmt_map = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                   ".gif": "GIF", ".bmp": "BMP"}
        walls.append({
            "filename":  fname,
            "name":      fname,
            "info":      f"{fmt_map.get(ext, ext.upper())} — {size_kb:.1f} KB",
            "is_hidden": is_hidden,
        })
    return walls


def get_hidden_wallpapers() -> set:
    if not os.path.exists(LITE_DB_PATH):
        return set()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT filename FROM hidden_wallpapers")
        result = {row[0] for row in cur.fetchall()}
        conn.close()
        return result
    except Exception as e:
        print(f"Error reading hidden wallpapers: {e}")
        return set()


def hide_wallpaper(filename: str):
    init_lite_db()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur  = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO hidden_wallpapers (filename) VALUES (?)", (filename,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error hiding wallpaper {filename}: {e}")


def unhide_wallpaper(filename: str):
    init_lite_db()
    try:
        conn = sqlite3.connect(LITE_DB_PATH)
        cur  = conn.cursor()
        cur.execute("DELETE FROM hidden_wallpapers WHERE filename = ?", (filename,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error unhiding wallpaper {filename}: {e}")


@app.route("/hide/<int:book_id>")
def hide(book_id):
    hide_book(book_id)
    view = request.args.get("view", "date")
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view=view, show_hidden=show_hidden))


@app.route("/unhide/<int:book_id>")
def unhide(book_id):
    unhide_book(book_id)
    view = request.args.get("view", "date")
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view=view, show_hidden=show_hidden))


@app.route("/cover/<int:book_id>")
def cover(book_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT path FROM books WHERE id = ?", (book_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            abort(404)

        cover_path = os.path.join(BOOKS_DIR, row[0], "cover.jpg")
        if not os.path.exists(cover_path):
            abort(404)

        return send_file(
            cover_path,
            mimetype="image/jpeg",
        )
    except Exception as e:
        print(f"Error serving cover for book {book_id}: {e}")
        abort(404)


@app.route("/download/<int:book_id>/<path:filename>")
def download(book_id, filename):
    # Auto-hide on download
    hide_book(book_id)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT path FROM books WHERE id = ?", (book_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)

    file_path = os.path.join(BOOKS_DIR, row[0], filename)
    if not os.path.exists(file_path):
        abort(404)

    ext      = os.path.splitext(filename)[1].lower()
    mimetype = MIME_TYPES.get(ext, "application/octet-stream")

    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@app.route("/wallpaper-thumb/<path:filename>")
def wallpaper_thumb(filename):
    safe = os.path.basename(filename)
    path = os.path.join(WALL_DIR, safe)
    if not os.path.exists(path):
        abort(404)
    ext = os.path.splitext(safe)[1].lower()
    return send_file(path, mimetype=IMAGE_MIMES.get(ext, "image/jpeg"))


@app.route("/download-wallpaper/<path:filename>")
def download_wallpaper(filename):
    safe = os.path.basename(filename)
    path = os.path.join(WALL_DIR, safe)
    if not os.path.exists(path):
        abort(404)
    hide_wallpaper(safe)
    ext  = os.path.splitext(safe)[1].lower()
    mime = IMAGE_MIMES.get(ext, "application/octet-stream")
    return send_file(path, mimetype=mime, as_attachment=True, download_name=safe)


@app.route("/hide-wallpaper/<path:filename>")
def hide_wall(filename):
    safe = os.path.basename(filename)
    hide_wallpaper(safe)
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view="wallpapers", show_hidden=show_hidden))


@app.route("/unhide-wallpaper/<path:filename>")
def unhide_wall(filename):
    safe = os.path.basename(filename)
    unhide_wallpaper(safe)
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view="wallpapers", show_hidden=show_hidden))


# ─────────────────────────────────────────────────────────────────────────────
# Delete routes
# ─────────────────────────────────────────────────────────────────────────────

def delete_wallpaper_file(filename: str) -> bool:
    """Deletes wallpaper from disk and removes from hidden_wallpapers table."""
    safe = os.path.basename(filename)
    path = os.path.join(WALL_DIR, safe)
    try:
        if os.path.exists(path):
            os.unlink(path)
        # Clean up hidden_wallpapers table
        try:
            conn = sqlite3.connect(LITE_DB_PATH)
            cur  = conn.cursor()
            cur.execute("DELETE FROM hidden_wallpapers WHERE filename = ?", (safe,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"Error deleting wallpaper {safe}: {e}")
        return False


def delete_book(book_id: int) -> bool:
    """Deletes book from filesystem and from metadata.db. Returns True on success."""
    import shutil as _shutil
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT path FROM books WHERE id = ?", (book_id,))
        row  = cur.fetchone()
        if not row:
            conn.close()
            return False

        book_path = os.path.join(BOOKS_DIR, row[0])

        # Remove from all related tables
        for table, col in [
            ("books_authors_link",    "book"),
            ("books_tags_link",       "book"),
            ("books_ratings_link",    "book"),
            ("books_series_link",     "book"),
            ("books_publishers_link", "book"),
            ("books_languages_link",  "book"),
            ("data",                  "book"),
            ("comments",              "book"),
            ("identifiers",           "book"),
        ]:
            try:
                cur.execute(f"DELETE FROM {table} WHERE {col} = ?", (book_id,))
            except Exception:
                pass

        cur.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        conn.close()

        # Delete filesystem directory
        if os.path.isdir(book_path):
            _shutil.rmtree(book_path)

        # Remove from hidden_books if present
        try:
            lconn = sqlite3.connect(LITE_DB_PATH)
            lcur  = lconn.cursor()
            lcur.execute("DELETE FROM hidden_books WHERE book_id = ?", (book_id,))
            lconn.commit()
            lconn.close()
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"Error deleting book {book_id}: {e}")
        return False


@app.route("/delete-wallpaper/<path:filename>")
def delete_wall(filename):
    safe = os.path.basename(filename)
    delete_wallpaper_file(safe)
    view        = request.args.get("view", "wallpapers")
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view=view, show_hidden=show_hidden))


@app.route("/delete-book/<int:book_id>")
def delete_book_route(book_id):
    delete_book(book_id)
    view        = request.args.get("view", "date")
    show_hidden = request.args.get("show_hidden", "0")
    return redirect(url_for("index", view=view, show_hidden=show_hidden))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084)
