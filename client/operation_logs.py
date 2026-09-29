"""Administrator audit-log viewer backed by the service database."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from client.api import MessengerApi


ACTION_NAMES = {
    "register": "用户注册",
    "login": "登录系统",
    "logout": "退出登录",
    "send_message": "发送消息",
    "admin_create_user": "创建用户",
    "admin_update_user": "修改用户",
    "admin_delete_user": "删除用户",
    "admin_reset_password": "重置密码",
    "admin_moderate_message": "审核消息",
}


class OperationLogWindow:
    """A paged, read-only view. It intentionally never renders credentials or message text."""

    def __init__(self, parent: tk.Tk, api: MessengerApi, token: str) -> None:
        self.api, self.token = api, token
        self.rows: dict[str, dict[str, Any]] = {}
        self.after_id = 0
        self.pages: list[int] = []
        self.has_more = False
        self.busy = False
        self.results: queue.Queue = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.window.title("操作日志 · Secure Messenger")
        self.window.geometry("1060x700")
        self.window.minsize(820, 560)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        panel = ttk.Frame(self.window, style="Surface.TFrame", padding=22)
        panel.grid(sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        ttk.Label(panel, text="系统操作日志", style="SurfaceTitle.TLabel").grid(row=0, column=0, sticky="w")
        toolbar = ttk.Frame(panel, style="Surface.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=12)
        ttk.Label(toolbar, text="搜索账号、动作或说明").pack(side="left")
        self.search = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search, width=28)
        search_entry.pack(side="left", padx=8)
        search_entry.bind("<Return>", lambda _event: self.reset_page())
        self.refresh_button = ttk.Button(toolbar, text="查询 / 返回第一页", command=self.reset_page, style="Secondary.TButton")
        self.refresh_button.pack(side="right")

        table = ttk.Frame(panel)
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("id", "time", "actor", "action", "result", "target", "detail"),
                                 show="headings", selectmode="browse", height=13)
        for key, title, width in (
            ("id", "编号", 60), ("time", "时间", 155), ("actor", "操作账号", 125),
            ("action", "动作", 110), ("result", "结果", 70), ("target", "目标", 125), ("detail", "说明", 190),
        ):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=48, anchor="center" if key != "detail" else "w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("failed", foreground="#B42342")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_detail())

        ttk.Label(panel, text="选中记录详情", style="SectionTitle.TLabel").grid(row=3, column=0, sticky="w", pady=(14, 5))
        self.detail = ScrolledText(panel, height=5, wrap="word", state="disabled", font=("Microsoft YaHei UI", 10))
        self.detail.grid(row=4, column=0, sticky="ew")
        actions = ttk.Frame(panel, style="Surface.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=12)
        self.next_button = ttk.Button(actions, text="下一页", command=self.next_page)
        self.next_button.pack(side="right")
        self.previous_button = ttk.Button(actions, text="上一页", command=self.previous_page)
        self.previous_button.pack(side="right", padx=8)
        self.status = tk.StringVar(value="每页 50 条；日志不保存密码、会话令牌或消息正文。")
        ttk.Label(panel, textvariable=self.status, style="SectionCopy.TLabel").grid(row=6, column=0, sticky="w")
        self.timer = self.window.after(80, self.drain_results)
        self.load()

    def close(self) -> None:
        self.window.after_cancel(self.timer)
        self.window.destroy()

    def request(self, action: str, callback: Callable[[dict], None], **payload: Any) -> None:
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        self.status.set("正在读取日志…")

        def worker() -> None:
            try:
                result = self.api.call(action, token=self.token, **payload)
            except Exception as exc:
                self.results.put((None, exc, callback))
            else:
                self.results.put((result, None, callback))

        threading.Thread(target=worker, daemon=True).start()

    def drain_results(self) -> None:
        try:
            data, error, callback = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if error is not None:
                self.status.set("读取失败，可稍后重试。")
                messagebox.showerror("操作日志读取失败", str(error), parent=self.window)
            else:
                callback(data)
            self.update_buttons()
        self.timer = self.window.after(80, self.drain_results)

    def update_buttons(self) -> None:
        self.refresh_button.configure(state="disabled" if self.busy else "normal")
        self.previous_button.configure(state="normal" if self.pages and not self.busy else "disabled")
        self.next_button.configure(state="normal" if self.has_more and not self.busy else "disabled")

    def reset_page(self) -> None:
        if not self.busy:
            self.pages.clear()
            self.after_id = 0
            self.load()

    def next_page(self) -> None:
        if self.rows and self.has_more and not self.busy:
            self.pages.append(self.after_id)
            self.after_id = max(row["id"] for row in self.rows.values())
            self.load()

    def previous_page(self) -> None:
        if self.pages and not self.busy:
            self.after_id = self.pages.pop()
            self.load()

    def load(self) -> None:
        self.request("admin_list_operation_logs", self.loaded, after_id=self.after_id, search=self.search.get().strip())

    def loaded(self, data: dict) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows = {str(row["id"]): row for row in data["logs"]}
        self.has_more = bool(data["has_more"])
        for iid, row in self.rows.items():
            actor = row.get("actor_username") or (f"已删除用户 #{row['actor_id']}" if row.get("actor_id") else "未登录")
            target = row.get("target_username") or (f"已删除用户 #{row['target_user_id']}" if row.get("target_user_id") else "—")
            self.tree.insert("", "end", iid=iid, tags=("failed",) if not row["success"] else (), values=(
                row["id"], row["created_at"], actor, ACTION_NAMES.get(row["action"], row["action"]),
                "成功" if row["success"] else "失败", target, row.get("detail", ""),
            ))
        self.show_detail()
        self.status.set(f"第 {len(self.pages) + 1} 页 · {len(self.rows)} 条记录 · 不显示密码、令牌与消息正文")

    def show_detail(self) -> None:
        selection = self.tree.selection()
        row = self.rows.get(selection[0]) if selection else None
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if row:
            self.detail.insert("end", f"动作：{ACTION_NAMES.get(row['action'], row['action'])}\n")
            self.detail.insert("end", f"结果：{'成功' if row['success'] else '失败'}\n")
            self.detail.insert("end", f"操作说明：{row.get('detail', '')}\n")
            if row.get("message_id"):
                self.detail.insert("end", f"关联消息编号：{row['message_id']}\n")
        self.detail.configure(state="disabled")
        self.update_buttons()
