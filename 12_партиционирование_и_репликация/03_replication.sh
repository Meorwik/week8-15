#!/bin/bash
# Занятие 12, часть Б. Логическая репликация primary -> replica и отказ primary.
# Инструкция преподавателя не выдана — шаги написаны по описанию задания.
# Два сервера PostgreSQL 17 в docker в одной сети; на primary база seattle_library из занятий 1–2.
# Пароль только из переменной окружения: PGPASSWORD=... ./03_replication.sh > output_replication.txt 2>&1
set -u
: "${PGPASSWORD:?задай PGPASSWORD}"
P=$(cd "$(dirname "$0")/.." && pwd)                      # папка «Практики» (нужны скрипты занятий 1–2 и data/)
NET=hpd-w12-net; PRI=hpd-w12-primary; REP=hpd-w12-replica

pri()  { docker exec -i "$PRI" psql -U postgres -d seattle_library -e "$@"; }
rep()  { docker exec -i "$REP" psql -U postgres -d seattle_library -e "$@"; }
step() { echo; echo "=================== $* ==================="; }
wait_pg() { until docker exec "$1" psql -U postgres -c 'select 1' >/dev/null 2>&1; do sleep 1; done; }

step "0. Два сервера в одной сети: primary (wal_level=logical) и replica"
docker rm -f "$PRI" "$REP" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1
docker network create "$NET" >/dev/null
docker run -d --name "$PRI" --network "$NET" -p 55441:5432 -e POSTGRES_PASSWORD="$PGPASSWORD" -v "$P:/w:ro" \
    postgres:17 -c wal_level=logical >/dev/null           # logical — в WAL пишется информация для логической репликации
docker run -d --name "$REP" --network "$NET" -p 55442:5432 -e POSTGRES_PASSWORD="$PGPASSWORD" postgres:17 >/dev/null
wait_pg "$PRI"; wait_pg "$REP"
docker exec -w /w/01_знакомство_с_PostgreSQL "$PRI" psql -U postgres -q -f 01_create_db.sql >/dev/null 2>&1
docker exec -w /w/02_ключи_и_связи "$PRI" psql -U postgres -d seattle_library -q -f 01_import.sql -f 02_tasks.sql >/dev/null 2>&1
pri -c "SHOW wal_level" -c "SELECT COUNT(*) AS titles FROM titles"

step "1. primary: публикация таблиц titles и checkout_facts"
pri -c "CREATE PUBLICATION pub_lib FOR TABLE titles, checkout_facts"

step "2. replica: схема переносится вручную (DDL не реплицируется), затем подписка"
docker exec "$REP" psql -U postgres -c "CREATE DATABASE seattle_library"
docker exec "$PRI" pg_dump -U postgres -s -t titles -t checkout_facts seattle_library | docker exec -i "$REP" psql -U postgres -d seattle_library -q >/dev/null
# Пароль попадает в pg_subscription (видит только суперпользователь); в бою — файл .pgpass на replica
rep -c "CREATE SUBSCRIPTION sub_lib CONNECTION 'host=$PRI dbname=seattle_library user=postgres password=$PGPASSWORD' PUBLICATION pub_lib" \
    | sed "s/password=[^ ']*/password=***/"
until [ "$(docker exec "$REP" psql -U postgres -d seattle_library -Atc "SELECT COUNT(*) FROM pg_subscription_rel WHERE srsubstate <> 'r'")" = 0 ]; do sleep 1; done
echo "-- начальная синхронизация (COPY) завершена"
pri -c "SELECT (SELECT COUNT(*) FROM titles) AS titles, (SELECT COUNT(*) FROM checkout_facts) AS facts"
rep -c "SELECT (SELECT COUNT(*) FROM titles) AS titles, (SELECT COUNT(*) FROM checkout_facts) AS facts"

step "3. INSERT/UPDATE/DELETE на primary доходят до replica"
pri -c "INSERT INTO titles (title, creator) VALUES ('Новая книга с primary', 'Занятие 12') RETURNING title_id" \
    -c "UPDATE checkout_facts SET checkouts = 999 WHERE fact_id = 1" \
    -c "DELETE FROM checkout_facts WHERE fact_id = 2"
sleep 2
rep -c "SELECT title_id, title FROM titles WHERE title = 'Новая книга с primary'" \
    -c "SELECT fact_id, checkouts FROM checkout_facts WHERE fact_id IN (1, 2)"

step "4. DDL не реплицируется: новый столбец на primary ломает применение изменений"
pri -c "ALTER TABLE titles ADD COLUMN note text" \
    -c "INSERT INTO titles (title, note) VALUES ('Книга после ALTER', 'есть note')"
sleep 3
rep -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'titles' AND column_name = 'note'" \
    -c "SELECT COUNT(*) AS arrived FROM titles WHERE title = 'Книга после ALTER'"
docker logs "$REP" 2>&1 | grep -m1 "missing replicated column"
echo "-- исправляем: тот же ALTER на replica, применение продолжается"
rep -c "ALTER TABLE titles ADD COLUMN note text"
sleep 6
rep -c "SELECT title, note FROM titles WHERE title = 'Книга после ALTER'"

step "5. Последовательности не реплицируются: запись на replica с автоматическим id"
pri -c "SELECT last_value FROM titles_title_id_seq"
rep -c "SELECT last_value FROM titles_title_id_seq"
rep -c "INSERT INTO titles (title) VALUES ('Запись на replica')"
rep -c "INSERT INTO titles (title_id, title) VALUES (900001, 'Запись на replica с явным id')"

step "6. Отказ primary: replica читает и пишет, но новых изменений не получает"
docker stop "$PRI" >/dev/null && echo "-- primary остановлен"
sleep 8                                                  # воркер подписки переподключается раз в 5 секунд
rep -c "SELECT COUNT(*) AS titles_on_replica FROM titles" \
    -c "INSERT INTO checkout_facts (fact_id, title_id, checkoutyear, checkoutmonth, materialtype, checkouts) VALUES (900001, 1, 2019, 7, 'BOOK', 5)" \
    -c "SELECT subname, pid, received_lsn FROM pg_stat_subscription"
docker logs "$REP" 2>&1 | grep -E -m2 "could not (receive data|connect)"

step "7. primary снова запущен: репликация продолжается сама; изменения replica на primary не попадают"
docker start "$PRI" >/dev/null; wait_pg "$PRI"
pri -c "INSERT INTO titles (title) VALUES ('Книга после восстановления primary')"
sleep 6
rep -c "SELECT title_id, title FROM titles WHERE title LIKE 'Книга после восстановления%'"
pri -c "SELECT COUNT(*) AS replica_row_on_primary FROM titles WHERE title_id = 900001"

step "Уборка"
docker rm -f "$PRI" "$REP" >/dev/null; docker network rm "$NET" >/dev/null && echo "-- контейнеры и сеть удалены"
