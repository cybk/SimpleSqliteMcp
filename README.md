# SimpleSqliteMcp

Servidor MCP en Python (transporte **stdio**) para hacer preguntas en lenguaje natural sobre las
vacaciones registradas en `Vacations.db`. El cliente MCP (Claude Desktop, Claude Code, etc.)
traduce la pregunta a llamadas a las herramientas del servidor.

El acceso a la base de datos es **solo lectura**: se abre con `mode=ro` y `PRAGMA query_only`,
así que ninguna herramienta puede modificar datos.

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Requiere Python 3.10+.

## Herramientas

| Herramienta | Para preguntas como |
|---|---|
| `vacations_in_period(start_date, end_date)` | ¿Qué personas pidieron vacaciones entre el 1 y el 31 de diciembre? |
| `remaining_vacation_days(name?, year?)` | ¿Cuántos días de vacaciones le quedan a cada persona? |
| `vacations_next_week(reference_date?)` | ¿Quién sale de vacaciones la próxima semana (lunes a domingo)? |
| `overlapping_vacations(start_date?, end_date?, min_people=2)` | ¿Cuántas y cuáles personas coinciden de vacaciones? (por defecto, los próximos 90 días) |
| `people_without_vacations(year?)` | ¿Quién no ha tomado vacaciones este año? |
| `get_schema()` | Estructura de las tablas. |
| `run_select_query(sql)` | Cualquier otra pregunta: ejecuta un `SELECT` (máx. 500 filas). |

Las fechas usan el formato `YYYY-MM-DD`. `Users.AvailablePtos` es el total de días del año;
los días restantes se calculan como `AvailablePtos - SUM(RequestedDays)` de las solicitudes
que empiezan en ese año.

## Configuración en el cliente

Por defecto se usa el `Vacations.db` que está junto a `server.py`; puedes apuntar a otra base
con la variable de entorno `VACATIONS_DB`.

**Claude Code** (desde la carpeta del proyecto):

```powershell
claude mcp add vacations -- C:\Git\Mcp\SimpleSqliteMcp\.venv\Scripts\python.exe C:\Git\Mcp\SimpleSqliteMcp\server.py
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "vacations": {
      "command": "C:\\Git\\Mcp\\SimpleSqliteMcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Git\\Mcp\\SimpleSqliteMcp\\server.py"]
    }
  }
}
```

Usa siempre el `python.exe` del venv para que encuentre el paquete `mcp`.

## Probar sin un cliente

```powershell
.\.venv\Scripts\Activate.ps1
mcp dev server.py
```

Abre el MCP Inspector en el navegador para llamar a las herramientas manualmente.
