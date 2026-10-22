-- Занятие 9. Подготовка: размножаем срез raw_checkouts (5000 строк) до 1 000 000 строк.
-- Файл преподавателя не выдан — написан свой по описанию задания.
-- Данные учебные: важен объём, а не смысл. Каждая строка среза повторяется 200 раз,
-- год размазан по 2005–2024 (нужно для партиций в занятии 12), месяц случайный.
-- Запуск: psql -U postgres -d seattle_library -f 01_big_table.sql

DROP TABLE IF EXISTS big_checkouts CASCADE;

CREATE TABLE big_checkouts AS
SELECT row_number() OVER ()::bigint      AS id,     -- просто номер строки, БЕЗ первичного ключа: таблица без индексов
       r.materialtype,
       2005 + g % 20                     AS checkoutyear,
       1 + floor(random() * 12)::int     AS checkoutmonth,
       r.checkouts,
       r.title,
       r.creator
FROM raw_checkouts r
CROSS JOIN generate_series(0, 199) AS g
ORDER BY checkoutyear, checkoutmonth;               -- как в настоящей таблице выдач: строки копятся по времени

VACUUM ANALYZE big_checkouts;                       -- статистика для планировщика

SELECT COUNT(*) AS rows,
       pg_size_pretty(pg_total_relation_size('big_checkouts')) AS size,
       MIN(checkoutyear) AS min_year, MAX(checkoutyear) AS max_year
FROM big_checkouts;
