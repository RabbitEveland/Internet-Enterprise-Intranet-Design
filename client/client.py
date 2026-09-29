"""Complete Tkinter UI for user registration, messaging, and administration."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

# PyCharm's configuration executes this file directly. Put the project root
# first so ``client.api`` resolves to the package instead of this entrypoint.
if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root in sys.path:
        sys.path.remove(project_root)
    sys.path.insert(0, project_root)

from client.api import ApiError, MessengerApi
from client.moderation import ModerationWindow
from client.operation_logs import OperationLogWindow
from client.profile import ProfileWindow
from client.profile_view import PublicProfileWindow
from common.config import Settings, load_settings


class MessengerWindow:
    COLORS = {
        "ink": "#152033",
        "muted": "#64748B",
        "canvas": "#EEF2F8",
        "surface": "#FFFFFF",
        "surface_soft": "#F7F9FC",
        "line": "#D9E2EE",
        "navy": "#102A43",
        "navy_soft": "#1B3B5A",
        "blue": "#2563EB",
        "blue_hover": "#1D4ED8",
        "cyan": "#22C1C3",
        "danger": "#DC4C64",
        "danger_hover": "#C73951",
        "success": "#16835D",
    }
    FONT = "Microsoft YaHei UI"

    def __init__(self, root: tk.Tk, settings: Settings) -> None:
        self.root = root
        self.api = MessengerApi(settings)
        self.token = ""
        self.current_user: dict[str, Any] | None = None
        self.selected_user: dict[str, Any] | None = None
        self.user_rows: dict[str, dict[str, Any]] = {}
        self.selected_contact: dict[str, Any] | None = None
        self.contact_rows: dict[str, dict[str, Any]] = {}
        self._configure_theme()
        self.show_login()

    def _configure_theme(self) -> None:
        self.root.title("Secure Messenger · 安全消息中心")
        self.root.geometry("1240x800")
        self.root.minsize(1000, 680)
        self.root.configure(bg=self.COLORS["canvas"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.COLORS["canvas"])
        style.configure("Topbar.TFrame", background=self.COLORS["navy"])
        style.configure("Hero.TFrame", background=self.COLORS["navy"])
        style.configure("Surface.TFrame", background=self.COLORS["surface"])
        style.configure("Sidebar.TFrame", background="#E6EDF7")
        style.configure("Card.TFrame", background=self.COLORS["surface"])
        style.configure("TLabel", background=self.COLORS["surface"], foreground=self.COLORS["ink"], font=(self.FONT, 10))
        style.configure("PageTitle.TLabel", background=self.COLORS["navy"], foreground="#FFFFFF", font=(self.FONT, 18, "bold"))
        style.configure("PageSubtitle.TLabel", background=self.COLORS["navy"], foreground="#B8C7D9", font=(self.FONT, 9))
        style.configure("BrandMark.TLabel", background=self.COLORS["cyan"], foreground=self.COLORS["navy"], font=(self.FONT, 12, "bold"), anchor="center")
        style.configure("HeroEyebrow.TLabel", background=self.COLORS["navy"], foreground=self.COLORS["cyan"], font=(self.FONT, 9, "bold"))
        style.configure("HeroTitle.TLabel", background=self.COLORS["navy"], foreground="#FFFFFF", font=(self.FONT, 27, "bold"))
        style.configure("HeroCopy.TLabel", background=self.COLORS["navy"], foreground="#C5D2E1", font=(self.FONT, 10), wraplength=390, justify="left")
        style.configure("SurfaceTitle.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["ink"], font=(self.FONT, 18, "bold"))
        style.configure("SectionTitle.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["ink"], font=(self.FONT, 12, "bold"))
        style.configure("SectionCopy.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["muted"], font=(self.FONT, 9))
        style.configure("SidebarTitle.TLabel", background="#E6EDF7", foreground=self.COLORS["ink"], font=(self.FONT, 13, "bold"))
        style.configure("SidebarCopy.TLabel", background="#E6EDF7", foreground=self.COLORS["muted"], font=(self.FONT, 9))
        style.configure("Status.TLabel", background="#E8EFF8", foreground="#39516C", font=(self.FONT, 9), padding=(22, 8))
        style.configure("Online.TLabel", background=self.COLORS["navy"], foreground="#A7F3D0", font=(self.FONT, 9, "bold"))
        style.configure("TEntry", fieldbackground="#FFFFFF", foreground=self.COLORS["ink"], padding=(11, 8), bordercolor=self.COLORS["line"], lightcolor=self.COLORS["line"], darkcolor=self.COLORS["line"])
        style.map("TEntry", bordercolor=[("focus", self.COLORS["blue"])], lightcolor=[("focus", self.COLORS["blue"])], darkcolor=[("focus", self.COLORS["blue"])])
        style.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF", foreground=self.COLORS["ink"], padding=(9, 7))
        style.configure("Primary.TButton", background=self.COLORS["blue"], foreground="#FFFFFF", padding=(16, 10), font=(self.FONT, 10, "bold"), borderwidth=0)
        style.map("Primary.TButton", background=[("active", self.COLORS["blue_hover"]), ("disabled", "#A9BCEB")])
        style.configure("Secondary.TButton", background="#E7EEF9", foreground="#21466E", padding=(12, 8), font=(self.FONT, 9, "bold"), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#D5E2F5")])
        style.configure("Ghost.TButton", background=self.COLORS["navy"], foreground="#DCE9F7", padding=(11, 7), font=(self.FONT, 9, "bold"), borderwidth=0)
        style.map("Ghost.TButton", background=[("active", self.COLORS["navy_soft"])], foreground=[("active", "#FFFFFF")])
        style.configure("Danger.TButton", background="#FCE8EC", foreground=self.COLORS["danger"], padding=(10, 7), font=(self.FONT, 9, "bold"), borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#F8D5DD")], foreground=[("active", self.COLORS["danger_hover"])])
        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground=self.COLORS["ink"], rowheight=36, font=(self.FONT, 9), borderwidth=0)
        style.map("Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", "#163F78")])
        style.configure("Treeview.Heading", background="#EAF0F7", foreground="#36506D", font=(self.FONT, 9, "bold"), relief="flat", padding=(8, 9))
        style.map("Treeview.Heading", background=[("active", "#DCE7F3")])

    def _clear(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def _run_async(self, task: Callable[[], Any], success: Callable[[Any], None], busy_text: str = "正在处理…") -> None:
        self.status_var.set(busy_text)

        def worker() -> None:
            try:
                result = task()
            except Exception as exc:
                self.root.after(0, lambda error=exc: self._show_error(error))
            else:
                self.root.after(0, lambda: success(result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, exc: Exception) -> None:
        self.status_var.set("操作失败")
        messagebox.showerror("操作失败", str(exc))

    def _make_header(self, title: str, subtitle: str, allow_logout: bool = False) -> ttk.Frame:
        header = ttk.Frame(self.root, style="Topbar.TFrame", padding=(28, 15))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="SM", style="BrandMark.TLabel", width=4).grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 13))
        ttk.Label(header, text=title, style="PageTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text=subtitle, style="PageSubtitle.TLabel").grid(row=1, column=1, sticky="w", pady=(2, 0))
        if allow_logout:
            ttk.Label(header, text="● 安全连接", style="Online.TLabel").grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 10))
            ttk.Button(header, text="个人中心", style="Ghost.TButton", command=self.open_profile).grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, 8))
            ttk.Button(header, text="退出登录", style="Ghost.TButton", command=self.logout).grid(row=0, column=4, rowspan=2, sticky="e")
        return header

    def _make_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w").grid(row=2, column=0, sticky="ew")

    def show_login(self) -> None:
        self._clear()
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self._make_header("Secure Messenger", "加密通信 · 用户消息 · 管理控制")
        page = ttk.Frame(self.root, style="App.TFrame", padding=(48, 42))
        page.grid(row=1, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)
        page.rowconfigure(0, weight=1)
        hero = ttk.Frame(page, style="Hero.TFrame", padding=(46, 44))
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        ttk.Label(hero, text="SECURE MESSENGER", style="HeroEyebrow.TLabel").pack(anchor="w")
        ttk.Label(hero, text="消息，不必\n暴露在风险里。", style="HeroTitle.TLabel", justify="left").pack(anchor="w", pady=(16, 18))
        ttk.Label(hero, text="面向用户与管理员的一体化消息中心。使用 TLS 加密传输，统一处理账户、会话与客服消息。", style="HeroCopy.TLabel").pack(anchor="w")
        ttk.Separator(hero, orient="horizontal").pack(fill="x", pady=28)
        for text in ("TLS 连接验证", "会话自动失效", "账户与消息集中管理"):
            ttk.Label(hero, text=f"✓  {text}", style="HeroCopy.TLabel").pack(anchor="w", pady=5)

        card = ttk.Frame(page, style="Surface.TFrame", padding=(42, 38))
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="欢迎回来", style="SurfaceTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text="登录后继续你的安全会话", style="SectionCopy.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 26))
        ttk.Label(card, text="用户名", style="SectionTitle.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.login_username = ttk.Entry(card, width=34)
        self.login_username.grid(row=3, column=0, sticky="ew")
        ttk.Label(card, text="密码", style="SectionTitle.TLabel").grid(row=4, column=0, sticky="w", pady=(18, 6))
        self.login_password = ttk.Entry(card, width=34, show="●")
        self.login_password.grid(row=5, column=0, sticky="ew")
        self.login_password.bind("<Return>", lambda _event: self.login())
        ttk.Button(card, text="登录并继续", style="Primary.TButton", command=self.login).grid(row=6, column=0, sticky="ew", pady=(26, 10))
        ttk.Button(card, text="创建新用户", style="Secondary.TButton", command=self.open_registration).grid(row=7, column=0, sticky="ew")
        ttk.Label(card, text="管理员账号由服务端首次启动时创建。", style="SectionCopy.TLabel").grid(row=8, column=0, sticky="w", pady=(22, 0))
        self._make_status_bar()
        self.login_username.focus_set()

    def login(self) -> None:
        username = self.login_username.get().strip()
        password = self.login_password.get()
        self._run_async(
            lambda: self.api.call("login", username=username, password=password),
            self._complete_login,
            "正在验证账户…",
        )

    def _complete_login(self, data: dict[str, Any]) -> None:
        self.token = str(data["token"])
        self.current_user = dict(data["user"])
        self.selected_user = None
        self.selected_contact = None
        self.show_dashboard()

    def open_registration(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("创建账户 · Secure Messenger")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=self.COLORS["canvas"])
        frame = ttk.Frame(dialog, style="Surface.TFrame", padding=(30, 28))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="创建新账户", style="SurfaceTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="创建后会自动登录，并可立即联系管理员。", style="SectionCopy.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 22))
        ttk.Label(frame, text="用户名（3–32 位字母、数字、下划线）", style="SectionTitle.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))
        username = ttk.Entry(frame, width=34)
        username.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(frame, text="密码（8–128 个字符）", style="SectionTitle.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(16, 6))
        password = ttk.Entry(frame, width=34, show="●")
        password.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Label(frame, text="确认密码", style="SectionTitle.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(16, 6))
        confirm = ttk.Entry(frame, width=34, show="●")
        confirm.grid(row=7, column=0, columnspan=2, sticky="ew")

        def submit() -> None:
            if password.get() != confirm.get():
                messagebox.showwarning("密码不一致", "两次输入的密码不一致。", parent=dialog)
                return
            self._run_async(
                lambda: self.api.call("register", username=username.get().strip(), password=password.get()),
                lambda data: self._registered(dialog, data),
                "正在创建账户…",
            )

        ttk.Button(frame, text="取消", style="Secondary.TButton", command=dialog.destroy).grid(row=8, column=0, sticky="ew", pady=(26, 0), padx=(0, 7))
        ttk.Button(frame, text="创建并登录", style="Primary.TButton", command=submit).grid(row=8, column=1, sticky="ew", pady=(26, 0))
        username.focus_set()

    def _registered(self, dialog: tk.Toplevel, data: dict[str, Any]) -> None:
        dialog.destroy()
        self._complete_login(data)

    def show_dashboard(self) -> None:
        if self.current_user is None:
            self.show_login()
            return
        self._clear()
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        role_title = "管理员控制台" if self.current_user["role"] == "admin" else "用户消息中心"
        self._make_header(role_title, f"当前登录：{self.current_user['username']} · 角色：{self.current_user['role']}", allow_logout=True)
        if self.current_user["role"] == "admin":
            self._build_admin_dashboard()
        else:
            self._build_user_dashboard()
        self._make_status_bar()
        if self.current_user["role"] == "admin":
            self.refresh_users()
        else:
            self.refresh_contacts()

    def _build_user_dashboard(self) -> None:
        page = ttk.Frame(self.root, style="App.TFrame", padding=(28, 24))
        page.grid(row=1, column=0, sticky="nsew")
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, minsize=310)
        page.grid_columnconfigure(1, weight=1)
        contacts_frame = ttk.Frame(page, style="Sidebar.TFrame", padding=(18, 18))
        contacts_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        contacts_frame.columnconfigure(0, weight=1)
        contacts_frame.grid_rowconfigure(4, weight=1)
        ttk.Label(contacts_frame, text="联系人", style="SidebarTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(contacts_frame, text="用户与管理员均按职位分组显示", style="SidebarCopy.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 14))
        ttk.Label(contacts_frame, text="全部联系人", style="SidebarTitle.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 7))
        self.contact_search_var = tk.StringVar()
        search = ttk.Entry(contacts_frame, textvariable=self.contact_search_var)
        search.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        search.bind("<Return>", lambda _event: self.refresh_contacts())
        self.contact_tree = ttk.Treeview(contacts_frame, columns=("role",), show="tree headings", selectmode="browse", height=16)
        self.contact_tree.heading("#0", text="联系人 / 职位分组")
        self.contact_tree.column("#0", anchor="w", width=210)
        self.contact_tree.heading("role", text="角色")
        self.contact_tree.column("role", anchor="center", width=70)
        self.contact_tree.grid(row=4, column=0, sticky="nsew")
        self.contact_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_contact())
        ttk.Button(contacts_frame, text="刷新联系人", style="Secondary.TButton", command=self.refresh_contacts).grid(row=5, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(contacts_frame, text="查看选中联系人资料", style="Secondary.TButton", command=self.open_contact_profile).grid(row=6, column=0, sticky="ew", pady=(7, 0))

        panel = ttk.Frame(page, style="Surface.TFrame", padding=(22, 20))
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        toolbar = ttk.Frame(panel, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.conversation_title = tk.StringVar(value="选择一个联系人开始对话")
        self.conversation_copy = tk.StringVar(value="用户和管理员都在左侧联系人列表中")
        ttk.Label(toolbar, textvariable=self.conversation_title, style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(toolbar, textvariable=self.conversation_copy, style="SectionCopy.TLabel").pack(side="left", padx=(12, 0))
        ttk.Button(toolbar, text="刷新", style="Secondary.TButton", command=self.refresh_conversation).pack(side="right")
        self.transcript = self._make_transcript(panel)
        self.transcript.grid(row=1, column=0, sticky="nsew")
        self._build_composer(panel, row=2)

    def _build_admin_dashboard(self) -> None:
        page = ttk.Frame(self.root, style="App.TFrame", padding=(28, 24))
        page.grid(row=1, column=0, sticky="nsew")
        page.grid_columnconfigure(0, minsize=330)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)
        users_frame = ttk.Frame(page, style="Sidebar.TFrame", padding=(18, 18))
        users_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        chat_frame = ttk.Frame(page, style="Surface.TFrame", padding=(22, 20))
        chat_frame.grid(row=0, column=1, sticky="nsew")

        ttk.Label(users_frame, text="用户目录", style="SidebarTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(users_frame, text="选择普通用户后查看并回复消息", style="SidebarCopy.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 13))
        self.search_var = tk.StringVar()
        search = ttk.Entry(users_frame, textvariable=self.search_var)
        search.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        search.bind("<Return>", lambda _event: self.refresh_users())
        ttk.Button(users_frame, text="搜索", style="Secondary.TButton", command=self.refresh_users).grid(row=2, column=1, padx=(7, 0), pady=(0, 10))
        users_frame.columnconfigure(0, weight=1)
        self.user_tree = ttk.Treeview(users_frame, columns=("username", "role", "active"), show="headings", selectmode="browse", height=18)
        for column, title, width in (("username", "用户名", 130), ("role", "角色", 65), ("active", "状态", 65)):
            self.user_tree.heading(column, text=title)
            self.user_tree.column(column, width=width, anchor="center")
        self.user_tree.grid(row=3, column=0, columnspan=2, sticky="nsew")
        users_frame.grid_rowconfigure(3, weight=1)
        self.user_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_user())
        actions = ttk.Frame(users_frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        for index, (text, command) in enumerate((("新建", self.open_create_user), ("编辑", self.open_edit_user), ("重置密码", self.reset_password), ("删除", self.delete_user))):
            style = "Danger.TButton" if text == "删除" else "Secondary.TButton"
            ttk.Button(actions, text=text, command=command, style=style).grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
            actions.columnconfigure(index % 2, weight=1)
        ttk.Button(actions, text="对话审核 / 违规屏蔽", style="Primary.TButton",
                   command=self.open_moderation).grid(row=2, column=0, columnspan=2, sticky="ew", padx=3, pady=(12, 3))
        ttk.Button(actions, text="查看系统操作日志", style="Secondary.TButton",
                   command=self.open_operation_logs).grid(row=3, column=0, columnspan=2, sticky="ew", padx=3, pady=3)
        ttk.Button(actions, text="查看选中用户资料", style="Secondary.TButton",
                   command=self.open_selected_profile).grid(row=4, column=0, columnspan=2, sticky="ew", padx=3, pady=3)

        chat_frame.grid_columnconfigure(0, weight=1)
        chat_frame.grid_rowconfigure(1, weight=1)
        toolbar = ttk.Frame(chat_frame, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.conversation_title = tk.StringVar(value="选择一个普通用户以查看消息")
        ttk.Label(toolbar, textvariable=self.conversation_title, style="SectionTitle.TLabel").pack(side="left")
        ttk.Button(toolbar, text="刷新", style="Secondary.TButton", command=self.refresh_conversation).pack(side="right")
        self.transcript = self._make_transcript(chat_frame)
        self.transcript.grid(row=1, column=0, sticky="nsew")
        self._build_composer(chat_frame, row=2)

    def _make_transcript(self, parent: ttk.Frame) -> ScrolledText:
        transcript = ScrolledText(
            parent,
            wrap="word",
            font=(self.FONT, 10),
            state="disabled",
            padx=18,
            pady=16,
            relief="flat",
            borderwidth=0,
            background=self.COLORS["surface_soft"],
            foreground=self.COLORS["ink"],
            insertbackground=self.COLORS["ink"],
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            highlightcolor=self.COLORS["blue"],
        )
        transcript.tag_configure("meta", foreground=self.COLORS["muted"], font=(self.FONT, 8))
        transcript.tag_configure("mine", foreground=self.COLORS["blue"], font=(self.FONT, 9, "bold"), spacing1=12)
        transcript.tag_configure("theirs", foreground=self.COLORS["success"], font=(self.FONT, 9, "bold"), spacing1=12)
        transcript.tag_configure("body", foreground=self.COLORS["ink"], font=(self.FONT, 10), spacing3=8)
        return transcript

    def _build_composer(self, parent: ttk.Frame, row: int) -> None:
        composer = ttk.Frame(parent, style="Surface.TFrame")
        composer.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        composer.columnconfigure(0, weight=1)
        self.composer = tk.Text(
            composer,
            height=4,
            wrap="word",
            font=(self.FONT, 10),
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=12,
            background="#FFFFFF",
            foreground=self.COLORS["ink"],
            insertbackground=self.COLORS["ink"],
            highlightthickness=1,
            highlightbackground=self.COLORS["line"],
            highlightcolor=self.COLORS["blue"],
        )
        self.composer.grid(row=0, column=0, sticky="ew")
        ttk.Button(composer, text="发送\n消息", style="Primary.TButton", command=self.send_message).grid(row=0, column=1, sticky="ns", padx=(12, 0))

    def refresh_contacts(self) -> None:
        if self.current_user is None or self.current_user["role"] != "user":
            return
        self._run_async(
            lambda: self.api.call("user_list_contacts", token=self.token, search=self.contact_search_var.get().strip()),
            self._show_contacts,
            "正在发现其他用户…",
        )

    def _show_contacts(self, data: dict[str, Any]) -> None:
        selected_id = self.selected_contact.get("id") if self.selected_contact is not None else None
        for item in self.contact_tree.get_children():
            self.contact_tree.delete(item)
        self.contact_rows.clear()
        groups: dict[str, list[dict[str, Any]]] = {}
        for user in data["users"]:
            job_title = str(user.get("job_title") or "").strip()
            groups.setdefault(job_title or "未填写职位", []).append(user)
        for job_title in sorted(groups, key=lambda value: (value == "未填写职位", value.casefold())):
            group = self.contact_tree.insert("", "end", text=f"职位 · {job_title}", open=True, values=("",))
            for user in groups[job_title]:
                role = "管理员" if user["role"] == "admin" else "用户"
                item = self.contact_tree.insert(group, "end", text=user["username"], values=(role,))
                self.contact_rows[item] = user
                if selected_id == user["id"]:
                    self.contact_tree.selection_set(item)
        self.status_var.set(f"已发现 {len(data['users'])} 位联系人，按职位分组显示")

    def select_contact(self) -> None:
        selection = self.contact_tree.selection()
        if not selection or selection[0] not in self.contact_rows:
            return
        self.selected_contact = self.contact_rows[selection[0]]
        role = "管理员" if self.selected_contact["role"] == "admin" else "用户"
        self.conversation_title.set(f"与 {self.selected_contact['username']} 的对话")
        self.conversation_copy.set(f"{role}联系人 · 管理员可进行内容审核")
        self.refresh_conversation()

    def open_contact_profile(self) -> None:
        if self.selected_contact is None:
            messagebox.showwarning("未选择联系人", "请先在联系人列表中选择一位用户或管理员。")
            return
        PublicProfileWindow(self.root, self.api, self.token, int(self.selected_contact["id"]))

    def refresh_users(self) -> None:
        if self.current_user is None:
            return
        self._run_async(
            lambda: self.api.call("admin_list_users", token=self.token, search=self.search_var.get().strip()),
            self._show_users,
            "正在加载用户列表…",
        )

    def _show_users(self, data: dict[str, Any]) -> None:
        for item in self.user_tree.get_children():
            self.user_tree.delete(item)
        self.user_rows.clear()
        for user in data["users"]:
            item = self.user_tree.insert("", "end", values=(user["username"], user["role"], "启用" if user["is_active"] else "停用"))
            self.user_rows[item] = user
        self.status_var.set(f"已加载 {len(data['users'])} 个账户")

    def select_user(self) -> None:
        selection = self.user_tree.selection()
        if not selection:
            return
        self.selected_user = self.user_rows[selection[0]]
        if self.selected_user["role"] == "user":
            self.conversation_title.set(f"与 {self.selected_user['username']} 的对话")
            self.refresh_conversation()
        else:
            self.conversation_title.set("管理员账户不可作为消息接收方")
            self._set_transcript([])

    def refresh_conversation(self) -> None:
        if self.current_user is None:
            return
        payload: dict[str, Any] = {"token": self.token}
        if self.current_user["role"] == "admin":
            if self.selected_user is None or self.selected_user["role"] != "user":
                self.status_var.set("请先选择一个普通用户")
                return
            payload["user_id"] = self.selected_user["id"]
        elif self.selected_contact is not None:
            payload["user_id"] = self.selected_contact["id"]
        else:
            self.status_var.set("请先在左侧选择一位联系人")
            return
        self._run_async(lambda: self.api.call("conversation", **payload), self._show_conversation, "正在加载消息…")

    def _show_conversation(self, data: dict[str, Any]) -> None:
        self._set_transcript(data["messages"])
        self.status_var.set(f"已加载 {len(data['messages'])} 条消息")

    def _set_transcript(self, messages: list[dict[str, Any]]) -> None:
        self.transcript.config(state="normal")
        self.transcript.delete("1.0", "end")
        if not messages:
            self.transcript.insert("end", "还没有消息\n", "meta")
            self.transcript.insert("end", "发送第一条消息，开启这段会话。", "body")
        for message in messages:
            timestamp = str(message.get("created_at", ""))
            sender = message.get("sender_username", "未知用户")
            role = "管理员" if message.get("sender_role") == "admin" else "用户"
            is_self = self.current_user is not None and sender == self.current_user.get("username")
            sender_tag = "mine" if is_self else "theirs"
            self.transcript.insert("end", f"{role} · {sender}\n", sender_tag)
            self.transcript.insert("end", f"{timestamp}\n", "meta")
            self.transcript.insert("end", f"{message.get('body', '')}\n", "body")
        self.transcript.config(state="disabled")
        self.transcript.see("end")

    def send_message(self) -> None:
        if self.current_user is None:
            return
        body = self.composer.get("1.0", "end-1c").strip()
        if not body:
            messagebox.showwarning("消息为空", "请输入要发送的消息。")
            return
        payload: dict[str, Any] = {"token": self.token, "body": body}
        if self.current_user["role"] == "admin":
            if self.selected_user is None or self.selected_user["role"] != "user":
                messagebox.showwarning("未选择用户", "请先在左侧选择一个普通用户。")
                return
            payload["user_id"] = self.selected_user["id"]
        elif self.selected_contact is not None:
            payload["user_id"] = self.selected_contact["id"]
        self._run_async(lambda: self.api.call("send_message", **payload), self._message_sent, "正在发送消息…")

    def _message_sent(self, _data: dict[str, Any]) -> None:
        self.composer.delete("1.0", "end")
        self.refresh_conversation()

    def _selected_account(self) -> dict[str, Any] | None:
        if self.selected_user is None:
            messagebox.showwarning("未选择账户", "请先在左侧选择一个账户。")
            return None
        return self.selected_user

    def open_moderation(self) -> None:
        if self.current_user is not None and self.current_user["role"] == "admin":
            ModerationWindow(self.root, self.api, self.token, self.selected_user)

    def open_operation_logs(self) -> None:
        if self.current_user is not None and self.current_user["role"] == "admin":
            OperationLogWindow(self.root, self.api, self.token)

    def open_selected_profile(self) -> None:
        user = self._selected_account()
        if user is not None:
            PublicProfileWindow(self.root, self.api, self.token, int(user["id"]))

    def open_profile(self) -> None:
        if self.current_user is not None:
            ProfileWindow(self.root, self.api, self.token, self._profile_saved)

    def _profile_saved(self, user: dict[str, Any]) -> None:
        self.current_user = dict(user)
        self.status_var.set("个人资料已更新。")

    def open_create_user(self) -> None:
        self.open_user_editor(None)

    def open_edit_user(self) -> None:
        user = self._selected_account()
        if user is not None:
            self.open_user_editor(user)

    def open_user_editor(self, user: dict[str, Any] | None) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("新建账户" if user is None else f"编辑账户 · {user['username']}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=self.COLORS["canvas"])
        frame = ttk.Frame(dialog, style="Surface.TFrame", padding=(30, 28))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        title = "创建账户" if user is None else "编辑账户资料"
        copy = "为用户分配角色与初始凭据。" if user is None else "更新角色、名称或启用状态。"
        ttk.Label(frame, text=title, style="SurfaceTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text=copy, style="SectionCopy.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 22))
        ttk.Label(frame, text="用户名", style="SectionTitle.TLabel").grid(row=2, column=0, sticky="w")
        username = ttk.Entry(frame, width=34)
        username.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 16))
        username.insert(0, "" if user is None else user["username"])
        password: ttk.Entry | None = None
        if user is None:
            ttk.Label(frame, text="初始密码", style="SectionTitle.TLabel").grid(row=4, column=0, sticky="w")
            password = ttk.Entry(frame, width=34, show="●")
            password.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 16))
        ttk.Label(frame, text="角色", style="SectionTitle.TLabel").grid(row=6, column=0, sticky="w")
        role = ttk.Combobox(frame, values=("user", "admin"), state="readonly", width=31)
        role.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 16))
        role.set("user" if user is None else user["role"])
        active = tk.BooleanVar(value=True if user is None else bool(user["is_active"]))
        ttk.Checkbutton(frame, text="账户启用", variable=active).grid(row=8, column=0, columnspan=2, sticky="w")

        def save() -> None:
            if user is None:
                self._run_async(
                    lambda: self.api.call("admin_create_user", token=self.token, username=username.get().strip(), password=password.get() if password else "", role=role.get()),
                    lambda _data: self._editor_saved(dialog),
                    "正在创建账户…",
                )
            else:
                self._run_async(
                    lambda: self.api.call("admin_update_user", token=self.token, user_id=user["id"], username=username.get().strip(), role=role.get(), is_active=active.get()),
                    lambda _data: self._editor_saved(dialog),
                    "正在更新账户…",
                )

        ttk.Button(frame, text="取消", style="Secondary.TButton", command=dialog.destroy).grid(row=9, column=0, sticky="ew", padx=(0, 7), pady=(26, 0))
        ttk.Button(frame, text="保存更改", style="Primary.TButton", command=save).grid(row=9, column=1, sticky="ew", pady=(26, 0))
        username.focus_set()

    def _editor_saved(self, dialog: tk.Toplevel) -> None:
        dialog.destroy()
        self.selected_user = None
        self.refresh_users()

    def reset_password(self) -> None:
        user = self._selected_account()
        if user is None:
            return
        password = simpledialog.askstring("重置密码", f"为 {user['username']} 设置新密码：", show="●", parent=self.root)
        if password is None:
            return
        confirmation = simpledialog.askstring("确认新密码", "请再次输入新密码：", show="●", parent=self.root)
        if password != confirmation:
            messagebox.showwarning("密码不一致", "两次输入的密码不一致。")
            return
        self._run_async(
            lambda: self.api.call("admin_reset_password", token=self.token, user_id=user["id"], password=password),
            lambda _data: self._password_reset(user["username"]),
            "正在重置密码…",
        )

    def _password_reset(self, username: str) -> None:
        self.status_var.set(f"已重置 {username} 的密码；该账户已被强制退出。")
        messagebox.showinfo("密码已重置", f"{username} 的密码已重置，旧登录会话已失效。")

    def delete_user(self) -> None:
        user = self._selected_account()
        if user is None or not messagebox.askyesno("确认删除", f"确定删除账户“{user['username']}”及其消息吗？此操作不可撤销。"):
            return
        self._run_async(
            lambda: self.api.call("admin_delete_user", token=self.token, user_id=user["id"]),
            lambda _data: self._user_deleted(user["username"]),
            "正在删除账户…",
        )

    def _user_deleted(self, username: str) -> None:
        self.selected_user = None
        self._set_transcript([])
        self.status_var.set(f"已删除账户 {username}")
        self.refresh_users()

    def logout(self) -> None:
        token = self.token

        def done(_data: dict[str, Any]) -> None:
            self.token = ""
            self.current_user = None
            self.selected_user = None
            self.selected_contact = None
            self.contact_rows.clear()
            self.show_login()

        self._run_async(lambda: self.api.call("logout", token=token), done, "正在退出登录…")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Secure Messenger GUI client.")
    parser.add_argument("--config", help="Path to the canonical config.ini file.")
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
    except ValueError as exc:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("配置错误", str(exc), parent=error_root)
        error_root.destroy()
        return 1

    root = tk.Tk()
    MessengerWindow(root, settings)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
