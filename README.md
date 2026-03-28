# Gemini 图片去右下角 Logo（本地 LaMa）

使用开源 **LaMa（Large Mask Inpainting）** 对图片**右下角固定区域**做语义修复，用于去除 Gemini 等生成图右下角的固定角标。**推理完全在本地**，图片不会上传到业务服务器（首次使用需联网下载模型，见下文）。

| 方式 | 说明 |
|------|------|
| 图形界面 | 批量选文件夹、进度与日志：`remove_gemini_logo_gui.py` |
| 命令行单张 | 改脚本内路径：`remove_gemini_logo_lama.py` |
| Windows EXE | 见 `build_exe.bat` / `build_release.bat` |

## 环境要求

- **Python** 3.10～3.12（推荐）；3.13 若依赖冲突可按脚本头部注释处理  
- **PyTorch**（CPU 即可）、**simple-lama-inpainting**、**OpenCV**（打包脚本使用 `opencv-python-headless`）

## 安装依赖

在 CMD 或 PowerShell 中执行（整行复制）：

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install simple-lama-inpainting opencv-python-headless
```

首次运行会从官方渠道下载 **big-lama.pt**（约 200MB），之后会缓存在本机用户目录，可离线复用。也可将 `big-lama.pt` 放到程序同级的 `models\` 目录以实现便携离线（与便携版说明一致）。

## 运行

```bash
# 图形界面（批量）
python remove_gemini_logo_gui.py

# 单张（需先编辑脚本顶部的输入/输出路径）
python remove_gemini_logo_lama.py
```

界面中可调整「宽度比例 / 高度比例」以贴合实际水印大小：**宁小勿大**（过大易整图发糊），留印则略微加大。

## 打包 Windows 可执行文件

- **`build_exe.bat`**：生成 `dist\Gemini去Logo\`，内含 `Gemini去Logo.exe`。  
- **`build_release.bat`**：完整流程（打包、可选复制本机已缓存的 `big-lama.pt`、复制说明、生成 `release\` 下 ZIP）。

含 PyTorch 时体积较大（约 1～2GB 量级），首次打包耗时较长。

## 仓库说明

- **`lama_inpaint_core.py`**：修补核心与批量逻辑。  
- **`Gemini去Logo.spec`**：PyInstaller 规格文件（可与 bat 二选一维护）。  
- **`使用说明_便携版.txt`**：给最终用户（ZIP/便携目录）的阅读说明。

本仓库**不包含** `build/`、`dist/`、`release/*.zip` 等构建产物（见 `.gitignore`），克隆后请本地安装依赖并自行打包。

## 免责声明与商标

本项目为个人技术学习与本地图像处理工具示例。第三方库版权归各自所有者。「Gemini」为 Google 商标，本项目与 Google 无关；请遵守图片来源与使用条款，勿用于侵权或违法用途。

## 许可证

若未另行声明，请以仓库内许可证文件为准；依赖库（PyTorch、LaMa 相关实现等）遵循其各自开源协议。
