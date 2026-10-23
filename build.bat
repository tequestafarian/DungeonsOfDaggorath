@echo off
rem Build Dungeons of Daggorath for the CoCo 3
rem   build\dod.rom   - original 8K cartridge image ($C000), unchanged
rem   build\dod3.rom  - CoCo 3 edition: game + GIME engine ($C000)
rem   build\td_blk*   - top-down tiles and sprites (tools\topdown\make_assets.py)
rem   build\DOD3.DSK  - Disk BASIC disk (512K CoCo 3):
rem                       RUN"DOD"   CoCo 3 edition
rem                       RUN"DOD1"  original game
setlocal
if not exist "%LWTOOLS%\lwasm.exe" set LWTOOLS=C:\apps\coco\Projects\lwtools-4.24
if not exist "%TOOLSHED%\decb.exe" set TOOLSHED=C:\apps\coco\toolshed-2.2
cd /d "%~dp0"
if not exist build mkdir build

"%LWTOOLS%\lwasm.exe" --raw -obuild\dod.rom -lbuild\dod.lst --symbol-dump=build\dod.sym DAGGORATH.ASM || goto :fail
python -I tools\topdown\make_assets.py build || goto :fail
"%LWTOOLS%\lwasm.exe" --raw --define=COCO3 -obuild\dod3.rom -lbuild\dod3.lst --symbol-dump=build\dod3.sym DAGGORATH.ASM || goto :fail
pushd coco3
"%LWTOOLS%\lwasm.exe" --decb -o..\build\DOD1.BIN -l..\build\dodload.lst DODLOAD.ASM || (popd & goto :fail)
"%LWTOOLS%\lwasm.exe" --decb -o..\build\DOD.BIN -l..\build\dod3ld.lst DOD3LD.ASM || (popd & goto :fail)
popd

if exist build\DOD3.DSK del build\DOD3.DSK
"%TOOLSHED%\decb.exe" dskini build\DOD3.DSK || goto :fail
"%TOOLSHED%\decb.exe" copy -2 -b build\DOD.BIN build\DOD3.DSK,DOD.BIN || goto :fail
"%TOOLSHED%\decb.exe" copy -0 -t -l coco3\DOD.BAS build\DOD3.DSK,DOD.BAS || goto :fail
"%TOOLSHED%\decb.exe" copy -2 -b build\DOD1.BIN build\DOD3.DSK,DOD1.BIN || goto :fail
"%TOOLSHED%\decb.exe" copy -0 -t -l coco3\DOD1.BAS build\DOD3.DSK,DOD1.BAS || goto :fail
echo Built build\DOD3.DSK
exit /b 0

:fail
echo BUILD FAILED
exit /b 1
