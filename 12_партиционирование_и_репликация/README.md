# 12. Партиционирование и репликация

01_partitioning.sql переносит big_checkouts из 9 занятия в таблицу с партициями по годам, 02_tasks.sql сравнивает планы, делает DETACH/ATTACH, DEFAULT-партицию и хеш-партиции. Репликацию проверял на двух докер-контейнерах скриптом 03_replication.sh. Результаты в output.txt и output_replication.txt.
