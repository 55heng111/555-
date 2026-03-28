# -*- coding: utf-8 -*-
"""LaMa 右下角修复核心逻辑，供命令行脚本与图形界面共用。"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass
from typing import Callable, Iterator

# 支持的图片扩展名（小写，带点）
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _apply_bundled_lama_model_env() -> None:
    """
    便携版 / PyInstaller EXE：若程序同目录下存在 models\\big-lama.pt，则优先使用，无需再联网下载。
    未打包时：以当前运行的脚本/程序所在目录为基准。
    """
    import sys

    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    bundled = os.path.join(base, "models", "big-lama.pt")
    if os.path.isfile(bundled) and not os.environ.get("LAMA_MODEL"):
        os.environ["LAMA_MODEL"] = os.path.abspath(bundled)


@dataclass
class InpaintConfig:
    """修复区域与运行设备相关参数。"""

    # Gemini 实际水印只占右下角很小一块；过大会让 LaMa 重绘整片区域 → 糊、假、过渡差
    logo_width_ratio: float = 0.12
    logo_height_ratio: float = 0.065
    logo_min_width_px: int = 20
    logo_min_height_px: int = 20
    # 相对 Logo 框向左、向上多取多少倍「上下文」再裁剪成小图做修复（只动右下角一块，不全图硬推）
    context_expand: float = 2.5
    # 掩码边缘羽化（像素级混合），减轻修补边界生硬感；0 表示关闭
    edge_feather_radius: int = 3
    force_cpu: bool = True


def iter_image_files(folder: str, recursive: bool) -> Iterator[tuple[str, str]]:
    """
    遍历文件夹内待处理图片。
    产出 (绝对路径, 相对 folder 的相对路径)，便于在输出目录保持子目录结构。
    """
    folder = os.path.abspath(folder)
    if not recursive:
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                yield path, name
        return
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder)
            yield path, rel


def _load_image_rgb(pil_image, config: InpaintConfig):
    from PIL import Image

    if pil_image.mode == "P":
        pil_image = pil_image.convert("RGBA")
    if pil_image.mode == "RGBA":
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        background.paste(pil_image, mask=pil_image.split()[3])
        return background
    return pil_image.convert("RGB")


def _make_bottom_right_mask(width: int, height: int, config: InpaintConfig):
    from PIL import Image, ImageDraw

    box_w = max(config.logo_min_width_px, int(width * config.logo_width_ratio))
    box_h = max(config.logo_min_height_px, int(height * config.logo_height_ratio))
    box_w = min(box_w, width)
    box_h = min(box_h, height)
    left = width - box_w
    top = height - box_h
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((left, top, width - 1, height - 1), fill=255)
    return mask, (left, top, box_w, box_h)


def _corner_crop_bounds(
    width: int,
    height: int,
    left: int,
    top: int,
    box_w: int,
    box_h: int,
    expand: float,
) -> tuple[int, int, int, int]:
    """
    右下角补丁区域：紧贴右下，向左、向上扩展，给 LaMa 足够周围纹理参考。
    返回 (crop_left, crop_top, crop_w, crop_h)，其中 crop 右下角与整图对齐。
    """
    pad_w = max(8, int(box_w * expand))
    pad_h = max(8, int(box_h * expand))
    crop_left = max(0, left - pad_w)
    crop_top = max(0, top - pad_h)
    crop_w = width - crop_left
    crop_h = height - crop_top
    return crop_left, crop_top, crop_w, crop_h


def _blend_rgb_with_mask(orig, fixed, soft_mask):
    """按 soft_mask（0～255）在 RGB 上混合 orig 与 fixed，减轻硬边。"""
    import numpy as np
    from PIL import Image

    o = np.array(orig.convert("RGB"), dtype=np.float32)
    f = np.array(fixed.convert("RGB"), dtype=np.float32)
    m = np.array(soft_mask.convert("L"), dtype=np.float32) / 255.0
    m = np.clip(m[..., np.newaxis], 0.0, 1.0)
    out = o * (1.0 - m) + f * m
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _inpaint_corner_patch(
    image_rgb,
    mask_full,
    left: int,
    top: int,
    box_w: int,
    box_h: int,
    lama_model,
    config: InpaintConfig,
):
    """
    仅对右下角一块裁剪后跑 LaMa，再羽化贴回全图。
    返回 (完整 RGB 结果图, crop_left, crop_top, crop_w, crop_h) 供 RGBA 合成。
    """
    from PIL import ImageFilter

    W, H = image_rgb.size
    cl, ct, cw, ch = _corner_crop_bounds(W, H, left, top, box_w, box_h, config.context_expand)
    img_c = image_rgb.crop((cl, ct, cl + cw, ct + ch))
    mask_c = mask_full.crop((cl, ct, cl + cw, ct + ch))

    out_c = lama_model(img_c, mask_c)
    if out_c.size != (cw, ch):
        out_c = out_c.crop((0, 0, cw, ch))

    r = config.edge_feather_radius
    if r > 0:
        soft = mask_c.filter(ImageFilter.GaussianBlur(radius=r))
        blended_c = _blend_rgb_with_mask(img_c, out_c, soft)
    else:
        blended_c = out_c

    full = image_rgb.copy()
    full.paste(blended_c, (cl, ct))
    return full, cl, ct, cw, ch


def _composite_rgba_crop(original_rgba, new_rgb, cl: int, ct: int, cw: int, ch: int):
    """RGBA 原图：仅右下角补丁矩形内用 new_rgb 的像素（补丁边缘已与原图对齐）。"""
    from PIL import Image, ImageDraw

    W, H = original_rgba.size
    new_rgba = new_rgb.convert("RGBA")
    layer_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(layer_mask).rectangle((cl, ct, W - 1, H - 1), fill=255)
    return Image.composite(new_rgba, original_rgba.convert("RGBA"), layer_mask)


def _save_image(result_image, output_path: str, original_format: str | None) -> None:
    from PIL import Image

    ext = os.path.splitext(output_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        to_save = result_image
        if to_save.mode == "RGBA":
            background = Image.new("RGB", to_save.size, (255, 255, 255))
            background.paste(to_save, mask=to_save.split()[3])
            to_save = background
        to_save.save(output_path, format="JPEG", quality=100, subsampling=0, optimize=True)
    elif ext == ".png":
        result_image.save(output_path, format="PNG")
    else:
        fmt = (original_format or "PNG").upper()
        if fmt not in ("PNG", "JPEG", "JPG"):
            fmt = "PNG"
        if fmt in ("JPG", "JPEG"):
            result_image.save(output_path, format="JPEG", quality=100, subsampling=0, optimize=True)
        else:
            result_image.save(output_path, format="PNG")


class LamaInpainter:
    """加载一次 LaMa 模型，可反复处理多张图。"""

    def __init__(self, config: InpaintConfig | None = None) -> None:
        self.config = config or InpaintConfig()
        self._lama = None
        self._device = None

    def ensure_loaded(self) -> tuple[bool, str]:
        """首次调用时加载模型；成功返回 (True, '')，失败返回 (False, 错误说明)。"""
        if self._lama is not None:
            return True, ""
        _apply_bundled_lama_model_env()
        try:
            if self.config.force_cpu:
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
            from PIL import Image  # noqa: F401 — 尽早发现 Pillow 缺失
            import torch
            from simple_lama_inpainting import SimpleLama
        except ImportError as e:
            return False, f"缺少依赖库：{e}\n请先安装 torch、simple-lama-inpainting 等。"

        self._device = torch.device(
            "cuda" if torch.cuda.is_available() and not self.config.force_cpu else "cpu"
        )
        try:
            self._lama = SimpleLama(device=self._device)
        except Exception:
            return False, traceback.format_exc()
        return True, ""

    @property
    def device_str(self) -> str:
        if self._device is None:
            return "未加载"
        return str(self._device)

    def process_file(self, in_path: str, out_path: str) -> tuple[bool, str]:
        """
        处理单张图片。返回 (是否成功, 说明或错误堆栈)。
        调用前需已成功 ensure_loaded。
        """
        from PIL import Image, UnidentifiedImageError

        if self._lama is None:
            return False, "模型尚未加载，请先调用 ensure_loaded。"

        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir and not os.path.isdir(out_dir):
            return False, f"输出目录不存在：{out_dir}"

        try:
            original = Image.open(in_path)
            original.load()
        except UnidentifiedImageError:
            return False, "无法识别为有效图片（文件可能损坏或格式不符）。"
        except OSError as e:
            return False, f"读取文件失败：{e}"

        orig_mode = original.mode
        orig_format = original.format
        width, height = original.size
        if width < 2 or height < 2:
            return False, f"图片尺寸过小：{width}×{height}"

        cfg = self.config
        if not (0 < cfg.logo_width_ratio <= 1 and 0 < cfg.logo_height_ratio <= 1):
            return False, "Logo 区域比例必须在 (0, 1] 之间。"

        try:
            mask, (mleft, mtop, box_w, box_h) = _make_bottom_right_mask(width, height, cfg)
            image_rgb = _load_image_rgb(original, cfg)
            result_rgb, cl, ct, cw, ch = _inpaint_corner_patch(
                image_rgb, mask, mleft, mtop, box_w, box_h, self._lama, cfg
            )
            if orig_mode == "RGBA":
                final_image = _composite_rgba_crop(original, result_rgb, cl, ct, cw, ch)
            else:
                final_image = result_rgb
            _save_image(final_image, out_path, orig_format)
        except Exception:
            return False, traceback.format_exc()
        return True, "ok"


def run_batch(
    input_folder: str,
    output_folder: str,
    config: InpaintConfig,
    recursive: bool,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """
    批量处理。on_progress 会收到字典，例如：
    {"event": "start", "total": n}
    {"event": "file_begin", "index": i, "total": n, "path": str, "out": str}
    {"event": "file_done", "index": i, "ok": bool, "message": str, "elapsed_sec": float}
    {"event": "done", "ok_count": int, "fail_count": int, "total_sec": float}
    """
    import time

    input_folder = os.path.abspath(input_folder)
    output_folder = os.path.abspath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    files = list(iter_image_files(input_folder, recursive))
    total = len(files)
    if on_progress:
        on_progress({"event": "start", "total": total, "input": input_folder, "output": output_folder})

    if total == 0:
        if on_progress:
            on_progress(
                {
                    "event": "done",
                    "ok_count": 0,
                    "fail_count": 0,
                    "total_sec": 0.0,
                    "batch_total": 0,
                }
            )
        return {"ok": True, "ok_count": 0, "fail_count": 0, "total_sec": 0.0, "total": 0}

    inpainter = LamaInpainter(config)
    ok_load, load_msg = inpainter.ensure_loaded()
    if not ok_load:
        if on_progress:
            on_progress({"event": "fatal", "message": load_msg})
        return {"ok": False, "error": load_msg, "ok_count": 0, "fail_count": 0}

    if on_progress:
        on_progress({"event": "model_ready", "device": inpainter.device_str})

    ok_count = 0
    fail_count = 0
    t0 = time.perf_counter()

    for i, (in_path, rel) in enumerate(files, start=1):
        out_path = os.path.join(output_folder, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        t_file = time.perf_counter()
        if on_progress:
            on_progress(
                {
                    "event": "file_begin",
                    "index": i,
                    "total": total,
                    "path": in_path,
                    "out": out_path,
                    "rel": rel,
                }
            )
        ok, msg = inpainter.process_file(in_path, out_path)
        elapsed = time.perf_counter() - t_file
        if ok:
            ok_count += 1
        else:
            fail_count += 1
        if on_progress:
            on_progress(
                {
                    "event": "file_done",
                    "index": i,
                    "total": total,
                    "ok": ok,
                    "message": msg if not ok else "",
                    "elapsed_sec": elapsed,
                    "rel": rel,
                }
            )

    total_sec = time.perf_counter() - t0
    if on_progress:
        on_progress(
            {
                "event": "done",
                "ok_count": ok_count,
                "fail_count": fail_count,
                "total_sec": total_sec,
                "batch_total": total,
            }
        )
    return {
        "ok": True,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "total_sec": total_sec,
        "total": total,
    }
