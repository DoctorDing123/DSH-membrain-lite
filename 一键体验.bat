@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================================
echo   membrain-lite 一键体验
echo   给它 29 条示例记忆，然后画出它脑子里的样子
echo ==========================================================
echo.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  echo [!] 没找到 Python。
  echo     去 https://www.python.org/downloads/ 装 3.9 或更新的版本，
  echo     安装界面记得勾上 "Add python.exe to PATH"，然后重新双击我。
  echo.
  pause
  exit /b 1
)

echo [1/3] 建库 + 写入 29 条示例记忆 ...
%PY% -m membrain init
%PY% -m membrain demo
if errorlevel 1 goto fail

echo.
echo [2/3] 导出放射图用的数据 ...
%PY% -m membrain export --out examples\radial\memories.jsonl
if errorlevel 1 goto fail

if /i "%~1"=="dry" (
  echo.
  echo [dry] 只跑到这里，不启动网页。
  exit /b 0
)

echo.
echo [3/3] 启动本地网页，浏览器马上会自动打开 ...
echo       看够了就把这个黑窗口关掉，服务就停了。
echo.
start "" "http://127.0.0.1:8766/examples/radial/"
%PY% -m http.server 8766 --bind 127.0.0.1
goto :eof

:fail
echo.
echo [!] 出错了。把上面最后几行贴出来，就能看出卡在哪。
pause
exit /b 1
