@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 完整发布：生成 EXE + 复制模型 + 打 ZIP
echo ========================================
echo.
echo 将执行：PyInstaller 打包、可选复制 big-lama.pt、写入说明、压缩 release 目录。
echo 请确保已安装：Python 3.10+、torch(CPU)、simple-lama-inpainting、opencv、PyInstaller
echo 打包体积大，可能需要 10～30 分钟，请勿关闭窗口。
echo.
pause

pip install pyinstaller -q

echo.
echo [1/4] PyInstaller 打包中...
pyinstaller --noconfirm --clean --windowed --name "Gemini去Logo" ^
  --collect-all torch ^
  --collect-all torchvision ^
  --collect-all simple_lama_inpainting ^
  --hidden-import=lama_inpaint_core ^
  --hidden-import=PIL._tkinter_finder ^
  --hidden-import=cv2 ^
  remove_gemini_logo_gui.py

if not exist "dist\Gemini去Logo\Gemini去Logo.exe" (
    echo 打包失败：未找到 dist\Gemini去Logo\Gemini去Logo.exe
    pause
    exit /b 1
)

echo.
echo [2/4] 准备 models 目录（便携离线）...
if not exist "dist\Gemini去Logo\models" mkdir "dist\Gemini去Logo\models"

set "CACHED=%USERPROFILE%\.cache\torch\hub\checkpoints\big-lama.pt"
if exist "%CACHED%" (
    copy /Y "%CACHED%" "dist\Gemini去Logo\models\big-lama.pt"
    echo 已从本机缓存复制模型到包内，其它电脑解压后可离线使用。
) else (
    echo 提示：本机尚未缓存 big-lama.pt，ZIP 内暂无模型文件。
    echo       您可在本机先运行一次程序完成下载后，再重新执行本 bat 以打入模型。
)

echo.
echo [3/4] 复制使用说明...
if exist "使用说明_便携版.txt" (
    copy /Y "使用说明_便携版.txt" "dist\Gemini去Logo\使用说明.txt"
) else (
    echo 未找到 使用说明_便携版.txt
)

echo.
echo [4/4] 生成 ZIP（大文件，需数分钟；勿关闭窗口）...
if not exist "release" mkdir "release"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem; $base='%~dp0'; $src=Join-Path $base 'dist\Gemini去Logo'; $dst=Join-Path $base 'release\Gemini去Logo_便携版_win64.zip'; if(Test-Path $dst){Remove-Item -LiteralPath $dst -Force}; [System.IO.Compression.ZipFile]::CreateFromDirectory($src,$dst,[System.IO.Compression.CompressionLevel]::Optimal,$false)"

if exist "release\Gemini去Logo_便携版_win64.zip" (
    echo.
    echo ========================================
    echo 完成
    echo   EXE：dist\Gemini去Logo\Gemini去Logo.exe
    echo   ZIP：release\Gemini去Logo_便携版_win64.zip
    echo ========================================
    echo 请将整个「Gemini去Logo」文件夹或 ZIP 发给他人；不要只发单个 exe。
) else (
    echo ZIP 生成失败，请检查 PowerShell 是否可用。
)

pause
