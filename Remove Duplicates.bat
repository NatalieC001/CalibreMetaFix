@echo off
rem ======================================================================
rem  Remove Duplicates from Calibre
rem  Double-click this file. It will:
rem    1. make sure Calibre is closed
rem    2. show an easy-to-read preview in your web browser (nothing deleted yet)
rem    3. ask if you want to merge & remove the duplicates (with a backup first)
rem ======================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Remove Calibre Duplicates

rem ---- find Calibre ------------------------------------------------------
set "CAL_DIR=C:\Program Files\Calibre2"
if not exist "%CAL_DIR%\calibre-debug.exe" set "CAL_DIR=C:\Program Files (x86)\Calibre2"
if not exist "%CAL_DIR%\calibre-debug.exe" (
    echo Could not find Calibre in "C:\Program Files\Calibre2".
    pause
    exit /b 1
)

rem ---- make sure Calibre is closed --------------------------------------
:checkcalibre
tasklist /FI "IMAGENAME eq calibre.exe" 2>nul | find /I "calibre.exe" >nul
if not errorlevel 1 goto calibreopen
tasklist /FI "IMAGENAME eq calibre-server.exe" 2>nul | find /I "calibre-server.exe" >nul
if not errorlevel 1 goto calibreopen
goto preview
:calibreopen
echo.
echo  !! Calibre is still open. Please close Calibre completely,
echo     then press any key to continue.
pause >nul
goto checkcalibre

rem ---- step 1: preview ---------------------------------------------------
:preview
echo.
echo STEP 1 of 2: Checking for duplicates (nothing is deleted yet)...
echo.
"%CAL_DIR%\calibre-debug.exe" -e "%~dp0remove_duplicates.py"
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above. Nothing was changed.
    pause
    exit /b 1
)

echo.
echo Opening the easy-to-read preview in your web browser...
start "" "%~dp0duplicates_preview.html"
echo.
echo Take your time checking the list in your browser.
echo Nothing has been deleted yet.
echo.

rem ---- step 2: apply -----------------------------------------------------
choice /C YN /M "STEP 2 of 2: Merge formats and REMOVE these duplicates"
if errorlevel 2 (
    echo Cancelled - nothing was changed.
    pause
    exit /b 0
)

"%CAL_DIR%\calibre-debug.exe" -e "%~dp0remove_duplicates.py" -- --apply
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
    pause
    exit /b 1
)

echo.
echo All done! Removed copies were sent to the Recycle Bin and a database backup was saved.
echo You can open Calibre again.
pause
