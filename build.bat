@echo off
echo ==========================================
echo   octoMoA — 构建安装包
echo ==========================================
echo.

echo [1/3] PyInstaller 打包...
uv run pyinstaller octoMoA.spec --noconfirm --log-level WARN
if %errorlevel% neq 0 (
    echo ❌ PyInstaller 打包失败！
    pause
    exit /b 1
)
echo ✅ 打包完成

echo.
echo [2/3] 检查输出...
if not exist "dist\octoMoA\octoMoA.exe" (
    echo ❌ dist\octoMoA\octoMoA.exe 不存在！
    pause
    exit /b 1
)
echo ✅ octoMoA.exe 已生成

echo.
echo [3/3] NSIS 编译安装包...
"C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
if %errorlevel% neq 0 (
    echo ⚠ NSIS 未安装或编译失败。请手动安装 NSIS 后运行:
    echo   "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
) else (
    echo ✅ 安装包已生成: octoMoA-Setup-1.0.0.exe
)

echo.
echo ==========================================
echo   构建流程完成
echo ==========================================
pause
