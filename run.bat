@echo off
cd /d "%~dp0"
".\.venv\Scripts\python.exe" import_recipe.py %*
