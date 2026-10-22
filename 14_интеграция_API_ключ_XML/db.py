"""Функции доступа к БД seattle_library (занятие 7, + search_titles для занятия 14), их вызывает api.py.

Подключение берётся из переменной окружения DATABASE_URL, пароль в коде не хранится.
Пример: export DATABASE_URL="postgresql://postgres:ПАРОЛЬ@localhost:5432/seattle_library"
"""
import os

import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.getenv("DATABASE_URL", "dbname=seattle_library")  # остальное libpq возьмёт из PGHOST/PGUSER/PGPASSWORD


def _run(sql, params=()):
    """Выполняет запрос в отдельном соединении: SELECT -> список словарей, иначе -> число затронутых строк."""
    conn = psycopg2.connect(DSN, cursor_factory=RealDictCursor)  # новое соединение на каждый запрос, для учебного API этого хватает
    try:
        with conn, conn.cursor() as cur:  # with conn: COMMIT при успехе, ROLLBACK при исключении
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else cur.rowcount
    finally:
        conn.close()


def top_titles(year, limit=10):
    """Топ названий по сумме выдач за год."""
    return _run(
        """SELECT t.title_id, t.title, SUM(f.checkouts) AS total
           FROM checkout_facts f JOIN titles t ON t.title_id = f.title_id
           WHERE f.checkoutyear = %s
           GROUP BY t.title_id, t.title
           ORDER BY total DESC, t.title
           LIMIT %s""",
        (year, limit),
    )


def checkouts_by_title(title):
    """Выдачи по названию (поиск подстроки без учёта регистра)."""
    return _run(
        """SELECT t.title_id, t.title, f.checkoutyear AS year, f.checkoutmonth AS month,
                  f.materialtype AS material_type, f.checkouts
           FROM titles t JOIN checkout_facts f ON f.title_id = t.title_id
           WHERE t.title ILIKE %s
           ORDER BY t.title, year, month""",
        (f"%{title}%",),
    )


def add_checkout(title_id, year, month, material_type, checkouts):
    """Добавляет выдачу. Несуществующий title_id -> psycopg2.errors.ForeignKeyViolation."""
    return _run(
        """INSERT INTO checkout_facts (title_id, checkoutyear, checkoutmonth, materialtype, checkouts)
           VALUES (%s, %s, %s, %s, %s) RETURNING fact_id, title_id, checkoutyear AS year,
           checkoutmonth AS month, materialtype AS material_type, checkouts""",
        (title_id, year, month, material_type, checkouts),
    )[0]


def update_checkouts(title_id, year, month, material_type, checkouts):
    """Меняет число выдач у записи (title_id, год, месяц, тип). Возвращает число изменённых строк."""
    return _run(
        """UPDATE checkout_facts SET checkouts = %s
           WHERE title_id = %s AND checkoutyear = %s AND checkoutmonth = %s AND materialtype = %s""",
        (checkouts, title_id, year, month, material_type),
    )


def delete_checkout(title_id, year, month, material_type):
    """Удаляет запись (title_id, год, месяц, тип). Возвращает число удалённых строк."""
    return _run(
        """DELETE FROM checkout_facts
           WHERE title_id = %s AND checkoutyear = %s AND checkoutmonth = %s AND materialtype = %s""",
        (title_id, year, month, material_type),
    )


def search_titles(q, limit=50):
    """Полнотекстовый поиск по названию. q уходит параметром, поэтому склейки SQL нет и инъекция невозможна."""
    return _run(
        """SELECT t.title_id, t.title
           FROM titles t, plainto_tsquery('english', %s) AS query
           WHERE to_tsvector('english', t.title) @@ query
           ORDER BY ts_rank(to_tsvector('english', t.title), query) DESC, t.title
           LIMIT %s""",
        (q, limit),
    )
