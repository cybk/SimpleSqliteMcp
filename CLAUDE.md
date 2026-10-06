# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

Servidor MCP en Python (transporte stdio, mismo equipo que el cliente) que expone herramientas de
**solo lectura** para consultar vacaciones del personal en `Vacations.db` (SQLite). Todo el servidor
está en `server.py`; el README documenta las herramientas y la configuración de clientes.

## Comandos

En Windows usa siempre barras normales con el Bash tool o con `!` (bash elimina las `\`).

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python server.py          # arranca el servidor por stdio (espera un cliente)
.venv/Scripts/mcp dev server.py         # MCP Inspector para llamar herramientas a mano
```

No hay tests ni linter. Para probar, conecta un cliente con `mcp.client.stdio.stdio_client` +
`mcp.client.session.ClientSession` y apunta `VACATIONS_DB` a una **copia** de la base en el
scratchpad (con datos de prueba si hace falta). Imprime solo `structured_content` recortado:
los errores del servidor salen por stderr como tracebacks muy largos, así que descarta stderr
(`2>/dev/null`) y usa `PYTHONIOENCODING=utf-8` para ver bien los acentos.

## Arquitectura y decisiones

- **SDK `mcp` 2.x:** `FastMCP` ya no existe; se usa `from mcp.server.mcpserver import MCPServer`.
  Los errores para el cliente se lanzan con `ToolError` (`mcp.server.mcpserver.exceptions`); cualquier
  otra excepción llega solo como "Error executing tool …" sin el motivo.
- **Solo lectura en dos capas:** `_connect()` abre con URI `mode=ro` + `PRAGMA query_only = ON`, y
  `run_select_query` además exige que la SQL empiece por `SELECT`/`WITH`. El filtro de texto no basta
  por sí solo (`WITH … DELETE` lo pasa); la protección real es `mode=ro`. No añadir herramientas de escritura.
- **Ruta de la base:** variable de entorno `VACATIONS_DB`; por defecto `Vacations.db` junto a `server.py`.
- Las herramientas devuelven `dict` (salida estructurada) y llevan `ToolAnnotations(readOnlyHint=True)`.
- Las salidas nunca incluyen llaves (`Id`, `UserId`, `RequestId`): se filtran con `_without_keys`
  (también en `run_select_query`). Se pueden usar internamente, p. ej. para contar personas distintas.
- `overlapping_vacations` calcula en Python, día por día, qué personas coinciden y agrupa días
  consecutivos con el mismo grupo en tramos.

## Modelo de datos (`Vacations.db`)

- `Users(UserId PK, UserName, Email, AvailablePtos)`. `VacationRequests(Id PK, StartDate, EndDate,
  RequestedDays, UserId → Users(UserId))`.
- Fechas en texto ISO `YYYY-MM-DD`. Los nombres tienen acentos (UTF-8).
- `AvailablePtos` es el **total anual sin descontar lo usado**. Días restantes =
  `AvailablePtos - SUM(RequestedDays)` de las solicitudes que **empiezan** en el año.
- `RequestedDays` no siempre coincide con el rango de fechas. Para contar días se usa
  `RequestedDays`; para saber quién está ausente en una fecha se usa el rango, con `EndDate` inclusive.
- `fix_fk.py` fue una migración de una sola vez (la FK apuntaba a `Users(Id)`, que no existe); ya está aplicada.

## Permisos

Modificar `Vacations.db` (migraciones, datos) está bloqueado para Claude por el sistema de permisos:
prepara un script y pide al usuario que lo ejecute con `! .venv/Scripts/python <script>.py`.
La base la edita el usuario con otro programa; si aparece `Vacations.db-journal`, puede haber
cambios sin guardar ahí.
