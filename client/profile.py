"""Personal-center window for self-managed profile fields and avatar uploads."""

from __future__ import annotations

import base64
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from client.api import MessengerApi


GENDER_IDENTITY_OPTIONS = (
    "女性/Female",
    "男性/Male",
    "不愿透露",
)
MAX_AVATAR_BYTES = 512 * 1024


def _avatar_mime(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"GIF8"):
        return "image/gif"
    return None


class ProfileWindow:
    def __init__(self, parent: tk.Tk, api: MessengerApi, token: str, on_saved: Callable[[dict], None]) -> None:
        self.api, self.token, self.on_saved = api, token, on_saved
        self.busy = False
        self.results: queue.Queue = queue.Queue()
        self.avatar_payload: dict[str, str] | None = None
        self.avatar_changed = False
        self.avatar_image: tk.PhotoImage | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("个人中心 · Secure Messenger")
        self.window.geometry("760x740")
        self.window.minsize(650, 620)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        panel = ttk.Frame(self.window, style="Surface.TFrame", padding=(30, 26))
        panel.grid(sticky="nsew")
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(10, weight=1)
        ttk.Label(panel, text="个人中心", style="SurfaceTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(panel, text=" ", style="SectionCopy.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(5, 22)
        )

        avatar_box = ttk.Frame(panel, style="Surface.TFrame")
        avatar_box.grid(row=2, column=0, rowspan=5, sticky="n", padx=(0, 24))
        self.avatar_label = tk.Label(avatar_box, text="未设置\n头像", width=12, height=6, justify="center", bg="#E7EEF9", fg="#21466E",
                                     font=("Microsoft YaHei UI", 11, "bold"), relief="flat")
        self.avatar_label.pack(fill="both", expand=True)
        ttk.Button(avatar_box, text="选择头像", style="Secondary.TButton", command=self.choose_avatar).pack(fill="x", pady=(12, 5))
        ttk.Button(avatar_box, text="移除头像", style="Secondary.TButton", command=self.clear_avatar).pack(fill="x")
        ttk.Label(avatar_box, text="PNG / JPEG / GIF\n最大 512 KB", style="SectionCopy.TLabel", justify="center").pack(pady=(11, 0))

        self.username = tk.StringVar()
        self.role = tk.StringVar()
        ttk.Label(panel, textvariable=self.username, style="SectionTitle.TLabel").grid(row=2, column=1, sticky="w")
        ttk.Label(panel, textvariable=self.role, style="SectionCopy.TLabel").grid(row=3, column=1, sticky="w", pady=(3, 16))
        ttk.Label(panel, text="性别", style="SectionTitle.TLabel").grid(row=4, column=1, sticky="w")
        self.gender = ttk.Combobox(panel, values=GENDER_IDENTITY_OPTIONS, width=36)
        self.gender.grid(row=5, column=1, sticky="ew", pady=(6, 4))
        ttk.Label(panel, text="可直接填写；留空也可以。", style="SectionCopy.TLabel").grid(row=6, column=1, sticky="w", pady=(0, 14))
        ttk.Label(panel, text="职位", style="SectionTitle.TLabel").grid(row=7, column=0, columnspan=2, sticky="w")
        self.job_title = ttk.Entry(panel)
        self.job_title.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 16))
        ttk.Label(panel, text="个人简介", style="SectionTitle.TLabel").grid(row=9, column=0, columnspan=2, sticky="w")
        self.bio = ScrolledText(panel, height=6, wrap="word", font=("Microsoft YaHei UI", 10), relief="flat", padx=12, pady=10,
                                background="#F7F9FC", highlightthickness=1, highlightbackground="#D9E2EE")
        self.bio.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        actions = ttk.Frame(panel, style="Surface.TFrame")
        actions.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(20, 8))
        ttk.Button(actions, text="取消", style="Secondary.TButton", command=self.close).pack(side="right")
        self.save_button = ttk.Button(actions, text="保存个人资料（Ctrl+S）", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="right", padx=(0, 8))
        self.status = tk.StringVar(value="正在加载个人资料…")
        ttk.Label(panel, textvariable=self.status, style="SectionCopy.TLabel").grid(row=12, column=0, columnspan=2, sticky="w")
        self.timer = self.window.after(80, self.drain_results)
        self.window.bind("<Control-s>", lambda _event: self.save())
        self.request("get_profile", self.loaded)

    def close(self) -> None:
        self.window.after_cancel(self.timer)
        self.window.destroy()

    def request(self, action: str, callback: Callable[[dict], None], **payload: Any) -> None:
        if self.busy:
            return
        self.busy = True
        self.save_button.configure(state="disabled")

        def worker() -> None:
            try:
                data = self.api.call(action, token=self.token, **payload)
            except Exception as exc:
                self.results.put((None, exc, callback))
            else:
                self.results.put((data, None, callback))

        threading.Thread(target=worker, daemon=True).start()

    def drain_results(self) -> None:
        try:
            data, error, callback = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.save_button.configure(state="normal")
            if error is not None:
                self.status.set("操作失败，可稍后重试。")
                messagebox.showerror("个人中心", str(error), parent=self.window)
            else:
                callback(data)
        self.timer = self.window.after(80, self.drain_results)

    def loaded(self, data: dict) -> None:
        user = data["user"]
        self.username.set(user["username"])
        self.role.set("管理员账户" if user["role"] == "admin" else "普通用户账户")
        self.gender.set(user.get("gender_identity", ""))
        self.job_title.delete(0, "end")
        self.job_title.insert(0, user.get("job_title", ""))
        self.bio.delete("1.0", "end")
        self.bio.insert("1.0", user.get("bio", ""))
        self.avatar_payload = user.get("avatar")
        self.avatar_changed = False
        self.display_avatar(self.avatar_payload)
        self.status.set("资料已加载。")

    def choose_avatar(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window, title="选择个人头像", filetypes=(("图像文件", "*.png *.jpg *.jpeg *.gif"), ("所有文件", "*.*"))
        )
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            messagebox.showerror("无法读取头像", str(exc), parent=self.window)
            return
        mime = _avatar_mime(raw)
        if mime is None or len(raw) > MAX_AVATAR_BYTES:
            messagebox.showwarning("头像不符合要求", "请选择不超过 512 KB 的 PNG、JPEG 或 GIF 图片。", parent=self.window)
            return
        self.avatar_payload = {"mime": mime, "data": base64.b64encode(raw).decode("ascii")}
        self.avatar_changed = True
        self.display_avatar(self.avatar_payload)
        self.status.set("新头像已选择，点击保存后生效。")

    def clear_avatar(self) -> None:
        self.avatar_payload = None
        self.avatar_changed = True
        self.display_avatar(None)
        self.status.set("头像将在保存后移除。")

    def display_avatar(self, avatar: dict[str, str] | None) -> None:
        self.avatar_image = None
        if avatar is not None and avatar.get("mime") in {"image/png", "image/gif"}:
            try:
                image = tk.PhotoImage(data=avatar["data"])
                factor = max(1, (max(image.width(), image.height()) + 95) // 96)
                self.avatar_image = image.subsample(factor, factor)
                self.avatar_label.configure(image=self.avatar_image, text="", width=96, height=96)
                return
            except tk.TclError:
                pass
        if avatar is not None:
            self.avatar_label.configure(image="", text="头像已设置\n（保存成功）", width=12, height=6)
        else:
            self.avatar_label.configure(image="", text="未设置\n头像", width=12, height=6)

    def save(self) -> None:
        payload: dict[str, Any] = {
            "gender_identity": self.gender.get().strip(),
            "job_title": self.job_title.get().strip(),
            "bio": self.bio.get("1.0", "end-1c").strip(),
        }
        if self.avatar_changed:
            payload["avatar"] = self.avatar_payload
        self.status.set("正在保存个人资料…")
        self.request("update_profile", self.saved, **payload)

    def saved(self, data: dict) -> None:
        self.on_saved(data["user"])
        self.status.set("已保存个人资料。")
        messagebox.showinfo("个人中心", "个人资料已保存。", parent=self.window)
