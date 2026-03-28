# -*- coding: utf-8 -*-
"""
Gemini 右下角 Logo 去除 — 图形界面（批量选文件夹、显示进度与日志）。
依赖与命令行版相同，打包 EXE 见 build_exe.bat。
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from lama_inpaint_core import InpaintConfig, run_batch


def _ts() -> str:
    """当前时间字符串，用于日志行首。"""
    return time.strftime("%H:%M:%S")


class GeminiWatermarkApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Gemini 图片去右下角 Logo（本地 LaMa）")
        self.minsize(720, 520)
        self.geometry("860x600")

        self._var_in = tk.StringVar(value="")
        self._var_out = tk.StringVar(value="")
        self._var_recursive = tk.BooleanVar(value=False)
        self._var_force_cpu = tk.BooleanVar(value=True)
        self._var_wratio = tk.StringVar(value="0.12")
        self._var_hratio = tk.StringVar(value="0.065")

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

        self._build_ui()
        self.after(200, self._pump_queue)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="待处理文件夹（内含 png / jpg / jpeg）:").grid(row=0, column=0, sticky=tk.W, **pad)
        row1 = ttk.Frame(frm)
        row1.grid(row=1, column=0, columnspan=3, sticky=tk.EW, **pad)
        ent_in = ttk.Entry(row1, textvariable=self._var_in, width=70)
        ent_in.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row1, text="浏览…", command=self._pick_input).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frm, text="保存到的文件夹:").grid(row=2, column=0, sticky=tk.W, **pad)
        row2 = ttk.Frame(frm)
        row2.grid(row=3, column=0, columnspan=3, sticky=tk.EW, **pad)
        ent_out = ttk.Entry(row2, textvariable=self._var_out, width=70)
        ent_out.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="浏览…", command=self._pick_output).pack(side=tk.LEFT, padx=(8, 0))

        opt = ttk.Frame(frm)
        opt.grid(row=4, column=0, columnspan=3, sticky=tk.W, **pad)
        ttk.Checkbutton(opt, text="包含子文件夹（递归处理）", variable=self._var_recursive).pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Checkbutton(opt, text="强制使用 CPU（无显卡时建议勾选）", variable=self._var_force_cpu).pack(
            side=tk.LEFT
        )

        adv = ttk.LabelFrame(
            frm,
            text="右下角 Logo 框（占整图比例，宁小勿大；过大整片会糊，过小会留印）",
        )
        adv.grid(row=5, column=0, columnspan=3, sticky=tk.EW, **pad)
        ttk.Label(adv, text="宽度比例:").pack(side=tk.LEFT, padx=(8, 4), pady=6)
        ttk.Entry(adv, textvariable=self._var_wratio, width=8).pack(side=tk.LEFT)
        ttk.Label(adv, text="高度比例:").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Entry(adv, textvariable=self._var_hratio, width=8).pack(side=tk.LEFT, padx=(0, 8))

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=3, **pad)
        self._btn_start = ttk.Button(btn_row, text="开始批量处理", command=self._on_start)
        self._btn_start.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(frm, text="总体进度:").grid(row=7, column=0, sticky=tk.W, **pad)
        self._progress = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self._progress.grid(row=8, column=0, columnspan=3, sticky=tk.EW, **pad)
        self._lbl_stats = ttk.Label(frm, text="就绪。首次运行会下载模型（约 200MB），请保持联网。")
        self._lbl_stats.grid(row=9, column=0, columnspan=3, sticky=tk.W, **pad)

        ttk.Label(frm, text="处理过程（逐张记录）:").grid(row=10, column=0, sticky=tk.W, **pad)
        self._log = tk.Text(frm, height=16, wrap=tk.WORD, state=tk.DISABLED, font=("Microsoft YaHei UI", 9))
        self._log.grid(row=11, column=0, columnspan=3, sticky=tk.NSEW, **pad)
        sb = ttk.Scrollbar(frm, command=self._log.yview)
        sb.grid(row=11, column=3, sticky=tk.NS)
        self._log["yscrollcommand"] = sb.set

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(11, weight=1)

    def _pick_input(self) -> None:
        p = filedialog.askdirectory(title="选择待处理的文件夹")
        if p:
            self._var_in.set(p)

    def _pick_output(self) -> None:
        p = filedialog.askdirectory(title="选择保存结果的文件夹")
        if p:
            self._var_out.set(p)

    def _append_log(self, line: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, line + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)

    def _parse_config(self) -> tuple[InpaintConfig | None, str]:
        try:
            wr = float(self._var_wratio.get().strip().replace(",", "."))
            hr = float(self._var_hratio.get().strip().replace(",", "."))
        except ValueError:
            return None, "宽度/高度比例必须是数字（例如 0.22）。"
        if not (0 < wr <= 1 and 0 < hr <= 1):
            return None, "比例必须在 0 到 1 之间（不含 0）。"
        return (
            InpaintConfig(
                logo_width_ratio=wr,
                logo_height_ratio=hr,
                force_cpu=self._var_force_cpu.get(),
            ),
            "",
        )

    def _on_start(self) -> None:
        if self._running:
            messagebox.showinfo("提示", "正在处理中，请等待当前任务结束。")
            return
        in_dir = self._var_in.get().strip()
        out_dir = self._var_out.get().strip()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showerror("错误", "请选择有效的「待处理文件夹」。")
            return
        if not out_dir:
            messagebox.showerror("错误", "请选择「保存到的文件夹」。")
            return
        os.makedirs(out_dir, exist_ok=True)

        cfg, err = self._parse_config()
        if cfg is None:
            messagebox.showerror("参数错误", err)
            return

        self._running = True
        self._btn_start.configure(state=tk.DISABLED)
        self._progress["value"] = 0
        self._append_log(f"[{_ts()}] ——— 开始新任务 ———")
        self._append_log(f"[{_ts()}] 输入：{in_dir}")
        self._append_log(f"[{_ts()}] 输出：{out_dir}")
        self._append_log(f"[{_ts()}] 子文件夹：{'是' if self._var_recursive.get() else '否'}")

        def worker() -> None:
            def push(d: dict) -> None:
                self._queue.put(d)

            run_batch(
                in_dir,
                out_dir,
                cfg,
                self._var_recursive.get(),
                on_progress=push,
            )

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _pump_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                self._handle_progress(item)
        except queue.Empty:
            pass
        self.after(200, self._pump_queue)

    def _handle_progress(self, d: dict) -> None:
        ev = d.get("event")
        if ev == "start":
            total = d.get("total", 0)
            self._append_log(f"[{_ts()}] 扫描完成：共 {total} 张待处理图片。")
            if total == 0:
                self._lbl_stats.configure(text="未找到支持的图片（.png / .jpg / .jpeg）。")
            else:
                self._lbl_stats.configure(text=f"共 {total} 张，准备加载模型…")
        elif ev == "fatal":
            self._append_log(f"[{_ts()}] 【失败】{d.get('message', '')}")
            self._lbl_stats.configure(text="模型加载失败，请查看日志。")
            messagebox.showerror("模型加载失败", str(d.get("message", ""))[:800])
            self._finish_run()
        elif ev == "model_ready":
            self._append_log(f"[{_ts()}] 模型已就绪，计算设备：{d.get('device', '')}")
            self._lbl_stats.configure(text="模型已加载，正在逐张处理…")
        elif ev == "file_begin":
            i, n = d["index"], d["total"]
            self._append_log(f"[{_ts()}] ({i}/{n}) 处理中：{d.get('rel', d.get('path', ''))}")
            self._lbl_stats.configure(text=f"正在处理 {i}/{n} …")
            if n > 0:
                self._progress["value"] = 100.0 * (i - 1) / n
        elif ev == "file_done":
            i, n = d["index"], d["total"]
            ok = d.get("ok")
            sec = d.get("elapsed_sec", 0.0)
            if ok:
                self._append_log(f"[{_ts()}] ({i}/{n}) ✓ 完成，耗时 {sec:.1f} 秒")
            else:
                self._append_log(f"[{_ts()}] ({i}/{n}) ✗ 失败：{d.get('message', '')[:500]}")
            if n > 0:
                self._progress["value"] = 100.0 * i / n
        elif ev == "done":
            ok_c = d.get("ok_count", 0)
            fail_c = d.get("fail_count", 0)
            tsec = d.get("total_sec", 0.0)
            bt = d.get("batch_total")
            if bt == 0:
                self._append_log(f"[{_ts()}] 未找到可处理图片，已结束（未加载模型）。")
                self._lbl_stats.configure(text="未找到 png/jpg/jpeg 图片。")
            else:
                self._append_log(
                    f"[{_ts()}] ——— 全部结束 ——— 成功 {ok_c} 张，失败 {fail_c} 张，总耗时 {tsec:.1f} 秒"
                )
                self._lbl_stats.configure(text=f"完成：成功 {ok_c}，失败 {fail_c}，总耗时 {tsec:.1f} 秒")
                messagebox.showinfo(
                    "完成",
                    f"处理结束。\n成功：{ok_c} 张\n失败：{fail_c} 张\n总耗时：{tsec:.1f} 秒",
                )
            self._finish_run()

    def _finish_run(self) -> None:
        self._running = False
        self._btn_start.configure(state=tk.NORMAL)


def main() -> None:
    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = GeminiWatermarkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
