"""Servidor MCP (stdio) de solo lectura para consultar la base de datos Vacations.db.

Tablas:
    Users(UserId, UserName, Email, AvailablePtos)
    VacationRequests(Id, StartDate, EndDate, RequestedDays, UserId)

Las fechas se guardan como texto ISO (YYYY-MM-DD).
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

DB_PATH = Path(os.environ.get("VACATIONS_DB", Path(__file__).with_name("Vacations.db"))).resolve()
MAX_ROWS = 500

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    name="vacations",
    instructions=(
        "Consultas de solo lectura sobre vacaciones del personal. "
        "Usa las herramientas especializadas cuando apliquen; para preguntas que no cubran, "
        "consulta get_schema y luego run_select_query. Fechas en formato YYYY-MM-DD."
    ),
)


# --------------------------------------------------------------------------- helpers


def _connect() -> sqlite3.Connection:
    """Abre la base de datos en modo solo lectura (la escritura falla a nivel de SQLite)."""
    if not DB_PATH.exists():
        raise ToolError(f"No se encontró la base de datos: {DB_PATH}")
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _query(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _parse_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ToolError(f"Fecha inválida '{value}'. Usa el formato YYYY-MM-DD.") from exc


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise ToolError(f"La fecha final ({end}) es anterior a la inicial ({start}).")


def _requests_overlapping(start: date, end: date) -> list[dict[str, Any]]:
    """Solicitudes cuyo rango [StartDate, EndDate] se cruza con [start, end]."""
    return _query(
        """
        SELECT r.Id AS RequestId, u.UserId, u.UserName, u.Email,
               date(r.StartDate) AS StartDate, date(r.EndDate) AS EndDate, r.RequestedDays
        FROM VacationRequests r
        JOIN Users u ON u.UserId = r.UserId
        WHERE date(r.StartDate) <= :end AND date(r.EndDate) >= :start
        ORDER BY date(r.StartDate), u.UserName
        """,
        {"start": start.isoformat(), "end": end.isoformat()},
    )


# --------------------------------------------------------------------------- tools


@mcp.tool(annotations=READ_ONLY)
def vacations_in_period(start_date: str, end_date: str) -> dict[str, Any]:
    """Personas que tienen vacaciones solicitadas dentro de un periodo (total o parcialmente).

    Args:
        start_date: Inicio del periodo, YYYY-MM-DD.
        end_date: Fin del periodo, YYYY-MM-DD (inclusive).
    """
    start = _parse_date(start_date, date.today())
    end = _parse_date(end_date, start)
    _check_range(start, end)
    rows = _requests_overlapping(start, end)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "people_count": len({r["UserId"] for r in rows}),
        "requests": rows,
    }


@mcp.tool(annotations=READ_ONLY)
def remaining_vacation_days(name: str | None = None, year: int | None = None) -> dict[str, Any]:
    """Días de vacaciones restantes de todas las personas (o de quienes coincidan con un nombre).

    AvailablePtos es el total de días del año, sin descontar lo usado. Los días restantes se
    calculan como AvailablePtos menos los días solicitados (RequestedDays) en ese año; cada
    solicitud cuenta en el año de su fecha de inicio.

    Args:
        name: Filtro opcional por nombre (coincidencia parcial, sin distinguir mayúsculas).
        year: Año a calcular. Por defecto, el año actual.
    """
    year = year or date.today().year
    rows = _query(
        """
        SELECT u.UserId, u.UserName, u.Email,
               u.AvailablePtos AS TotalDays,
               COALESCE(SUM(r.RequestedDays), 0) AS UsedDays,
               u.AvailablePtos - COALESCE(SUM(r.RequestedDays), 0) AS RemainingDays
        FROM Users u
        LEFT JOIN VacationRequests r
               ON r.UserId = u.UserId AND strftime('%Y', r.StartDate) = :year
        WHERE :name IS NULL OR u.UserName LIKE '%' || :name || '%'
        GROUP BY u.UserId
        ORDER BY u.UserName
        """,
        {"year": str(year), "name": name},
    )
    return {"year": year, "people": rows}


@mcp.tool(annotations=READ_ONLY)
def vacations_next_week(reference_date: str | None = None) -> dict[str, Any]:
    """Personas que estarán de vacaciones la próxima semana (lunes a domingo).

    Args:
        reference_date: Fecha desde la que se calcula "la próxima semana", YYYY-MM-DD.
            Por defecto, hoy.
    """
    ref = _parse_date(reference_date, date.today())
    start = ref + timedelta(days=7 - ref.weekday())
    end = start + timedelta(days=6)
    rows = _requests_overlapping(start, end)
    return {
        "week": {"start": start.isoformat(), "end": end.isoformat()},
        "people_count": len({r["UserId"] for r in rows}),
        "requests": rows,
    }


@mcp.tool(annotations=READ_ONLY)
def overlapping_vacations(
    start_date: str | None = None, end_date: str | None = None, min_people: int = 2
) -> dict[str, Any]:
    """Cuántas y cuáles personas estarán de vacaciones al mismo tiempo.

    Devuelve tramos de días consecutivos en los que coincide el mismo grupo de personas,
    solo cuando el grupo tiene al menos `min_people` integrantes.

    Args:
        start_date: Inicio del análisis, YYYY-MM-DD. Por defecto, hoy.
        end_date: Fin del análisis, YYYY-MM-DD. Por defecto, 90 días después del inicio.
        min_people: Mínimo de personas coincidiendo para reportar un tramo (por defecto 2).
    """
    start = _parse_date(start_date, date.today())
    end = _parse_date(end_date, start + timedelta(days=90))
    _check_range(start, end)
    requests = _requests_overlapping(start, end)

    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    day = start
    while day <= end:
        iso = day.isoformat()
        people = sorted({r["UserName"] for r in requests if r["StartDate"] <= iso <= r["EndDate"]})
        if len(people) >= max(min_people, 1):
            if current and current["people"] == people:
                current["end"] = iso
            else:
                current = {"start": iso, "end": iso, "people_count": len(people), "people": people}
                segments.append(current)
        else:
            current = None
        day += timedelta(days=1)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "max_simultaneous": max((s["people_count"] for s in segments), default=0),
        "segments": segments,
    }


@mcp.tool(annotations=READ_ONLY)
def people_without_vacations(year: int | None = None) -> dict[str, Any]:
    """Personas que no han tomado (ni tienen solicitadas) vacaciones en un año.

    Args:
        year: Año a revisar. Por defecto, el año actual.
    """
    year = year or date.today().year
    rows = _query(
        """
        SELECT u.UserId, u.UserName, u.Email, u.AvailablePtos AS RemainingDays
        FROM Users u
        WHERE NOT EXISTS (
            SELECT 1 FROM VacationRequests r
            WHERE r.UserId = u.UserId
              AND strftime('%Y', r.StartDate) <= :year
              AND strftime('%Y', r.EndDate) >= :year
        )
        ORDER BY u.UserName
        """,
        {"year": str(year)},
    )
    return {"year": year, "people_count": len(rows), "people": rows}


@mcp.tool(annotations=READ_ONLY)
def get_schema() -> dict[str, Any]:
    """Esquema de las tablas de la base de datos, útil antes de usar run_select_query."""
    rows = _query("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    return {"tables": {r["name"]: r["sql"] for r in rows}}


_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


@mcp.tool(annotations=READ_ONLY)
def run_select_query(sql: str) -> dict[str, Any]:
    """Ejecuta una consulta SQL de solo lectura (SELECT/WITH) para preguntas no cubiertas
    por las demás herramientas. Devuelve como máximo 500 filas.

    Args:
        sql: Una única sentencia SELECT de SQLite.
    """
    if not _SELECT_RE.match(sql):
        raise ToolError("Solo se permiten consultas SELECT o WITH.")
    try:
        with _connect() as conn:
            rows = [dict(r) for r in conn.execute(sql).fetchmany(MAX_ROWS + 1)]
    except sqlite3.Error as exc:
        raise ToolError(f"Error de SQLite: {exc}") from exc
    return {"row_count": min(len(rows), MAX_ROWS), "truncated": len(rows) > MAX_ROWS, "rows": rows[:MAX_ROWS]}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
