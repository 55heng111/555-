@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 打包「Gemini 去 Logo」图形界面为 EXE
echo ========================================
echo.
echo 请先确认已安装：Python 3.10+、torch、simple-lama-inpainting、PyInstaller
echo 将生成文件夹 dist\Gemini去Logo\ ，其中 Gemini去Logo.exe 可双击运行。
echo 注意：含 PyTorch 时体积较大（约 1～2GB），首次打包需较长时间。
echo 需要「EXE + 说明 + 可选模型 + 一键 ZIP」请运行：build_release.bat
echo.
pause

pip install pyinstaller -q
pyinstaller --noconfirm --clean --windowed --name "Gemini去Logo" ^
  --collect-all torch ^
  --collect-all torchvision ^
  --collect-all simple_lama_inpainting ^
  --hidden-import=lama_inpaint_core ^
  --hidden-import=PIL._tkinter_finder ^
  --hidden-import=cv2 ^
  remove_gemini_logo_gui.py

echo.
if exist "dist\Gemini去Logo\Gemini去Logo.exe" (
    echo 成功：dist\Gemini去Logo\Gemini去Logo.exe
) else (
    echo 若失败，请尝试在 PowerShell 中查看报错，或安装：pip install opencv-python-headless
)
pause
