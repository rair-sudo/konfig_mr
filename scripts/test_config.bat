@echo off
cd /d "%~dp0\.."
echo --- Po umolchaniyu ---
echo exit | python -m src.main
echo --- Tolko VFS ---
echo exit | python -m src.main --vfs vfs\minimal.csv
echo --- Tolko script ---
python -m src.main --script scripts\stage2.txt
echo --- Oba parametra ---
python -m src.main --vfs vfs\minimal.csv --script scripts\stage2.txt
