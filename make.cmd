@echo off
rem Windows shim for `make <target>` when GNU make is not installed.
rem cmd.exe: make demo    PowerShell: .\make demo
uv run python "%~dp0scripts\tasks.py" %*
