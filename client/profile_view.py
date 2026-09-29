"""Read-only public profile card shown to another logged-in account."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from client.api import MessengerApi


class PublicProfileWindow:
    def __init__(self, parent: tk.Tk, api: MessengerApi, token: str, user_id: int) -> None:
        self.api, self.token, self.user_id = api, token, user_id
        self.results: queue.Queue = queue.Queue()
        self.avatar_image: tk.PhotoImage | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("查看个人资料 · Secure Messenger")
        self.window.geometry("610x560")
        self.window.minsize(520, 470)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        panel = ttk.Frame(self.window, style="Surface.TFrame", padding=(30, 28))
        panel.grid(sticky="nsew")
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(6, weight=1)
        ttk.Label(panel, text="个人资料", style="SurfaceTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(panel, text="以下内容由对方在个人中心主动填写。", style="SectionCopy.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 22))
        self.avatar = tk.Label(panel, text="未设置\n头像", width=12, height=6, justify="center", bg="#E7EEF9", fg="#21466E",
                               font=("Microsoft YaHei UI", 11, "bold"), relief="flat")
        self.avatar.grid(row=2, column=0, rowspan=5, sticky="n", padx=(0, 24))
        self.name = tk.StringVar(value="正在加载…")
        self.role = tk.StringVar()
        self.gender = tk.StringVar()
        self.job_title = tk.StringVar()
        ttk.Label(panel, textvariable=self.name, style="SectionTitle.TLabel").grid(row=2, column=1, sticky="w")
        ttk.Label(panel, textvariable=self.role, style="SectionCopy.TLabel").grid(row=3, column=1, sticky="w", pady=(3, 16))
        ttk.Label(panel, text="性别", style="SectionTitle.TLabel").grid(row=4, column=1, sticky="w")
        ttk.Label(panel, textvariable=self.gender, style="SectionCopy.TLabel", wraplength=320).grid(row=5, column=1, sticky="w", pady=(4, 14))
        ttk.Label(panel, text="职位 / 工作身份", style="SectionTitle.TLabel").grid(row=6, column=1, sticky="nw")
        ttk.Label(panel, textvariable=self.job_title, style="SectionCopy.TLabel", wraplength=320).grid(row=7, column=1, sticky="nw", pady=(4, 14))
        ttk.Label(panel, text="个人简介", style="SectionTitle.TLabel").grid(row=8, column=0, columnspan=2, sticky="w", pady=(18, 5))
        self.bio = ScrolledText(panel, height=8, wrap="word", state="disabled", font=("Microsoft YaHei UI", 10), relief="flat", padx=12, pady=10,
                                background="#F7F9FC", highlightthickness=1, highlightbackground="#D9E2EE")
        self.bio.grid(row=9, column=0, columnspan=2, sticky="nsew")
        ttk.Button(panel, text="关闭", style="Secondary.TButton", command=self.close).grid(row=10, column=1, sticky="e", pady=(18, 0))
        self.status = tk.StringVar(value="正在读取资料…")
        ttk.Label(panel, textvariable=self.status, style="SectionCopy.TLabel").grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.timer = self.window.after(80, self.drain_results)
        self.request()

    def close(self) -> None:
        self.window.after_cancel(self.timer)
        self.window.destroy()

    def request(self) -> None:
        def worker() -> None:
            try:
                data = self.api.call("get_user_profile", token=self.token, user_id=self.user_id)
            except Exception as exc:
                self.results.put((None, exc))
            else:
                self.results.put((data, None))

        threading.Thread(target=worker, daemon=True).start()

    def drain_results(self) -> None:
        try:
            data, error = self.results.get_nowait()
        except queue.Empty:
            self.timer = self.window.after(80, self.drain_results)
            return
        if error is not None:
            self.status.set("资料读取失败。")
            messagebox.showerror("查看个人资料", str(error), parent=self.window)
            return
        self.loaded(data["user"])

    def loaded(self, user: dict[str, Any]) -> None:
        self.name.set(user["username"])
        self.role.set("管理员" if user["role"] == "admin" else "普通用户")
        self.gender.set(f"性别：{user.get('gender_identity') or '对方未填写'}")
        self.job_title.set(f"职位：{user.get('job_title') or '对方未填写'}")
        self.bio.configure(state="normal")
        self.bio.delete("1.0", "end")
        self.bio.insert("1.0", user.get("bio") or "对方未填写个人简介。")
        self.bio.configure(state="disabled")
        self.display_avatar(user.get("avatar"))
        self.status.set("资料已加载。")

    def display_avatar(self, avatar: dict[str, str] | None) -> None:
        self.avatar_image = None
        if avatar is not None and avatar.get("mime") in {"image/png", "image/gif"}:
            try:
                image = tk.PhotoImage(data=avatar["data"])
                factor = max(1, (max(image.width(), image.height()) + 95) // 96)
                self.avatar_image = image.subsample(factor, factor)
                self.avatar.configure(image=self.avatar_image, text="", width=96, height=96)
                return
            except tk.TclError:
                pass
        self.avatar.configure(image="", text="头像已设置" if avatar else "未设置\n头像", width=12, height=6)
