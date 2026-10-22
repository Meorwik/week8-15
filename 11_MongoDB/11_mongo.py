"""Занятие 11. MongoDB в Web-приложении: перенос seattle_library в документы, CRUD, агрегация, индексы.

Запуск: python 11_mongo.py
Адреса из переменных окружения:
  DATABASE_URL — PostgreSQL (как в 08/db.py), например postgresql://postgres:ПАРОЛЬ@localhost:5432/seattle_library
  MONGO_URL    — MongoDB, по умолчанию mongodb://localhost:27017
Скрипт можно запускать повторно: коллекция очищается перед загрузкой (delete_many), тестовый документ удаляется.
"""
import os

import psycopg2
from pymongo import MongoClient

YEAR, SUBJECT = 2019, "Fantasy"  # в срезе есть только 2019 год

pg = psycopg2.connect(os.getenv("DATABASE_URL", "dbname=seattle_library"))
cur = pg.cursor()
coll = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))["seattle_mongo"]["titles"]


def section(name):
    print(f"\n=== {name} ===")


# ---------------------------------------------------------------------------------------------
section("1. PostgreSQL -> документы: один запрос с JOIN, группировка в Python")
# LEFT JOIN: название без тем или без выдач всё равно станет документом.
# Темы и выдачи в одном запросе перемножаются (выдачи × темы), поэтому дубли убираем по subject и fact_id.
cur.execute("""
    SELECT t.title_id, t.title, t.creator, t.publisher, s.subject_name,
           f.fact_id, f.checkoutyear, f.checkoutmonth, f.materialtype, f.checkouts
    FROM titles t
    LEFT JOIN title_subjects ts ON ts.title_id = t.title_id
    LEFT JOIN subjects s        ON s.subject_id = ts.subject_id
    LEFT JOIN checkout_facts f  ON f.title_id = t.title_id
    ORDER BY t.title_id, s.subject_name, f.fact_id
""")
rows = cur.fetchall()
docs, seen_facts = {}, set()
for title_id, title, creator, publisher, subject, fact_id, year, month, mtype, cnt in rows:
    d = docs.setdefault(title_id, {"title_id": title_id, "title": title, "creator": creator,
                                   "publisher": publisher, "subjects": [], "checkouts": []})
    if subject is not None and subject not in d["subjects"]:
        d["subjects"].append(subject)
    if fact_id is not None and fact_id not in seen_facts:
        seen_facts.add(fact_id)
        d["checkouts"].append({"year": year, "month": month, "material_type": mtype, "count": cnt})

coll.delete_many({})  # без очистки повторный запуск задвоил бы документы
coll.insert_many(list(docs.values()))

cur.execute("SELECT (SELECT COUNT(*) FROM titles), (SELECT COUNT(*) FROM checkout_facts), "
            "(SELECT COUNT(*) FROM title_subjects)")
sql_titles, sql_facts, sql_links = cur.fetchone()
mongo_facts = next(coll.aggregate([{"$group": {"_id": None, "n": {"$sum": {"$size": "$checkouts"}}}}]))["n"]
mongo_links = next(coll.aggregate([{"$group": {"_id": None, "n": {"$sum": {"$size": "$subjects"}}}}]))["n"]
print(f"строк в результате JOIN: {len(rows)}")
print(f"{'':12}{'SQL':>8}{'Mongo':>8}")
print(f"{'названия':12}{sql_titles:>8}{coll.count_documents({}):>8}")
print(f"{'выдачи':12}{sql_facts:>8}{mongo_facts:>8}")
print(f"{'темы-связи':12}{sql_links:>8}{mongo_links:>8}")
assert (sql_titles, sql_facts, sql_links) == (coll.count_documents({}), mongo_facts, mongo_links)
print("пример документа (с несколькими темами):")
print(coll.find_one({"subjects.2": {"$exists": True}}, {"_id": 0}))

