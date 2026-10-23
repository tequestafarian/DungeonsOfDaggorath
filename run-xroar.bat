@echo off
rem Launch the CoCo 3 disk build in XRoar (512K, RGB monitor) and auto-run it
setlocal
if not exist "%XROAR%" set XROAR=C:\Program Files\6809.org.uk\XRoar 1.10\xroar.exe
cd /d "%~dp0"
start "" "%XROAR%" -m coco3 -ram 512 -tv-input rgb -load-fd0 build\DOD3.DSK -type "RUN\"DOD\"\r"
