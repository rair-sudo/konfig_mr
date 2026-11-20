@echo off
cd /d "%~dp0\.."
for %%S in (scripts\stage4.txt scripts\stage5.txt) do (
    echo --- %%S ---
    python -m src.main --vfs vfs\deep.csv --script "%%S"
)
