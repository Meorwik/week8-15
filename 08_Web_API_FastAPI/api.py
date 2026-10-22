"""Занятие 8. Web API для БД seattle_library: CRUD над выдачами, обмен данными в JSON.

Запуск (из этой папки): uvicorn api:app --reload  ->  http://127.0.0.1:8000/docs
Подключение к БД: переменная окружения DATABASE_URL (см. db.py).
"""
from typing import Annotated

import psycopg2.errors
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import db

app = FastAPI(title="Seattle Library API")


class CheckoutKey(BaseModel):
    """По этим полям находится запись о выдаче (для DELETE)."""
    title_id: int
    year: int
    month: int = Field(ge=1, le=12)
    material_type: str = Field(min_length=1, max_length=50)


class Checkout(CheckoutKey):
    """Тело POST/PUT: ключ записи + число выдач."""
    checkouts: int = Field(ge=0)


# /titles/top объявлен РАНЬШЕ /titles/{title}: FastAPI проверяет маршруты по порядку,
# иначе «top» попадёт в {title} и уйдёт в поиск по названию.
@app.get("/titles/top")
def titles_top(year: int, limit: Annotated[int, Query(ge=1, le=100)] = 10):
    return db.top_titles(year, limit)


@app.get("/titles/{title}")
def titles_by_title(title: str):
    rows = db.checkouts_by_title(title)
    if not rows:
        raise HTTPException(404, f"Выдачи по названию «{title}» не найдены")
    return rows


@app.post("/checkouts", status_code=201)
def create_checkout(c: Checkout):
    try:
        return db.add_checkout(**c.model_dump())
    except psycopg2.errors.ForeignKeyViolation:  # иначе клиент получил бы 500 Internal Server Error
        raise HTTPException(404, f"Название с title_id={c.title_id} не найдено")


@app.put("/checkouts")
def update_checkout(c: Checkout):
    if not db.update_checkouts(**c.model_dump()):
        raise HTTPException(404, "Запись о выдаче не найдена")
    return c


@app.delete("/checkouts")
def delete_checkout(c: Annotated[CheckoutKey, Query()]):  # у DELETE параметры в строке запроса, не в теле
    if not db.delete_checkout(**c.model_dump()):
        raise HTTPException(404, "Запись о выдаче не найдена")
    return {"deleted": c}
