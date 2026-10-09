@echo off
chcp 65001 >nul
echo ========================================================
echo   AI认知复盘交易系统 · 交易员驾驶舱一键启动
echo   生产基线: Commit 87e82bf
echo ========================================================

set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

echo [1/3] 检查并启动后端服务 (端口 8000)...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %ERRORLEVEL% equ 0 (
    echo     后端服务已在运行中 (端口 8000).
) else (
    echo     正在启动后端 FastAPI 服务...
    start "AI Trading Backend (:8000)" cmd /k "cd /d %PROJECT_DIR% && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"
    timeout /t 3 /nobreak >nul
)

echo [2/3] 检查并启动前端服务 (端口 3000)...
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul
if %ERRORLEVEL% equ 0 (
    echo     前端服务已在运行中 (端口 3000).
) else (
    echo     正在启动前端 Next.js 服务...
    start "AI Trading Frontend (:3000)" cmd /k "cd /d %PROJECT_DIR%\frontend && npm run dev"
    timeout /t 4 /nobreak >nul
)

echo [3/3] 打开交易员驾驶舱页面...
start http://localhost:3000/cockpit

echo ========================================================
echo   系统已就绪！驾驶舱地址: http://localhost:3000/cockpit
echo ========================================================
pause