# ---------------------------------------------------------------------------------------------
section(f"2. CRUD")
# (1) Read: тема + условие на год. "checkouts.year" ищет внутри массива выдач.
query = {"subjects": SUBJECT, "checkouts.year": YEAR}
print(f"find {query}: {coll.count_documents(query)} документов")
cur.execute("""SELECT COUNT(DISTINCT t.title_id)
               FROM titles t
               JOIN title_subjects ts ON ts.title_id = t.title_id
               JOIN subjects s        ON s.subject_id = ts.subject_id
               JOIN checkout_facts f  ON f.title_id = t.title_id
               WHERE s.subject_name = %s AND f.checkoutyear = %s""", (SUBJECT, YEAR))
print(f"тот же запрос в SQL (3 JOIN): {cur.fetchone()[0]}")
for d in coll.find(query, {"_id": 0, "title": 1, "checkouts": 1}).sort("title", 1).limit(3):
    print("  ", d)

# (2) Create
new_id = coll.insert_one({"title_id": None, "title": "Practice 11 test book", "creator": "Student",
                          "publisher": "Test Press", "subjects": ["Databases", "Fantasy"],
                          "checkouts": [{"year": 2020, "month": 1, "material_type": "BOOK", "count": 3}]}).inserted_id
print("insert_one:", new_id)
# (3) $push: новая выдача в массив
r = coll.update_one({"_id": new_id}, {"$push": {"checkouts": {"year": 2020, "month": 2, "material_type": "EBOOK", "count": 5}}})
print(f"$push: matched={r.matched_count} modified={r.modified_count}")
# (4) $set: изменить поле
r = coll.update_one({"_id": new_id}, {"$set": {"publisher": "Updated Press"}})
print(f"$set:  matched={r.matched_count} modified={r.modified_count}")
print("документ после $push и $set:", coll.find_one({"_id": new_id}, {"_id": 0}))
# (5) Delete
r = coll.delete_one({"_id": new_id})
print(f"delete_one: deleted={r.deleted_count}; документов снова {coll.count_documents({})}")

# ---------------------------------------------------------------------------------------------
section(f"3. Агрегация: топ-5 названий за {YEAR} ($unwind -> $match -> $group -> $sort -> $limit)")
pipeline = [
    {"$unwind": "$checkouts"},                     # одна выдача = один документ
    {"$match": {"checkouts.year": YEAR}},
    {"$group": {"_id": "$title_id", "title": {"$first": "$title"}, "total": {"$sum": "$checkouts.count"}}},
    {"$sort": {"total": -1, "title": 1}},
    {"$limit": 5},
]
mongo_top = [(d["_id"], d["title"], d["total"]) for d in coll.aggregate(pipeline)]
# Тот же запрос, что top_titles() в db.py занятия 7/8
cur.execute("""SELECT t.title_id, t.title, SUM(f.checkouts) AS total
               FROM checkout_facts f JOIN titles t ON t.title_id = f.title_id
               WHERE f.checkoutyear = %s
               GROUP BY t.title_id, t.title
               ORDER BY total DESC, t.title
               LIMIT %s""", (YEAR, 5))
sql_top = cur.fetchall()
print(f"{'#':<3}{'title_id':>8}{'SQL':>6}{'Mongo':>7}  title")
for i, (s, m) in enumerate(zip(sql_top, mongo_top), 1):
    print(f"{i:<3}{s[0]:>8}{s[2]:>6}{m[2]:>7}  {s[1][:70]}")
print("совпадает:", [(s[0], s[2]) for s in sql_top] == [(m[0], m[2]) for m in mongo_top])
assert [(s[0], s[2]) for s in sql_top] == [(m[0], m[2]) for m in mongo_top]

# ---------------------------------------------------------------------------------------------
section("4. Индексы по title и subjects")
coll.create_index("title")
coll.create_index("subjects")  # индекс по массиву = multikey: по ключу на каждую тему
for name, info in coll.index_information().items():
    print(f"  {name}: {info['key']}")
plan = coll.find({"subjects": SUBJECT}).explain()["queryPlanner"]["winningPlan"]
stages = []
while plan:  # план — вложенные стадии: FETCH -> IXSCAN
    stages.append(plan["stage"] + (f"({plan['indexName']})" if "indexName" in plan else ""))
    plan = plan.get("inputStage")
print(f"план find({{subjects: '{SUBJECT}'}}):", " -> ".join(stages))

pg.close()
