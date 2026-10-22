-- Занятие 12, часть А. Переносим big_checkouts (занятие 9) в таблицу, разбитую по годам.
-- Файл преподавателя не выдан — написан свой по описанию задания.
-- Запуск: psql -U postgres -d seattle_library -f 01_partitioning.sql

DROP TABLE IF EXISTS checkouts_part, checkouts_2005_2009 CASCADE;   -- вторая — если после DETACH осталась отдельной

CREATE TABLE checkouts_part (
    id            bigint,
    materialtype  varchar(50),
    checkoutyear  int NOT NULL,
    checkoutmonth int,
    checkouts     int,
    title         text,
    creator       text
) PARTITION BY RANGE (checkoutyear);

-- Границы: FROM включительно, TO — НЕ включительно
CREATE TABLE checkouts_2005_2009 PARTITION OF checkouts_part FOR VALUES FROM (2005) TO (2010);
CREATE TABLE checkouts_2010_2014 PARTITION OF checkouts_part FOR VALUES FROM (2010) TO (2015);
CREATE TABLE checkouts_2015_2019 PARTITION OF checkouts_part FOR VALUES FROM (2015) TO (2020);
CREATE TABLE checkouts_2020_2024 PARTITION OF checkouts_part FOR VALUES FROM (2020) TO (2025);

INSERT INTO checkouts_part SELECT id, materialtype, checkoutyear, checkoutmonth, checkouts, title, creator FROM big_checkouts;
ANALYZE checkouts_part;

-- Проверка переноса: строк столько же, сколько в big_checkouts
SELECT (SELECT COUNT(*) FROM big_checkouts) AS big_rows, (SELECT COUNT(*) FROM checkouts_part) AS part_rows;
SELECT tableoid::regclass AS partition, COUNT(*) AS rows, MIN(checkoutyear), MAX(checkoutyear)
FROM checkouts_part GROUP BY 1 ORDER BY 1;
