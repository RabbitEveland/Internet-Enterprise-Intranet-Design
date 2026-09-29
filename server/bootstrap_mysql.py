"""One-time local setup for the repository's MySQL instance.

The script initializes an empty local data directory, asks for two new
passwords in Tkinter dialogs, and provisions only the application's database
privileges. It never saves either password in the project.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import mysql.connector

from common.secrets import get_new_account_password


MYSQL_HOME = Path(r"D:\mysql-runtime")
MYSQLD = MYSQL_HOME / "mysql-9.7.2-winx64" / "bin" / "mysqld.exe"
MYSQL_INI = MYSQL_HOME / "my.ini"
MYSQL_DATA = MYSQL_HOME / "data"
MYSQL_ERROR_LOG = MYSQL_HOME / "mysql-error.log"
MYSQL_PID_FILE = MYSQL_HOME / "mysql.pid"
BOOTSTRAP_MARKER = MYSQL_HOME / ".secure-messenger-bootstrap-complete"
APPLICATION_DATABASE = "secure_messenger"
APPLICATION_USER = "secure_messenger_app"
APPLICATION_HOST = "127.0.0.1"
ROOT_HOST = "localhost"


def _is_running() -> bool:
    try:
        with socket.create_connection((APPLICATION_HOST, 3306), timeout=0.5):
            return True
    except OSError:
        return False


def _start_server() -> None:
    if _is_running():
        return
    if not MYSQLD.is_file() or not MYSQL_INI.is_file():
        raise RuntimeError("找不到 D:\\mysql-runtime 中的 MySQL 运行时或配置文件。")
    subprocess.Popen(
        [str(MYSQLD), f"--defaults-file={MYSQL_INI}"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _is_running():
            return
        time.sleep(0.25)
    raise RuntimeError("MySQL 未能在 15 秒内启动，请检查 D:\\mysql-runtime\\mysql-error.log。")


def _wait_until_stopped() -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not _is_running():
            return
        time.sleep(0.25)
    raise RuntimeError("MySQL 未能在 15 秒内停止。")


def _stop_server_from_pid_file() -> None:
    """Stop only this local instance, identified by its own configured PID file."""
    if not MYSQL_PID_FILE.is_file():
        return
    try:
        process_id = int(MYSQL_PID_FILE.read_text(encoding="ascii").strip())
        if process_id > 0:
            os.kill(process_id, 15)
    except (OSError, ValueError):
        pass
    _wait_until_stopped()


def _initialize_empty_instance() -> None:
    """Reset only the unconfigured runtime created for this project."""
    if BOOTSTRAP_MARKER.exists():
        raise RuntimeError("MySQL 已完成首次设置；请不要再次运行 setup_mysql。")
    if _is_running():
        _stop_server_from_pid_file()
    if _is_running():
        raise RuntimeError("无法停止未配置的 MySQL 实例。")
    if MYSQL_DATA.exists():
        shutil.rmtree(MYSQL_DATA)
    MYSQL_ERROR_LOG.unlink(missing_ok=True)
    subprocess.run(
        [str(MYSQLD), f"--defaults-file={MYSQL_INI}", "--initialize-insecure", "--console"],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _require_strong_password(title: str) -> str:
    password = get_new_account_password(title)
    if len(password) < 12:
        raise ValueError(f"{title}至少需要 12 个字符。")
    return password


def main() -> None:
    _initialize_empty_instance()
    _start_server()
    root_password = _require_strong_password("MySQL 管理员 root 密码")
    application_password = _require_strong_password("项目 MySQL 账户密码")

    connection = mysql.connector.connect(
        host=ROOT_HOST,
        port=3306,
        user="root",
        password="",
        connection_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{APPLICATION_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(
                f"CREATE USER IF NOT EXISTS '{APPLICATION_USER}'@'{APPLICATION_HOST}' IDENTIFIED BY %s",
                (application_password,),
            )
            cursor.execute(
                f"ALTER USER '{APPLICATION_USER}'@'{APPLICATION_HOST}' IDENTIFIED BY %s",
                (application_password,),
            )
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES "
                f"ON `{APPLICATION_DATABASE}`.* TO '{APPLICATION_USER}'@'{APPLICATION_HOST}'"
            )
            cursor.execute("FLUSH PRIVILEGES")
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("SHUTDOWN")
    finally:
        connection.close()

    _wait_until_stopped()
    _start_server()
    BOOTSTRAP_MARKER.write_text("configured\n", encoding="ascii")
    print("MySQL 本地账号和项目数据库已创建，服务正在 127.0.0.1:3306 运行。")


if __name__ == "__main__":
    main()
