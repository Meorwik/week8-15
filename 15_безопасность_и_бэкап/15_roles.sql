-- Занятие 15, часть 1. Роли app_reader (только чтение) и app_writer (чтение + INSERT/UPDATE).
-- Пароли не хранятся в файле: передаются переменными psql из окружения.
-- Запуск: psql -U postgres -d seattle_library -v reader_pw="$APP_READER_PW" -v writer_pw="$APP_WRITER_PW" -f 15_roles.sql

-- Повторный запуск: сначала снять права, иначе DROP ROLE откажет (у роли есть привилегии)
SELECT 'DROP OWNED BY ' || string_agg(rolname, ', ') FROM pg_roles
WHERE rolname IN ('app_reader', 'app_writer') HAVING COUNT(*) > 0 \gexec
DROP ROLE IF EXISTS app_reader;
DROP ROLE IF EXISTS app_writer;

CREATE ROLE app_reader LOGIN PASSWORD :'reader_pw';
CREATE ROLE app_writer LOGIN PASSWORD :'writer_pw';

GRANT CONNECT ON DATABASE seattle_library TO app_reader, app_writer;
GRANT USAGE ON SCHEMA public TO app_reader, app_writer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;  -- в PG 15+ уже так по умолчанию; в старых версиях CREATE TABLE был бы разрешён всем

-- Чтение 4 таблиц — обеим ролям
GRANT SELECT ON titles, checkout_facts, subjects, title_subjects TO app_reader, app_writer;

-- Запись — только app_writer, и только то, что нужно приложению (DELETE не выдаём)
GRANT INSERT, UPDATE ON checkout_facts TO app_writer;
GRANT INSERT ON titles TO app_writer;
-- SERIAL берёт значения из последовательности: без USAGE INSERT упадёт с «permission denied for sequence»
GRANT USAGE ON SEQUENCE checkout_facts_fact_id_seq, titles_title_id_seq TO app_writer;

-- Итог: кто что может (information_schema показывает выданные права)
SELECT grantee, table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type) AS privileges
FROM information_schema.role_table_grants
WHERE grantee IN ('app_reader', 'app_writer')
GROUP BY grantee, table_name
ORDER BY grantee, table_name;
