"""Занятие 13. Перенос 4 таблиц seattle_library в облачный PostgreSQL и сравнение скорости.

Файл преподавателя не выдан — написан свой по описанию задания.
Строки подключения только из переменных окружения:
  DATABASE_URL — локальная база,  CLOUD_DSN — облачная (Neon/Supabase, с ?sslmode=require).
Запуск: python migrate_to_cloud.py
"""
import io
import os
import statistics
import sys
import time

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "08_Web_API_FastAPI"))
import db  # noqa: E402  — запрос занятия 7 (top_titles) берём из db.py, а не копируем

LOCAL = os.getenv("DATABASE_URL", "dbname=seattle_library")
CLOUD = os.environ["CLOUD_DSN"]  # нет переменной -> KeyError: в коде пароля быть не должно

TABLES = ["titles", "checkout_facts", "subjects", "title_subjects"]  # порядок важен из-за внешних ключей
DDL = """
DROP TABLE IF EXISTS title_subjects, subjects, checkout_facts, titles CASCADE;
CREATE TABLE titles (
    title_id SERIAL PRIMARY KEY, title TEXT, isbn VARCHAR(50), creator TEXT,
    publisher TEXT, publicationyear VARCHAR(50));
CREATE TABLE checkout_facts (
    fact_id SERIAL PRIMARY KEY, title_id INT NOT NULL REFERENCES titles(title_id),
    usageclass VARCHAR(50), checkouttype VARCHAR(50), checkoutyear INT, checkoutmonth INT,
    materialtype VARCHAR(50), checkouts INT);
CREATE TABLE subjects (subject_id SERIAL PRIMARY KEY, subject_name VARCHAR(200) UNIQUE);
CREATE TABLE title_subjects (
    title_id INT REFERENCES titles(title_id), subject_id INT REFERENCES subjects(subject_id),
    PRIMARY KEY (title_id, subject_id));
"""


def counts(conn):
    result = {}
    with conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            result[t] = cur.fetchone()[0]
    return result


def median_ms(dsn, n=20):
    """Медиана времени одного запроса занятия 7 (каждый раз новое соединение, как в db.py)."""
    db.DSN = dsn
    db.top_titles(2019, 10)  # прогрев: первое соединение (DNS, TLS) не считаем
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        db.top_titles(2019, 10)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


src, dst = psycopg2.connect(LOCAL), psycopg2.connect(CLOUD)
with src, dst, src.cursor() as s, dst.cursor() as d:
    d.execute(DDL)
    for t in TABLES:  # COPY TO -> буфер в памяти -> COPY FROM (5000 строк — помещаются)
        buf = io.StringIO()
        s.copy_expert(f"COPY {t} TO STDOUT", buf)
        buf.seek(0)
        d.copy_expert(f"COPY {t} FROM STDIN", buf)
    for t, pk in [("titles", "title_id"), ("checkout_facts", "fact_id"), ("subjects", "subject_id")]:
        # COPY не двигает SERIAL: без этого первый INSERT в облаке упадёт на дубле ключа
        d.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{pk}'), (SELECT MAX({pk}) FROM {t}))")

lc, cc = counts(src), counts(dst)
print(f"{'таблица':<16}{'локально':>10}{'облако':>10}  совпало")
for t in TABLES:
    print(f"{t:<16}{lc[t]:>10}{cc[t]:>10}  {'да' if lc[t] == cc[t] else 'НЕТ'}")
with dst.cursor() as d:
    d.execute("SELECT inet_server_addr(), current_setting('server_version'), "
              "(SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid())")
    print("облачный сервер: адрес %s, PostgreSQL %s, SSL=%s" % d.fetchone())
src.close(), dst.close()

loc, cl = median_ms(LOCAL), median_ms(CLOUD)
print(f"медиана top_titles(2019, 10), 20 запусков: локально {loc:.1f} мс, облако {cl:.1f} мс")
print("топ-3 в облаке:", [(r["title_id"], r["total"]) for r in db.top_titles(2019, 3)])
