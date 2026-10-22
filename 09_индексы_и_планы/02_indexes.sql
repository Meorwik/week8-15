-- Занятие 9. Индексы и планы выполнения запросов.
-- Запуск после 01_big_table.sql: psql -U postgres -d seattle_library -e -f 02_indexes.sql > output.txt
-- Переменные psql (комментарий на той же строке после \set попал бы в значение):
-- mt — тип материала варианта V: V0 BOOK, V1 EBOOK, V2 SOUNDDISC, V3 VIDEODISC
-- t — (б) любое название из big_checkouts; prefix — (в) начало названия; word — (г) слово для ILIKE и FTS
\set mt 'BOOK'
\set t 'Spinning silver / Naomi Novik.'
\set prefix 'Spinning%'
\set word 'war'

-- Повторный запуск начинается «с нуля»: без индексов на big_checkouts
DROP INDEX IF EXISTS ix_year_type, ix_title, ix_title_pattern, ix_title_hash, ix_title_fts;
SELECT datcollate FROM pg_database WHERE datname = current_database();   -- не «C» -> для LIKE нужен text_pattern_ops

------------------------------------------------------------------------------------------
-- Задание 1. Планы «до»: индексов нет, везде Seq Scan по 1 000 000 строк.
------------------------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts WHERE checkoutyear = 2019 AND materialtype = :'mt';  -- (а)
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title = :'t';                                              -- (б)
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title LIKE :'prefix';                                      -- (в)
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title ILIKE '%' || :'word' || '%';                         -- (г)

------------------------------------------------------------------------------------------
-- Задание 2. Составной B-tree (checkoutyear, materialtype).
------------------------------------------------------------------------------------------
CREATE INDEX ix_year_type ON big_checkouts (checkoutyear, materialtype);
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts WHERE checkoutyear = 2019 AND materialtype = :'mt';  -- (а) снова
-- Только по второму столбцу индекса: дерево отсортировано сначала по году, поэтому найти нужный тип «сразу» нельзя
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts WHERE materialtype = :'mt';
-- Только по первому столбцу: индекс работает (левый префикс)
EXPLAIN (ANALYZE, BUFFERS) SELECT SUM(checkouts) FROM big_checkouts WHERE checkoutyear = 2019;

------------------------------------------------------------------------------------------
-- Задание 3. B-tree по title: (б) ускоряется, (в) — нет из-за сортировки en_US; text_pattern_ops решает.
------------------------------------------------------------------------------------------
CREATE INDEX ix_title ON big_checkouts (title);
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title = :'t';             -- (б) с индексом
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title LIKE :'prefix';     -- (в) обычный B-tree не подходит
CREATE INDEX ix_title_pattern ON big_checkouts (title text_pattern_ops);
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title LIKE :'prefix';     -- (в) с text_pattern_ops

------------------------------------------------------------------------------------------
-- Задание 4. Hash по title вместо B-tree: размеры и LIKE.
------------------------------------------------------------------------------------------
CREATE TEMP TABLE idx_sizes AS
SELECT indexrelid::regclass::text AS index_name, pg_relation_size(indexrelid) AS bytes
FROM pg_index WHERE indexrelid IN ('ix_title'::regclass, 'ix_title_pattern'::regclass);
DROP INDEX ix_title, ix_title_pattern;
CREATE INDEX ix_title_hash ON big_checkouts USING hash (title);
INSERT INTO idx_sizes VALUES ('ix_title_hash', pg_relation_size('ix_title_hash'));
SELECT index_name, pg_size_pretty(bytes) AS size FROM idx_sizes ORDER BY bytes DESC;
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title = :'t';             -- (б) hash работает для «=»
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title LIKE :'prefix';     -- (в) hash не умеет LIKE/диапазоны
DROP INDEX ix_title_hash;

------------------------------------------------------------------------------------------
-- Задание 5. Полнотекстовый поиск: GIN по to_tsvector('english', title) против ILIKE '%слово%'.
------------------------------------------------------------------------------------------
CREATE INDEX ix_title_fts ON big_checkouts USING gin (to_tsvector('english', title));
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE title ILIKE '%' || :'word' || '%';
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM big_checkouts WHERE to_tsvector('english', title) @@ to_tsquery('english', :'word');
SELECT COUNT(*) FILTER (WHERE title ILIKE '%' || :'word' || '%')                                AS ilike_rows,
       COUNT(*) FILTER (WHERE to_tsvector('english', title) @@ to_tsquery('english', :'word'))  AS fts_rows
FROM big_checkouts;
-- Чем отличаются: ILIKE ищет подстроку (Edward, warrior, award), FTS — слово по основе (war, wars)
SELECT DISTINCT title AS only_ilike FROM raw_checkouts
WHERE title ILIKE '%' || :'word' || '%' AND NOT to_tsvector('english', title) @@ to_tsquery('english', :'word')
ORDER BY 1 LIMIT 8;
SELECT DISTINCT title AS fts_matches FROM raw_checkouts
WHERE to_tsvector('english', title) @@ to_tsquery('english', :'word')
ORDER BY 1 LIMIT 8;

------------------------------------------------------------------------------------------
-- Задание 6. Цена индексов: вставка 100 000 строк без индексов и с тремя индексами.
-- Вставка в транзакции с ROLLBACK: время измерено, а таблица остаётся 1 000 000 строк.
------------------------------------------------------------------------------------------
CREATE TEMP TABLE ins_src AS SELECT * FROM big_checkouts LIMIT 100000;
DROP INDEX ix_year_type, ix_title_fts;
SELECT COUNT(*) AS indexes_now FROM pg_indexes WHERE tablename = 'big_checkouts';
BEGIN;
\timing on
INSERT INTO big_checkouts SELECT * FROM ins_src;           -- без индексов
\timing off
ROLLBACK;
CREATE INDEX ix_year_type ON big_checkouts (checkoutyear, materialtype);
CREATE INDEX ix_title     ON big_checkouts (title);
CREATE INDEX ix_title_fts ON big_checkouts USING gin (to_tsvector('english', title));
SELECT COUNT(*) AS indexes_now FROM pg_indexes WHERE tablename = 'big_checkouts';
BEGIN;
\timing on
INSERT INTO big_checkouts SELECT * FROM ins_src;           -- с тремя индексами
\timing off
ROLLBACK;

-- Итог: индексы таблицы и их размеры
SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) AS size, indexdef
FROM pg_indexes WHERE tablename = 'big_checkouts' ORDER BY indexname;
SELECT pg_size_pretty(pg_relation_size('big_checkouts')) AS table_size;
