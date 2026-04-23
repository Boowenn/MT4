@echo off
setlocal

set "TARGET_URL=%~1"
if "%TARGET_URL%"=="" set "TARGET_URL=http://localhost:8080/QuantGod_Dashboard.html"

set "CHROME_PATH="

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
)

if defined CHROME_PATH (
    start "" "%CHROME_PATH%" --new-window "%TARGET_URL%"
) else (
    start "" "%TARGET_URL%"
)

endlocal
