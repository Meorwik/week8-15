-- Занятие 10. Подготовка: таблицы copies (экземпляры в наличии) и loans (выдачи).
-- Файл преподавателя не выдан — написан свой по описанию задания.
-- Запуск (из этой папки): psql -U postgres -d seattle_library -f 00_setup_w10.sql

DROP TABLE IF EXISTS loans, copies;

CREATE TABLE copies (
    title_id  INT PRIMARY KEY REFERENCES titles(title_id),
    available INT NOT NULL CHECK (available >= 0)   -- сколько экземпляров сейчас на полке
);

CREATE TABLE loans (
    loan_id   SERIAL PRIMARY KEY,
    title_id  INT NOT NULL REFERENCES copies(title_id),
    reader    TEXT NOT NULL,                         -- NOT NULL: на этом ограничении ломаем транзакцию в задании 1
    loan_date DATE NOT NULL DEFAULT current_date
);

-- По 10 экземпляров каждого названия из своего среза
INSERT INTO copies (title_id, available)
SELECT title_id, 10 FROM titles;

SELECT (SELECT COUNT(*) FROM copies) AS copies_rows,
       (SELECT COUNT(*) FROM loans)  AS loans_rows;
SELECT c.title_id, t.title, c.available
FROM copies c JOIN titles t ON t.title_id = c.title_id
WHERE c.title_id IN (1, 2);
