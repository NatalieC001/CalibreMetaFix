@echo off
rem ======================================================================
rem  Update Calibre Metadata
rem  Double-click this file. It will:
rem    1. ask you to pick a CSV file with the wanted titles/authors/tags
rem    2. show a PREVIEW of every change (nothing is changed yet)
rem    3. ask if you want to apply the changes (a backup is made first)
rem  Only title, authors and tags are changed. Ratings, series, covers,
rem  comments etc. are left alone. Tags are replaced by the CSV's tags.
rem ======================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Update Calibre Metadata

rem ---- find Calibre ------------------------------------------------------
set "CAL_DIR=C:\Program Files\Calibre2"
if not exist "%CAL_DIR%\calibre-debug.exe" set "CAL_DIR=C:\Program Files (x86)\Calibre2"
if not exist "%CAL_DIR%\calibre-debug.exe" (
    echo Could not find Calibre in "C:\Program Files\Calibre2".
    echo Please install Calibre or edit CAL_DIR at the top of this file.
    pause
    exit /b 1
)

rem ---- step 1: choose the CSV -------------------------------------------
echo.
echo STEP 1 of 3: choose the CSV file with the new metadata...
set "CSV="
for /f "usebackq delims=" %%F in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'Choose the CSV with the new metadata'; $d.Filter = 'CSV files (*.csv)|*.csv|All files (*.*)|*.*'; $d.InitialDirectory = '%~dp0'; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "CSV=%%F"
if not defined CSV (
    echo No file chosen - nothing was done.
    pause
    exit /b 0
)
echo Using: %CSV%

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

rem ---- step 2: preview ---------------------------------------------------
:preview
echo.
echo STEP 2 of 3: PREVIEW - nothing is changed yet...
echo.
"%CAL_DIR%\calibre-debug.exe" -e "%~dp0update_calibre_metadata.py" -- --new "%CSV%"
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above. Nothing was changed.
    pause
    exit /b 1
)
echo.
echo Opening the easy-to-read preview in your web browser...
start "" "%~dp0preview.html"
echo.
echo Take your time checking the list in your browser.
echo Nothing has been changed yet.
echo.
choice /C YN /M "STEP 3 of 3: Do these look right? APPLY these changes to Calibre"
if errorlevel 2 (
    echo Cancelled - nothing was changed.
    pause
    exit /b 0
)
"%CAL_DIR%\calibre-debug.exe" -e "%~dp0update_calibre_metadata.py" -- --new "%CSV%" --apply
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
    pause
    exit /b 1
)

rem ---- optional: write metadata into the book files ----------------------
echo.
echo Optional: write the new metadata into the ebook files themselves.
echo (Only needed if you copy books to your PocketBook by hand instead of
echo  using Calibre's "Send to device". Takes a minute or two.)
choice /C YN /M "Write metadata into the book files now"
if not errorlevel 2 "%CAL_DIR%\calibredb.exe" embed_metadata all

echo.
echo All done. You can open Calibre again.
pause
