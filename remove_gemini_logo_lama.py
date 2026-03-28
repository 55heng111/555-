# -*- coding: utf-8 -*-
"""
使用 LaMa（Large Mask Inpainting）开源模型，对图片右下角固定区域做语义修复，
用于去除 Gemini 生成图右下角的固定 Logo。全程本地推理，图片不会上传。

图形界面批量版请运行：remove_gemini_logo_gui.py（可打包为 EXE）。

【依赖安装 - 整行复制到 CMD 或 PowerShell】
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu; pip install simple-lama-inpainting
（推荐 Python 3.10～3.12；首次运行需联网下载模型 big-lama.pt，之后可断网使用缓存。）
Python 3.13 若安装失败，可先装 torch 再：pip install opencv-python-headless "fire>=0.5.0,<0.6.0"; pip install simple-lama-inpainting --no-deps
"""

from __future__ import annotations

import os
import sys

from lama_inpaint_core import InpaintConfig, LamaInpainter

# ---------------------------------------------------------------------------
# 【新手只需改这里】输入 / 输出路径（支持 png、jpg、jpeg）
# ---------------------------------------------------------------------------
INPUT_IMAGE_PATH = r"F:\path\to\your\input.png"
OUTPUT_IMAGE_PATH = r"F:\path\to\your\output.png"

# 与 Gemini 真实水印尺度接近；过大易整片糊掉（见 lama_inpaint_core 说明）
LOGO_WIDTH_RATIO = 0.12
LOGO_HEIGHT_RATIO = 0.065
LOGO_MIN_WIDTH_PX = 20
LOGO_MIN_HEIGHT_PX = 20
FORCE_CPU = True


def _print_error(title: str, detail: str) -> None:
    print("\n" + "=" * 60)
    print(f"【错误】{title}")
    print("-" * 60)
    print(detail.strip())
    print("=" * 60 + "\n")


def main() -> int:
    in_path = INPUT_IMAGE_PATH.strip().strip('"').strip("'")
    out_path = OUTPUT_IMAGE_PATH.strip().strip('"').strip("'")

    if not in_path:
        _print_error("输入路径为空", "请在脚本顶部将 INPUT_IMAGE_PATH 改为你的图片完整路径。")
        return 1
    if not out_path:
        _print_error("输出路径为空", "请在脚本顶部将 OUTPUT_IMAGE_PATH 改为保存结果的完整路径。")
        return 1

    if not os.path.isfile(in_path):
        _print_error(
            "找不到输入文件",
            f"路径不存在或不是文件：\n{in_path}",
        )
        return 1

    ext = os.path.splitext(in_path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        _print_error(
            "不支持的输入格式",
            f"当前仅支持扩展名为 .png / .jpg / .jpeg 的文件，你提供的是：{ext or '（无扩展名）'}",
        )
        return 1

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        _print_error("输出目录不存在", f"请先创建文件夹：\n{out_dir}")
        return 1

    config = InpaintConfig(
        logo_width_ratio=LOGO_WIDTH_RATIO,
        logo_height_ratio=LOGO_HEIGHT_RATIO,
        logo_min_width_px=LOGO_MIN_WIDTH_PX,
        logo_min_height_px=LOGO_MIN_HEIGHT_PX,
        force_cpu=FORCE_CPU,
    )

    inpainter = LamaInpainter(config)
    ok, msg = inpainter.ensure_loaded()
    if not ok:
        _print_error("模型加载失败", msg)
        return 1

    print("\n" + "-" * 60)
    print("准备开始本地 LaMa 修复（首次运行会自动下载模型，请保持网络畅通）")
    print(f"设备：{inpainter.device_str}")
    print("-" * 60 + "\n")

    ok, msg = inpainter.process_file(in_path, out_path)
    if not ok:
        _print_error("处理失败", msg)
        return 1

    print("\n" + "=" * 60)
    print("【成功】处理完成！")
    print(f"已保存到：{out_path}")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
