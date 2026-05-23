@echo off
setlocal EnableExtensions

set "HERE=%~dp0"
set "APP=%HERE%import_recipe.py"
set "VENV=%HERE%.venv"
set "PY=%VENV%\Scripts\python.exe"
set "REQ=%HERE%requirements.txt"
set "FALLBACK_PY=D:\Python\python.exe"

call :venv_is_usable
if errorlevel 1 (
	echo Recipes Site virtual environment is missing or points to a removed Python install.
	echo Rebuilding virtual environment...
	call :rebuild_venv
	if errorlevel 1 goto :fallback_direct
	call :venv_is_usable
	if errorlevel 1 goto :fallback_direct
)

"%PY%" "%APP%" %*
exit /b %errorlevel%

:fallback_direct
if exist "%FALLBACK_PY%" (
	if exist "%REQ%" (
		"%FALLBACK_PY%" -m pip install -r "%REQ%"
		if errorlevel 1 goto :error
	)
	"%FALLBACK_PY%" "%APP%" %*
	exit /b %errorlevel%
)
goto :error

:venv_is_usable
if not exist "%PY%" exit /b 1
set "VENV_HOME="
if exist "%VENV%\pyvenv.cfg" (
	for /f "tokens=1,* delims==" %%A in ('findstr /b /i "home" "%VENV%\pyvenv.cfg" 2^>nul') do set "VENV_HOME=%%B"
)
if defined VENV_HOME if "%VENV_HOME:~0,1%"==" " set "VENV_HOME=%VENV_HOME:~1%"
if defined VENV_HOME if not exist "%VENV_HOME%\python.exe" exit /b 1
exit /b 0

:rebuild_venv
set "BOOTSTRAP_PY="
if exist "D:\Python\python.exe" set "BOOTSTRAP_PY=D:\Python\python.exe"
if not defined BOOTSTRAP_PY where py.exe >nul 2>nul && set "BOOTSTRAP_PY=py -3"
if not defined BOOTSTRAP_PY where python.exe >nul 2>nul && set "BOOTSTRAP_PY=python"
if not defined BOOTSTRAP_PY exit /b 1
if exist "%VENV%" rmdir /s /q "%VENV%"
"%BOOTSTRAP_PY%" -m venv "%VENV%"
if errorlevel 1 exit /b 1
"%PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
if exist "%REQ%" (
	"%PY%" -m pip install -r "%REQ%"
	if errorlevel 1 exit /b 1
)
exit /b 0

:error
echo Failed to start Recipes Site tool.
pause
exit /b 1
