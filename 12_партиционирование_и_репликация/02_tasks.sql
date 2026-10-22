-- Занятие 12, часть А. Задания 1–5. Запуск после 01_partitioning.sql:
-- psql -U postgres -d seattle_library -e -f 02_tasks.sql
-- mt — тип материала варианта V: V0 BOOK, V1 EBOOK, V2 SOUNDDISC, V3 VIDEODISC
\set mt 'BOOK'

-- Сравниваем «чистый» эффект партиций: индексы из занятия 9 на big_checkouts убираем
DROP INDEX IF EXISTS ix_year_type, ix_title, ix_title_pattern, ix_title_hash, ix_title_fts;
VACUUM ANALYZE big_checkouts;     -- убрать «мёртвые» строки от вставок с ROLLBACK в занятии 9

------------------------------------------------------------------------------------------
-- Задание 1. Запрос по ключу партиционирования: читается только одна часть (partition pruning).
------------------------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts  WHERE checkoutyear = 2019;
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM checkouts_part WHERE checkoutyear = 2019;

------------------------------------------------------------------------------------------
-- Задание 2. Без условия по году: читаются все 4 части, ускорения нет.
------------------------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts  WHERE materialtype = :'mt';
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM checkouts_part WHERE materialtype = :'mt';

------------------------------------------------------------------------------------------
-- Задание 3. Архивирование: DETACH отрезает часть мгновенно (без DELETE), ATTACH возвращает.
------------------------------------------------------------------------------------------
SELECT COUNT(*) AS rows_before FROM checkouts_part;
ALTER TABLE checkouts_part DETACH PARTITION checkouts_2005_2009;
SELECT COUNT(*) AS rows_after_detach FROM checkouts_part;
SELECT COUNT(*) AS rows_in_archive  FROM checkouts_2005_2009;      -- теперь это обычная отдельная таблица
ALTER TABLE checkouts_part ATTACH PARTITION checkouts_2005_2009 FOR VALUES FROM (2005) TO (2010);
SELECT COUNT(*) AS rows_after_attach FROM checkouts_part;

------------------------------------------------------------------------------------------
-- Задание 4. Год вне диапазонов -> ошибка; решение — DEFAULT-партиция.
------------------------------------------------------------------------------------------
\set ON_ERROR_STOP off
INSERT INTO checkouts_part (id, materialtype, checkoutyear, checkoutmonth, checkouts, title)
VALUES (0, :'mt', 2200, 1, 1, 'Год вне диапазона');
\set ON_ERROR_STOP on
CREATE TABLE checkouts_default PARTITION OF checkouts_part DEFAULT;
INSERT INTO checkouts_part (id, materialtype, checkoutyear, checkoutmonth, checkouts, title)
VALUES (0, :'mt', 2200, 1, 1, 'Год вне диапазона');
SELECT tableoid::regclass AS partition, checkoutyear, title FROM checkouts_part WHERE checkoutyear = 2200;
DROP TABLE checkouts_default;                                       -- убираем тестовую строку вместе с частью

------------------------------------------------------------------------------------------
-- Задание 5. Хеш-партиционирование по id на 3 части: строки делятся поровну.
------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS checkouts_hash;
CREATE TABLE checkouts_hash (LIKE checkouts_part) PARTITION BY HASH (id);
CREATE TABLE checkouts_hash_0 PARTITION OF checkouts_hash FOR VALUES WITH (MODULUS 3, REMAINDER 0);
CREATE TABLE checkouts_hash_1 PARTITION OF checkouts_hash FOR VALUES WITH (MODULUS 3, REMAINDER 1);
CREATE TABLE checkouts_hash_2 PARTITION OF checkouts_hash FOR VALUES WITH (MODULUS 3, REMAINDER 2);
INSERT INTO checkouts_hash SELECT * FROM checkouts_part;
SELECT tableoid::regclass AS partition, COUNT(*) AS rows,
       round(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM checkouts_hash GROUP BY 1 ORDER BY 1;
-- Поиск по id читает одну часть, по диапазону годов — все три
EXPLAIN SELECT * FROM checkouts_hash WHERE id = 12345;
EXPLAIN SELECT COUNT(*) FROM checkouts_hash WHERE checkoutyear = 2019;
