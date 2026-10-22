"""Занятие 15, часть 2. Учебная SQL-инъекция: уязвимая функция (склейка строки) и исправленная (параметры).

ТОЛЬКО для учебной базы на своём компьютере. Не проверяйте так чужие сайты и сервисы.
Файл преподавателя не выдан — написан свой по описанию задания.

Запуск: python vuln_api.py
  DATABASE_URL — подключение владельцем базы (postgres), APP_READER_PW — пароль роли app_reader (часть 1).
"""
import os

import psycopg2

OWNER_DSN = os.getenv("DATABASE_URL", "dbname=seattle_library")
READER = dict(dbname="seattle_library", user="app_reader", password=os.environ["APP_READER_PW"])  # хост — PGHOST/PGPORT


def find_titles_vulnerable(conn, title):
    """УЯЗВИМО: значение пользователя вклеено в текст SQL, кавычка в нём меняет смысл запроса."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT title_id, title FROM titles WHERE title ILIKE '%{title}%'")
        return cur.fetchall()


def find_titles_safe(conn, title):
    """Исправлено: текст запроса и значение уходят на сервер раздельно, значение не может стать SQL."""
    with conn.cursor() as cur:
        cur.execute("SELECT title_id, title FROM titles WHERE title ILIKE %s", (f"%{title}%",))
        return cur.fetchall()


ATTACKS = [
    ("обычный запрос", "spinning silver"),
    ("(а) все строки", "x' OR 1=1 --"),
    ("(б) список ролей сервера через UNION", "x' UNION SELECT oid::int, rolname::text FROM pg_roles --"),
]


def run(conn, func, value):
    try:
        rows = func(conn, value)
        conn.commit()
        shown = ", ".join(str(r[1])[:40] for r in rows[:6]) + (" ..." if len(rows) > 6 else "")
        return f"{len(rows)} строк: {shown}"
    except psycopg2.Error as e:
        conn.rollback()
        return e.pgerror.splitlines()[0]


if __name__ == "__main__":
    owner = psycopg2.connect(OWNER_DSN)
    reader = psycopg2.connect(**READER)
    for title, conn in [("владелец базы (postgres)", owner), ("роль app_reader", reader)]:
        print(f"\n== Подключение: {title} ==")
        for func in (find_titles_vulnerable, find_titles_safe):
            print(f"-- {func.__name__}")
            for name, value in ATTACKS:
                print(f"   {name:<38} {value!r}\n      -> {run(conn, func, value)}")

    # DROP TABLE через ту же уязвимость — только под app_reader: права не дадут выполнить второй оператор
    drop = "x'; DROP TABLE title_subjects; --"
    print(f"\n== DROP TABLE через инъекцию под app_reader: {drop!r}")
    print(f"   find_titles_vulnerable -> {run(reader, find_titles_vulnerable, drop)}")
    print(f"   find_titles_safe       -> {run(reader, find_titles_safe, drop)}")
    with owner.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM title_subjects")
        print(f"   title_subjects на месте: {cur.fetchone()[0]} строк")
