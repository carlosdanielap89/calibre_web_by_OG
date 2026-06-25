import os
import sqlite3
from flask import Flask, render_template_string, send_file, abort

app = Flask(__name__)

BOOKS_DIR = "/books"
DB_PATH = os.path.join(BOOKS_DIR, "metadata.db")

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
<title>Mis libros</title>
<style>
  body { background:#fff; color:#000; font-family:serif; font-size:16px; padding:8px; }
  h1   { font-size:20px; margin-bottom:12px; }
  ul   { list-style:none; padding:0; margin:0; }
  li   { border-bottom:1px solid #aaa; padding:10px 4px; }
  a    { color:#000; text-decoration:none; font-size:18px; display:block; }
  .author { font-size:13px; color:#555; }
  .empty  { color:#888; }
</style>
</head>
<body>
<h1>&#128218; Mis libros</h1>
{% if books %}
<ul>
{% for b in books %}
<li>
  <a href="/download/{{ b.book_id }}/{{ b.filename }}">&#8681; {{ b.title }}</a>
  <span class="author">{{ b.author }}</span>
</li>
{% endfor %}
</ul>
{% else %}
<p class="empty">No hay libros todavia. Sube alguno desde Calibre-Web.</p>
{% endif %}
</body>
</html>"""


def get_books():
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, b.title, b.path,
               COALESCE(a.name, 'Autor desconocido') as author
        FROM books b
        LEFT JOIN books_authors_link bal ON bal.book = b.id
        LEFT JOIN authors a ON a.id = bal.author
        ORDER BY b.title
    """)
    rows = cur.fetchall()
    conn.close()

    books = []
    for row in rows:
        book_path = os.path.join(BOOKS_DIR, row["path"])
        if not os.path.isdir(book_path):
            continue
        for fname in sorted(os.listdir(book_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in MIME_TYPES:
                books.append({
                    "book_id": row["id"],
                    "title":   row["title"],
                    "author":  row["author"],
                    "filename": fname,
                })
                break
    return books


@app.route("/")
def index():
    books = get_books()
    return render_template_string(HTML, books=books)


@app.route("/download/<int:book_id>/<path:filename>")
def download(book_id, filename):
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084)
