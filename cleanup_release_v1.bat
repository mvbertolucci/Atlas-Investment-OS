@echo off
setlocal

echo Limpando artefatos temporarios da release v1.0...

for %%F in (TEST_REPORT_PR*.txt) do (
    if exist "%%F" (
        del /q "%%F"
        echo Removido: %%F
    )
)

if exist "Atlas_Source.zip" (
    del /q "Atlas_Source.zip"
    echo Removido: Atlas_Source.zip
)

echo Limpeza concluida.
endlocal
