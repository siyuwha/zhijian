@echo off
chcp 65001 >nul
echo ========================================================
echo   AI认知复盘交易系统 · 停止服务脚本
echo ========================================================

echo 正在停止端口 8000 的后端进程...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo 终止 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo 正在停止端口 3000 的前端进程...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo 终止 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo ========================================================
echo   服务已安全停止。
echo ========================================================
pause
