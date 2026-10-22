"""Занятие 10. Транзакции, изоляция и блокировки: все опыты через два соединения psycopg2 (S1 и S2).

Каждое соединение — отдельная сессия, как два окна psql. Запросы и ответы печатаются в виде протокола.
Запуск (после 00_setup_w10.sql):
    export DATABASE_URL="postgresql://postgres:ПАРОЛЬ@localhost:5432/seattle_library"
    python w10_demo.py
"""
import os
import threading
import time

import psycopg2

DSN = os.getenv("DATABASE_URL", "dbname=seattle_library")


def session():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True  # BEGIN/COMMIT/ROLLBACK пишем сами, как в psql
    return conn


def sql(conn, name, q, params=None):
    """Выполняет запрос в сессии и печатает его как в окне psql. Ошибку печатает и не роняет скрипт."""
    print(f"{name}> {q}", flush=True)
    cur = conn.cursor()
    try:
        cur.execute(q, params)
    except psycopg2.Error as e:  # (S1)/(S2) в начале: при блокировках ответ может прийти не сразу после запроса
        print(f"     ({name}) " + e.pgerror.strip().replace("\n", "\n     "), flush=True)
        return None
    if not cur.description:
        print(f"     ({name}) {cur.statusmessage}", flush=True)  # как psql: BEGIN, UPDATE 1, COMMIT
    else:
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        for r in rows:
            print("     " + ", ".join(f"{c}={v}" for c, v in zip(cols, r)), flush=True)
        return rows


def header(text):
    print(f"\n{'=' * 100}\n{text}\n{'=' * 100}", flush=True)


s1, s2 = session(), session()
AVAIL = "SELECT available FROM copies WHERE title_id = 1"

# ------------------------------------------------------------------------------------------
header("1. Атомарность: UPDATE copies + INSERT loans с reader = NULL в одной транзакции")
sql(s2, "S2", "UPDATE copies SET available = 10 WHERE title_id IN (1, 2)")
sql(s2, "S2", "SELECT title_id, title FROM titles WHERE title_id IN (1, 2) ORDER BY title_id")
sql(s1, "S1", "SELECT COUNT(*) AS loans FROM loans")
sql(s1, "S1", "BEGIN")
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 1")
sql(s1, "S1", AVAIL)  # внутри транзакции S1 видит своё изменение: 9
sql(s2, "S2", AVAIL)  # S2 не видит незакоммиченное: 10
sql(s1, "S1", "INSERT INTO loans (title_id, reader) VALUES (1, NULL)")  # NOT NULL -> ошибка
sql(s1, "S1", AVAIL)  # после ошибки транзакция «сломана»: current transaction is aborted
sql(s1, "S1", "ROLLBACK")
sql(s1, "S1", AVAIL)  # снова 10: UPDATE тоже отменён
sql(s1, "S1", "SELECT COUNT(*) AS loans FROM loans")  # 0: строка в loans не появилась

print("\n-- для сравнения: та же транзакция без ошибки, S2 видит изменения только после COMMIT")
sql(s1, "S1", "BEGIN")
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 1")
sql(s1, "S1", "INSERT INTO loans (title_id, reader) VALUES (1, 'Иванов') RETURNING loan_id")
sql(s2, "S2", "SELECT (" + AVAIL + ") AS available, (SELECT COUNT(*) FROM loans) AS loans")  # 10 и 0
sql(s1, "S1", "COMMIT")
sql(s2, "S2", "SELECT (" + AVAIL + ") AS available, (SELECT COUNT(*) FROM loans) AS loans")  # 9 и 1

# ------------------------------------------------------------------------------------------
for level in ("READ COMMITTED", "REPEATABLE READ"):
    header(f"2. {level}: S1 читает дважды, S2 между чтениями меняет значение и делает COMMIT")
    sql(s2, "S2", "UPDATE copies SET available = 10 WHERE title_id = 1")
    sql(s1, "S1", f"BEGIN ISOLATION LEVEL {level}")
    sql(s1, "S1", AVAIL)  # первое чтение
    sql(s2, "S2", "UPDATE copies SET available = 7 WHERE title_id = 1")  # autocommit = сразу COMMIT
    sql(s1, "S1", AVAIL)  # RC: 7 (неповторяющееся чтение), RR: 10 (снимок на начало транзакции)
    sql(s1, "S1", "COMMIT")
    sql(s1, "S1", AVAIL)  # после COMMIT S1 видит 7 на любом уровне

header("2а. READ UNCOMMITTED в PostgreSQL = READ COMMITTED: грязного чтения нет")
sql(s2, "S2", "UPDATE copies SET available = 10 WHERE title_id = 1")
sql(s1, "S1", "BEGIN ISOLATION LEVEL READ UNCOMMITTED")
sql(s1, "S1", "SHOW transaction_isolation")
sql(s2, "S2", "BEGIN")
sql(s2, "S2", "UPDATE copies SET available = 999 WHERE title_id = 1")  # не закоммичено
sql(s1, "S1", AVAIL)  # 10, а не 999: незакоммиченные данные не видны
sql(s2, "S2", "ROLLBACK")
sql(s1, "S1", "COMMIT")

# ------------------------------------------------------------------------------------------
header("3. Потерянное обновление: 2 потока x 50 раз «прочитать available, вычесть 1, записать»; старт 100, ждём 0")
N = 50


