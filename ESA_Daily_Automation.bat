@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM ==============================================================================
REM ESA Daily Automation - Windows Task Scheduler Launcher
REM Uses SMB UNC paths for the script, input data, outputs, and logs.
REM ==============================================================================

REM ------------------------------------------------------------------------------
REM 1) ArcGIS Pro Python launcher
REM ------------------------------------------------------------------------------
set "PROPY=C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat"

REM ------------------------------------------------------------------------------
REM 2) SMB script folder and local launch directory
REM ------------------------------------------------------------------------------
set "SMB_ROOT=\\smb.rcnas03.pge.com\SanRamon03\GroupShared\CMT_ETL"
set "SCRIPT_DIR=%SMB_ROOT%\GIS_TEAM\ERM_GIS\Scripts\ESA_Daily_Automation"
REM CMD launches from a local folder. All network paths are absolute UNC paths.
set "WORK_DIR=%SystemRoot%\System32"
set "SCRIPT_PATH=%SCRIPT_DIR%\ESA_Daily_Automation_populate_missing_lat_Long.py"

REM ------------------------------------------------------------------------------
REM 3) Log folder
REM ------------------------------------------------------------------------------
set "LOG_DIR=%SCRIPT_DIR%\TaskScheduler_Logs"

REM ------------------------------------------------------------------------------
REM 4) Paths used by the supplied Python script
REM    Keep these checks aligned with the Python script if its inputs change.
REM ------------------------------------------------------------------------------
set "INPUT_CSV=%SMB_ROOT%\GIS_TEAM\PGE_EVM\External_Received\ESA\D10_ESA.csv"
set "REF_GDB=%SMB_ROOT%\GIS_TEAM\PGE_EVM\Data\Library\Library\HWY_SHN_Postmiles_Tenth.gdb"
set "OUTPUT_FOLDER=%SMB_ROOT%\GIS_TEAM\ERM_GIS\Analysis\ESA"

REM Initialize cleanup flags and a default failure code.
set "PUSHD_ACTIVE=0"
set "EXIT_CODE=1"

REM ------------------------------------------------------------------------------
REM 5) Create the log folder and a locale-independent timestamp
REM    PowerShell is included with Windows; no extra Python modules are needed.
REM ------------------------------------------------------------------------------
if not exist "%LOG_DIR%\" mkdir "%LOG_DIR%" 2>nul
if not exist "%LOG_DIR%\" (
    echo ERROR: Cannot create or access log folder: "%LOG_DIR%"
    exit /b 103
)

set "RUN_STAMP="
for /f "delims=" %%I in ('powershell.exe -NoLogo -NoProfile -NonInteractive -Command "Get-Date -Format yyyyMMdd_HHmmss_fff" 2^>nul') do set "RUN_STAMP=%%I"
if not defined RUN_STAMP set "RUN_STAMP=run_%RANDOM%_%RANDOM%"
set "LOG_FILE=%LOG_DIR%\ESA_Daily_Automation_%RUN_STAMP%.log"

type nul > "%LOG_FILE%" 2>nul
if errorlevel 1 (
    echo ERROR: Cannot write log file: "%LOG_FILE%"
    exit /b 104
)

call :log "=============================================================================="
call :log "ESA Daily Automation Started: %date% %time%"
call :log "Script Path: %SCRIPT_PATH%"
call :log "Local Launch Dir: %WORK_DIR%"
call :log "ArcGIS Pro Python: %PROPY%"
call :log "Log File: %LOG_FILE%"
call :log "=============================================================================="

REM ------------------------------------------------------------------------------
REM 6) Validate the launcher, script, and local launch folder
REM ------------------------------------------------------------------------------
if not exist "%PROPY%" (
    call :log "ERROR: ArcGIS Pro propy.bat was not found: %PROPY%"
    set "EXIT_CODE=100"
    goto :finish
)

if not exist "%SCRIPT_PATH%" (
    call :log "ERROR: ESA Python script was not found: %SCRIPT_PATH%"
    set "EXIT_CODE=101"
    goto :finish
)

if not exist "%WORK_DIR%\" (
    call :log "ERROR: Working directory was not found: %WORK_DIR%"
    set "EXIT_CODE=102"
    goto :finish
)

if not exist "%INPUT_CSV%" (
    call :log "ERROR: Input CSV was not found or is inaccessible: %INPUT_CSV%"
    set "EXIT_CODE=107"
    goto :finish
)

REM A feature class inside a file GDB is validated by ArcPy during execution.
if not exist "%REF_GDB%\" (
    call :log "ERROR: Reference geodatabase was not found or is inaccessible: %REF_GDB%"
    set "EXIT_CODE=108"
    goto :finish
)

if not exist "%OUTPUT_FOLDER%\" mkdir "%OUTPUT_FOLDER%" >> "%LOG_FILE%" 2>&1
if not exist "%OUTPUT_FOLDER%\" (
    call :log "ERROR: Cannot create or access output folder: %OUTPUT_FOLDER%"
    set "EXIT_CODE=109"
    goto :finish
)

call :log "Input CSV: %INPUT_CSV%"
call :log "Reference GDB: %REF_GDB%"
call :log "Output Folder: %OUTPUT_FOLDER%"

REM ------------------------------------------------------------------------------
REM 7) Launch from a local directory and run Python by its full SMB path
REM    pushd/popd operate on the local launch folder and create no drive mapping.
REM ------------------------------------------------------------------------------
pushd "%WORK_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: Could not enter working directory: %WORK_DIR%"
    set "EXIT_CODE=110"
    goto :finish
)
set "PUSHD_ACTIVE=1"

REM Flush Python output promptly and preserve Unicode text in the UTF-8 log.
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

call :log "Launching ESA Python script..."
call "%PROPY%" "%SCRIPT_PATH%" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

REM ------------------------------------------------------------------------------
REM 8) Restore the caller directory and return the result to Task Scheduler
REM ------------------------------------------------------------------------------
:finish
if "%PUSHD_ACTIVE%"=="1" popd

call :log "=============================================================================="
call :log "ESA Daily Automation Finished: %date% %time%"
call :log "Exit Code: %EXIT_CODE%"
call :log "Log File: %LOG_FILE%"
call :log "=============================================================================="

endlocal & exit /b %EXIT_CODE%

REM ------------------------------------------------------------------------------
REM Console and log output helper
REM ------------------------------------------------------------------------------
:log
echo(%~1
>> "%LOG_FILE%" echo(%~1
exit /b 0

