import sqlite3

DB_PATH = "bot.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Crea las tablas si no existen."""
    with get_connection() as conn:
        cur = conn.cursor()

        # Búsquedas del usuario
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                size TEXT,
                min_price REAL,
                max_price REAL,
                include_words TEXT,
                exclude_words TEXT,
                url TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Artículos ya vistos (para no avisar otra vez)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                search_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                PRIMARY KEY (search_id, item_id),
                FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
            )
            """
        )

        conn.commit()


def add_search(
    user_id: int,
    query: str,
    size: str | None,
    min_price: float | None,
    max_price: float | None,
    include_words: str | None,
    exclude_words: str | None,
    url: str,
):
    """Añade una búsqueda nueva para un usuario."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO searches (
                user_id, query, size, min_price, max_price,
                include_words, exclude_words, url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, query, size, min_price, max_price, include_words, exclude_words, url),
        )
        conn.commit()


def get_searches(user_id: int):
    """Devuelve las búsquedas de un usuario."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, query, size, min_price, max_price,
                   include_words, exclude_words, url, created_at
            FROM searches
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        )
        return cur.fetchall()


def get_all_searches():
    """Devuelve todas las búsquedas de todos los usuarios."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, url, min_price, max_price,
                   include_words, exclude_words
            FROM searches
            """
        )
        return cur.fetchall()


def get_seen_items(search_id: int):
    """Devuelve los IDs de artículos ya vistos para una búsqueda."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT item_id FROM seen_items WHERE search_id = ?",
            (search_id,),
        )
        rows = cur.fetchall()
        return {row[0] for row in rows}


def add_seen_items(search_id: int, item_ids):
    """Marca una lista de artículos como vistos (no se avisarán otra vez)."""
    if not item_ids:
        return
    with get_connection() as conn:
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO seen_items (search_id, item_id) VALUES (?, ?)",
            [(search_id, item_id) for item_id in item_ids],
        )
        conn.commit()


def delete_search(search_id: int):
    """Borra una búsqueda por ID y también sus artículos vistos."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM seen_items WHERE search_id = ?", (search_id,))
        cur.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        conn.commit()
