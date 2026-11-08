@echo off
title Preparar Repositorio para la Nube
cd /d "%~dp0"
chcp 65001 > nul

echo ====================================================
echo   Preparando proyecto para Alojamiento en la Nube
echo ====================================================
echo.

git init
git branch -M main
git add .
git commit -m "Cripto Trading Bot para la nube 24/7"

echo.
echo ====================================================
echo   [OK] Proyecto preparado localmente con Git
echo ====================================================
echo.
echo Pasos finales para subirlo a tu GitHub:
echo  1. Crea un repositorio vacio en github.com
echo  2. Copia la URL de tu repositorio
echo  3. En esta consola ejecuta:
echo     git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
echo     git push -u origin main
echo.
pause
