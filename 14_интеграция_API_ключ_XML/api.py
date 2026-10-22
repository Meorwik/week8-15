"""Занятие 14. API из занятия 8 + ключ доступа X-API-Key, ответ JSON/XML, полнотекстовый поиск, веб-клиент.

Запуск (из этой папки): задать DATABASE_URL и API_KEY, затем  uvicorn api:app --reload
Страница клиента: http://127.0.0.1:8000/   Документация: http://127.0.0.1:8000/docs (кнопка Authorize — ввести ключ)
"""
import os
import secrets
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Literal

import psycopg2.errors
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

import db

API_KEY = os.environ["API_KEY"]  # нет переменной -> сервер не стартует (лучше, чем API без защиты)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(key: Annotated[str | None, Depends(api_key_header)]):
    # compare_digest сравнивает за одинаковое время: по задержке ответа нельзя подобрать ключ посимвольно
    if not key or not secrets.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(401, "Нет ключа или неверный ключ в заголовке X-API-Key")


app = FastAPI(title="Seattle Library API")
data = APIRouter(dependencies=[Depends(require_key)])  # все маршруты с данными — только с ключом


@app.get("/", include_in_schema=False)
def client_page():
    """Страница клиента без ключа: в ней нет данных, ключ пользователь вводит сам."""
    return FileResponse(Path(__file__).with_name("client.html"))


class CheckoutKey(BaseModel):
    """По этим полям находится запись о выдаче (для DELETE)."""
    title_id: int
    year: int
    month: int = Field(ge=1, le=12)
    material_type: str = Field(min_length=1, max_length=50)


class Checkout(CheckoutKey):
    """Тело POST/PUT: ключ записи + число выдач."""
    checkouts: int = Field(ge=0)


# /titles/top объявлен РАНЬШЕ /titles/{title}, иначе «top» попадёт в {title}
@data.get("/titles/top")
def titles_top(year: int, limit: Annotated[int, Query(ge=1, le=100)] = 10,
               format: Literal["json", "xml"] = "json"):  # другое значение -> 422 автоматически
    rows = db.top_titles(year, limit)
    if format == "json":
        return rows
    root = ET.Element("titles", year=str(year))
    for r in rows:
        ET.SubElement(root, "title", id=str(r["title_id"]), total=str(r["total"])).text = r["title"]
    return Response(ET.tostring(root, encoding="utf-8", xml_declaration=True), media_type="application/xml")


@data.get("/search")
def search(q: Annotated[str, Query(min_length=2)]):
    return db.search_titles(q)


@data.get("/titles/{title}")
def titles_by_title(title: str):
    rows = db.checkouts_by_title(title)
    if not rows:
        raise HTTPException(404, f"Выдачи по названию «{title}» не найдены")
    return rows


@data.post("/checkouts", status_code=201)
def create_checkout(c: Checkout):
    try:
        return db.add_checkout(**c.model_dump())
    except psycopg2.errors.ForeignKeyViolation:  # иначе клиент получил бы 500 Internal Server Error
        raise HTTPException(404, f"Название с title_id={c.title_id} не найдено")


@data.put("/checkouts")
def update_checkout(c: Checkout):
    if not db.update_checkouts(**c.model_dump()):
        raise HTTPException(404, "Запись о выдаче не найдена")
    return c


@data.delete("/checkouts")
def delete_checkout(c: Annotated[CheckoutKey, Query()]):  # у DELETE параметры в строке запроса, не в теле
    if not db.delete_checkout(**c.model_dump()):
        raise HTTPException(404, "Запись о выдаче не найдена")
    return {"deleted": c}


app.include_router(data)