def worker(mode, barrier):
    conn = session()
    cur = conn.cursor()
    barrier.wait()  # оба потока стартуют одновременно
    for _ in range(N):
        if mode == "atomic":  # исправление 1: вычитание внутри одного UPDATE
            cur.execute("UPDATE copies SET available = available - 1 WHERE title_id = 1")
            continue
        if mode == "for_update":  # исправление 2: блокируем строку на время «чтение -> запись»
            cur.execute("BEGIN")
            cur.execute(AVAIL + " FOR UPDATE")
        else:
            cur.execute(AVAIL)
        value = cur.fetchone()[0]
        time.sleep(0.001)  # приложение «думает» между чтением и записью
        cur.execute("UPDATE copies SET available = %s WHERE title_id = 1", (value - 1,))
        if mode == "for_update":
            cur.execute("COMMIT")
    conn.close()


for mode, title in (("naive", "SELECT, затем UPDATE SET available = <прочитанное - 1>  (ошибка)"),
                    ("atomic", "исправление 1: UPDATE ... SET available = available - 1"),
                    ("for_update", "исправление 2: BEGIN; SELECT ... FOR UPDATE; UPDATE; COMMIT")):
    sql(s1, "S1", "UPDATE copies SET available = 100 WHERE title_id = 1")
    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=worker, args=(mode, barrier)) for _ in range(2)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = s1.cursor()
    final.execute(AVAIL)
    value = final.fetchone()[0]
    print(f"   {title}\n   итог available = {value} (ожидали 0), потеряно обновлений: {value}, "
          f"время {time.perf_counter() - t0:.2f} с\n", flush=True)

# ------------------------------------------------------------------------------------------
header("4. REPEATABLE READ: could not serialize access и повтор транзакции")


def take_copy_with_retry(conn, interfere, max_attempts=5):
    """Выдать 1 экземпляр на уровне REPEATABLE READ; при SerializationFailure — повторить всю транзакцию."""
    cur = conn.cursor()
    for attempt in range(1, max_attempts + 1):
        try:
            cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
            cur.execute(AVAIL)
            print(f"   попытка {attempt}: S1 прочитал available = {cur.fetchone()[0]}", flush=True)
            if attempt == 1:
                interfere()  # пока S1 думает, S2 меняет ту же строку и коммитит
            cur.execute("UPDATE copies SET available = available - 1 WHERE title_id = 1")
            cur.execute("COMMIT")
            print(f"   попытка {attempt}: COMMIT прошёл", flush=True)
            return attempt
        except psycopg2.errors.SerializationFailure as e:
            cur.execute("ROLLBACK")
            print(f"   попытка {attempt}: {e.pgerror.strip().splitlines()[0]} -> ROLLBACK и повтор", flush=True)
    raise RuntimeError("не удалось выполнить транзакцию")


sql(s2, "S2", "UPDATE copies SET available = 10 WHERE title_id = 1")
attempts = take_copy_with_retry(
    s1, lambda: sql(s2, "S2", "UPDATE copies SET available = available - 1 WHERE title_id = 1"))
sql(s1, "S1", AVAIL)  # 10 - 1 (S2) - 1 (S1 со 2-й попытки) = 8
assert attempts == 2

# ------------------------------------------------------------------------------------------
header("5. Взаимоблокировка: S1 обновляет строки 1 -> 2, S2 обновляет 2 -> 1")
sql(s1, "S1", "SELECT pg_backend_pid() AS s1_pid")
sql(s2, "S2", "SELECT pg_backend_pid() AS s2_pid")
sql(s1, "S1", "BEGIN")
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 1")
sql(s2, "S2", "BEGIN")
sql(s2, "S2", "UPDATE copies SET available = available - 1 WHERE title_id = 2")
t = threading.Thread(target=sql, args=(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 2"))
t.start()  # S1 ждёт строку 2, которую держит S2
time.sleep(0.3)
sql(s2, "S2", "UPDATE copies SET available = available - 1 WHERE title_id = 1")  # S2 ждёт строку 1 -> цикл
t.join()
# через deadlock_timeout (1 с) сервер находит цикл и прерывает одну из транзакций
sql(s1, "S1", "ROLLBACK")
sql(s2, "S2", "ROLLBACK")

print("\n-- исправление: обе сессии обращаются к строкам в одном порядке (1, затем 2)")
sql(s1, "S1", "BEGIN")
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 1")
sql(s2, "S2", "BEGIN")
t = threading.Thread(target=sql, args=(s2, "S2", "UPDATE copies SET available = available - 1 WHERE title_id = 1"))
t.start()  # S2 просто ждёт, пока S1 отпустит строку 1
time.sleep(0.3)
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 2")
sql(s1, "S1", "COMMIT")
t.join()
sql(s2, "S2", "UPDATE copies SET available = available - 1 WHERE title_id = 2")
sql(s2, "S2", "COMMIT")
sql(s1, "S1", "SELECT title_id, available FROM copies WHERE title_id IN (1, 2) ORDER BY title_id")

# ------------------------------------------------------------------------------------------
header("6. MVCC: xmin и xmax строки до и после UPDATE")
MV = "SELECT xmin, xmax, ctid, title_id, available FROM copies WHERE title_id = 1"
# обычный UPDATE без ожиданий: после ожидания блокировки в xmax остаётся номер «блокировщика», это путает
sql(s2, "S2", "UPDATE copies SET available = 10 WHERE title_id = 1")
sql(s1, "S1", MV)
sql(s1, "S1", "BEGIN")
sql(s1, "S1", "SELECT txid_current() AS my_txid")
sql(s1, "S1", "UPDATE copies SET available = available - 1 WHERE title_id = 1")
sql(s2, "S2", MV)  # S2 видит старую версию строки, у неё xmax = txid S1 (S1 её «удаляет»)
sql(s1, "S1", "COMMIT")
sql(s1, "S1", MV)  # новая версия: xmin = txid S1, xmax = 0, другой ctid

s1.close()
s2.close()
