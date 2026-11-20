@echo off
cd /d "%~dp0\.."
for %%V in (vfs\minimal.csv vfs\several.csv vfs\deep.csv) do (
    echo --- %%V ---
    python -m src.main --vfs "%%V" --script scripts\stage3.txt
)
