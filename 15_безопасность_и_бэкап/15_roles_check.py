"""Занятие 15, часть 1. Подключается под каждой ролью и пробует SELECT/INSERT/UPDATE/DELETE/DROP/CREATE.

Пароли — из переменных окружения APP_READER_PW и APP_WRITER_PW. Хост/порт — PGHOST/PGPORT (по умолчанию localhost:5432).
Каждая попытка откатывается (ROLLBACK), поэтому данные не меняются.
"""
import os

import psycopg2

OPS = [
    ("SELECT", "SELECT COUNT(*) FROM titles"),
    ("INSERT checkout_facts", "INSERT INTO checkout_facts (title_id, checkoutyear, checkoutmonth, materialtype, checkouts) "
                              "VALUES (1, 2020, 1, 'BOOK', 1)"),
    ("INSERT titles", "INSERT INTO titles (title) VALUES ('role test')"),
    ("UPDATE checkout_facts", "UPDATE checkout_facts SET checkouts = checkouts WHERE fact_id = 1"),
    ("DELETE", "DELETE FROM checkout_facts WHERE fact_id = 1"),
    ("DROP TABLE", "DROP TABLE title_subjects"),
    ("CREATE TABLE", "CREATE TABLE hack (id INT)"),
]

for role, env in [("app_reader", "APP_READER_PW"), ("app_writer", "APP_WRITER_PW")]:
    conn = psycopg2.connect(dbname="seattle_library", user=role, password=os.environ[env])
    print(f"\n== {role} ==")
    for name, sql in OPS:
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            result = "OK"
        except psycopg2.Error as e:
            result = e.pgerror.splitlines()[0]  # первая строка: «ERROR: permission denied for table ...»
        conn.rollback()
        print(f"{name:<22} | {result}")
    conn.close()
