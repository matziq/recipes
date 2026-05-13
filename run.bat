@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . 'D:\aaaScripts\ensure_venv.ps1'; Ensure-Venv -ProjectDir '%~dp0' }"
".\.venv\Scripts\python.exe" import_recipe.py %*
