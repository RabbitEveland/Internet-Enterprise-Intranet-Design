import ssl
import logging
import socket
import tkinter as tk
from tkinter import messagebox

# 设置日志
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('client_log')

# 服务器信息
SERVER_HOST = '127.0.0.1'  # 服务器地址
SERVER_PORT = 8081  # 修改为 8081 端口

# 创建客户端连接
def create_ssl_client_socket(host, port):
    try:
        # 创建套接字
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SSL/TLS 配置，强制使用 TLS 1.2
        context = ssl.create_default_context()

        # 禁用证书验证（仅适用于开发/测试环境）
        context.check_hostname = False  # 禁用主机名验证
        context.verify_mode = ssl.CERT_NONE  # 禁用证书验证

        # 连接到服务器
        client_socket.connect((host, port))

        # 使用 SSL 包装套接字，强制使用 TLS 1.2
        ssl_client_socket = context.wrap_socket(client_socket, server_hostname=host)

        logger.info(f"成功连接到服务器 {host}:{port}")

        return ssl_client_socket

    except Exception as e:
        logger.error(f"客户端连接失败: {e}")
        return None

# 发送消息到服务器
def send_message(ssl_socket, message):
    try:
        # 发送消息
        ssl_socket.sendall(message.encode())

        # 接收响应
        response = ssl_socket.recv(1024).decode()
        logger.info(f"接收到服务器响应: {response}")

        return response
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return None

# 处理发送按钮点击事件
def on_send_button_click():
    message = message_entry.get()  # 获取用户输入的消息
    if message:
        # 创建 SSL 客户端连接
        ssl_socket = create_ssl_client_socket(SERVER_HOST, SERVER_PORT)
        if ssl_socket:
            response = send_message(ssl_socket, message)
            if response:
                # 显示服务器响应
                response_label.config(text=f"服务器响应: {response}")
            ssl_socket.close()
        else:
            messagebox.showerror("连接失败", "无法连接到服务器。")
    else:
        messagebox.showwarning("输入为空", "请输入要发送的消息。")

# 创建主界面
root = tk.Tk()
root.title("SSL 客户端")

# 设置界面布局
message_label = tk.Label(root, text="请输入消息:")
message_label.pack(pady=5)

message_entry = tk.Entry(root, width=50)
message_entry.pack(pady=5)

send_button = tk.Button(root, text="发送", command=on_send_button_click)
send_button.pack(pady=5)

response_label = tk.Label(root, text="服务器响应将在这里显示")
response_label.pack(pady=20)

# 启动 GUI 主循环
root.mainloop()
