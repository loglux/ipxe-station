@echo off
rem Minimal bootstrap baked into boot.wim (X:\Windows\System32\startnet.cmd).
rem All real logic lives on the server in start.ps1 so it can change without repacking the WIM.

rem Server that serves /http/provision/ (host:port). Edit here, or repack when the address changes.
set PXE_SERVER=192.168.1.100:9021

wpeinit

rem Wait up to ~2 minutes for an IPv4 address (wpeinit starts the DHCP client).
set /a TRIES=0
:waitnet
ipconfig | find "IPv4" >nul && goto havenet
set /a TRIES+=1
if %TRIES% GEQ 40 goto nonet
ping -n 4 127.0.0.1 >nul
goto waitnet

:nonet
echo No network address obtained. Dropping to a command prompt.
goto :eof

:havenet
if not exist X:\provision mkdir X:\provision
powershell -NoProfile -ExecutionPolicy Bypass -Command "(New-Object Net.WebClient).DownloadFile('http://%PXE_SERVER%/http/provision/start.ps1','X:\provision\start.ps1')"
if not exist X:\provision\start.ps1 (
    echo Could not download start.ps1 from %PXE_SERVER%. Dropping to a command prompt.
    goto :eof
)
powershell -NoProfile -ExecutionPolicy Bypass -File X:\provision\start.ps1 -Server %PXE_SERVER%
