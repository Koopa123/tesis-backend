@echo off
REM Lanza edge_agent.py con salida a un log, para que la tarea programada
REM de Windows no pierda lo que imprime (Task Scheduler no muestra consola).
cd /d "%~dp0"
".venv\Scripts\python.exe" edge_agent.py >> edge_agent.log 2>&1
