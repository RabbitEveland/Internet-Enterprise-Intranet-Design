"""Administrator message review, separate from the support-reply workflow."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from client.api import MessengerApi


class ModerationWindow:
    def __init__(self, parent: tk.Tk, api: MessengerApi, token: str, user: dict | None = None) -> None:
        self.api, self.token, self.user = api, token, user
        self.rows: dict[str, dict[str, Any]] = {}
        self.after_id = 0
        self.pages: list[int] = []
        self.has_more = False
        self.busy = False
        self.results: queue.Queue = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.window.title("对话审核 · Secure Messenger")
        self.window.geometry("1060x740")
        self.window.minsize(850, 600)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        panel = ttk.Frame(self.window, style="Surface.TFrame", padding=22)
        panel.grid(sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=2)
        panel.rowconfigure(4, weight=1)
        ttk.Label(panel, text="对话内容审核", style="SurfaceTitle.TLabel").grid(row=0, column=0, sticky="w")
        toolbar = ttk.Frame(panel, style="Surface.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=12)
        self.scope = tk.BooleanVar(value=user is not None)
        if user is not None:
            ttk.Checkbutton(toolbar, text=f"仅查看与 {user['username']} 相关的消息", variable=self.scope,
                            command=self.reset_page).pack(side="left")
        else:
            ttk.Label(toolbar, text="全部用户对话（包含管理员会话）").pack(side="left")
        self.refresh_button = ttk.Button(toolbar, text="刷新 / 返回第一页", command=self.reset_page, style="Secondary.TButton")
        self.refresh_button.pack(side="right")
        table = ttk.Frame(panel)
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("id", "sender", "recipient", "time", "state", "preview"),
                                 show="headings", selectmode="browse", height=8)
        for key, title, width in (("id", "编号", 55), ("sender", "发送人", 110), ("recipient", "接收人", 110),
                                  ("time", "时间", 155), ("state", "状态", 75), ("preview", "内容摘要", 260)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=45)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("blocked", foreground="#B42342")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_detail())
        ttk.Label(panel, text="原文与审核记录（仅管理员可见）", style="SectionTitle.TLabel").grid(row=3, column=0, sticky="w", pady=(14, 6))
        self.detail = ScrolledText(panel, height=6, wrap="word", state="disabled", font=("Microsoft YaHei UI", 10))
        self.detail.grid(row=4, column=0, sticky="nsew")
        ttk.Label(panel, text="操作原因（屏蔽及解除均需填写，最多 500 字）").grid(row=5, column=0, sticky="w", pady=(12, 5))
        self.reason = ttk.Entry(panel)
        self.reason.grid(row=6, column=0, sticky="ew")
        actions = ttk.Frame(panel, style="Surface.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=12)
        self.block_button = ttk.Button(actions, text="屏蔽选中消息", style="Danger.TButton", command=lambda: self.moderate(True))
        self.block_button.pack(side="left")
        self.restore_button = ttk.Button(actions, text="解除屏蔽", style="Secondary.TButton", command=lambda: self.moderate(False))
        self.restore_button.pack(side="left", padx=8)
        self.next_button = ttk.Button(actions, text="下一页", command=self.next_page)
        self.next_button.pack(side="right")
        self.previous_button = ttk.Button(actions, text="上一页", command=self.previous_page)
        self.previous_button.pack(side="right", padx=8)
        self.status = tk.StringVar(value="每页 40 条，按消息编号排序；选中消息查看完整原文。")
        ttk.Label(panel, textvariable=self.status, style="SectionCopy.TLabel").grid(row=8, column=0, sticky="w")
        self.timer = self.window.after(80, self.drain_results)
        self.load()

    def close(self) -> None:
        self.window.after_cancel(self.timer)
        self.window.destroy()

    def request(self, action: str, callback: Callable, **payload: Any) -> None:
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        self.status.set("正在处理…")

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
                self.status.set("请求失败，可点击刷新重试。")
                messagebox.showerror("审核操作失败", str(error), parent=self.window)
            else:
                callback(data)
            self.update_buttons()
        self.timer = self.window.after(80, self.drain_results)

    def update_buttons(self) -> None:
        selected = self.selected()
        for button, enabled in (
            (self.refresh_button, True), (self.previous_button, bool(self.pages)),
            (self.next_button, self.has_more),
            (self.block_button, selected is not None and not selected.get("is_blocked")),
            (self.restore_button, selected is not None and bool(selected.get("is_blocked"))),
        ):
            button.configure(state="normal" if enabled and not self.busy else "disabled")

    def selected(self) -> dict | None:
        selection = self.tree.selection()
        return self.rows.get(selection[0]) if selection else None

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
        payload = {"after_id": self.after_id}
        if self.user and self.scope.get():
            payload["user_id"] = self.user["id"]
        self.request("admin_review_messages", self.loaded, **payload)

    def loaded(self, data: dict) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.rows = {str(row["id"]): row for row in data["messages"]}
        self.has_more = data["has_more"]
        for iid, row in self.rows.items():
            blocked = bool(row.get("is_blocked"))
            self.tree.insert("", "end", iid=iid, tags=("blocked",) if blocked else (), values=(
                row["id"], row["sender_username"], row.get("recipient_username") or "管理员收件箱",
                row["created_at"], "已屏蔽" if blocked else "正常", row["body"].replace("\n", " ")[:80]))
        if selected and selected[0] in self.rows:
            self.tree.selection_set(selected[0])
        self.show_detail()
        self.status.set(f"第 {len(self.pages) + 1} 页 · {len(self.rows)} 条消息 · 屏蔽后双方在刷新对话时看到系统提示")

    def show_detail(self) -> None:
        row = self.selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if row:
            self.detail.insert("end", row["body"])
            if row.get("moderated_at"):
                self.detail.insert("end", f"\n\n最近审核：{row.get('moderator_username') or '已删除管理员'} · {row['moderated_at']}"
                                   f"\n状态：{'已屏蔽' if row.get('is_blocked') else '已解除屏蔽'}\n原因：{row.get('reason', '')}")
        self.detail.configure(state="disabled")
        self.update_buttons()

    def moderate(self, blocked: bool) -> None:
        row = self.selected()
        if row is None or self.busy:
            return
        reason = self.reason.get().strip()
        if not reason or len(reason) > 500:
            messagebox.showwarning("请填写原因", "请输入 1–500 字的操作原因。", parent=self.window)
            return
        label = "屏蔽" if blocked else "解除屏蔽"
        if not messagebox.askyesno("确认审核操作", f"确定{label}第 {row['id']} 条消息？", parent=self.window):
            return
        self.request("admin_moderate_message", self.moderated, message_id=row["id"], is_blocked=blocked, reason=reason)

    def moderated(self, _data: dict) -> None:
        self.reason.delete(0, "end")
        self.load()
