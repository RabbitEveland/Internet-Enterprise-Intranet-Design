"""Local, non-persistent password prompting for encrypted TLS keys."""

from __future__ import annotations

from getpass import getpass
import os


def _prompt_with_tkinter(title: str, prompt: str, confirm_prompt: str | None = None) -> str | None:
    """Return None only when a graphical prompt cannot be opened."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
    except tk.TclError:
        return None

    try:
        password = simpledialog.askstring(
            title,
            prompt,
            show="*",
            parent=root,
        )
        if password is None:
            raise ValueError("已取消输入私钥口令。")
        if confirm_prompt:
            repeated_password = simpledialog.askstring(
                f"确认{title}",
                confirm_prompt,
                show="*",
                parent=root,
            )
            if password != repeated_password:
                raise ValueError("两次输入的私钥口令不一致。")
        return password
    finally:
        root.destroy()


def get_secret(
    environment_variable: str,
    title: str,
    prompt: str,
    confirmation_prompt: str | None = None,
) -> str:
    """Use an optional environment value, otherwise prompt without saving the secret."""
    password = os.environ.get(environment_variable)
    if password:
        return password

    password = _prompt_with_tkinter(title, prompt, confirmation_prompt)
    if password is not None:
        return password

    password = getpass(f"{title}: ")
    if confirmation_prompt and password != getpass(f"确认{title}: "):
        raise ValueError("Passwords do not match.")
    if not password:
        raise ValueError("Private-key password must not be empty.")
    return password


def get_private_key_password(environment_variable: str, confirm: bool = False) -> str:
    return get_secret(
        environment_variable,
        "TLS 私钥口令",
        "请输入私钥口令（至少 12 个字符）：",
        "请再次输入同一口令：" if confirm else None,
    )


def get_database_password(environment_variable: str) -> str:
    return get_secret(environment_variable, "MySQL 数据库密码", "请输入 MySQL 账户密码：")


def get_new_account_password(title: str = "管理员账户密码") -> str:
    return get_secret("", title, "请输入至少 8 个字符的密码：", "请再次输入同一密码：")


def get_text_input(title: str, prompt: str) -> str:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        value = input(f"{prompt}: ")
        if not value:
            raise ValueError("输入不能为空。")
        return value

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = simpledialog.askstring(title, prompt, parent=root)
        if not value:
            raise ValueError("输入不能为空。")
        return value
    finally:
        root.destroy()
