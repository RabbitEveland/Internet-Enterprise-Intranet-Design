import ssl
import logging
import socket

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

# 主函数
def main():
    # 创建 SSL 客户端连接
    ssl_socket = create_ssl_client_socket(SERVER_HOST, SERVER_PORT)

    if ssl_socket:
        # 让用户输入消息
        message = input("请输入消息发送给服务器: ")

        # 发送消息到服务器
        response = send_message(ssl_socket, message)

        # 输出响应
        if response:
            print(f"服务器响应: {response}")

        # 关闭连接
        ssl_socket.close()
        logger.info("连接已关闭")

if __name__ == '__main__':
    main()
