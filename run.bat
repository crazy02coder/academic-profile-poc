@echo off
rem Windows komut isteminden baslatici:  run.bat  ->  http://127.0.0.1:8000
rem Komut isteminde "bash" WSL'in bash'ine gider (Linux dagitimi kurulu degilse hata verir); run.sh Git Bash ile calisir.
setlocal
set "GITBASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%GITBASH%" set "GITBASH=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not exist "%GITBASH%" set "GITBASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if not exist "%GITBASH%" (
  echo Git Bash bulunamadi. Git for Windows kurun: https://git-scm.com/download/win
  exit /b 1
)
"%GITBASH%" "%~dp0run.sh"
