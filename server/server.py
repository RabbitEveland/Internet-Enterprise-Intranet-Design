import socket
import ssl
import logging
import os

# 设置日志
def setup_logger():
    """
    配置日志记录器
    """
    log_file = "server_log.log"  # 日志文件路径
    logger = logging.getLogger('server_log')
    logger.setLevel(logging.DEBUG)  # 设置日志级别为 DEBUG，捕获更多信息

    # 防止重复记录日志
    if not logger.hasHandlers():
        # 创建文件处理器，指定编码为 utf-8
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 日志格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 将处理器添加到logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


# 初始化日志记录器
logger = setup_logger()

# 服务器信息
HOST = '127.0.0.1'  # 本机地址
PORT = 8081  # 监听端口


# 加载证书和私钥
def load_cert_and_key():
    try:
        certfile = "server.pem"  # 证书文件路径
        keyfile = "server.key"  # 私钥文件路径
        if not os.path.exists(certfile) or not os.path.exists(keyfile):
            logger.error(f"{certfile} 或 {keyfile} 文件未找到")
            raise FileNotFoundError("证书或私钥文件未找到")
        # 加载证书和私钥
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        return context
    except Exception as e:
        logger.error(f"加载证书和私钥时发生错误: {e}")
        return None


# 启动服务器
def start_server():
    try:
        context = load_cert_and_key()
        if not context:
            return

        # 创建套接字并绑定
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        logger.info(f"服务器启动，监听 {HOST}:{PORT}")

        while True:
            # 接受连接
            client_socket, client_address = server_socket.accept()
            logger.info(f"接收到来自 {client_address} 的连接")

            # 使用 SSL 包装套接字
            ssl_client_socket = context.wrap_socket(client_socket, server_side=True)

            try:
                # 处理客户端请求
                handle_client_request(ssl_client_socket)
            except Exception as e:
                logger.error(f"处理客户端请求时发生错误: {e}")
            finally:
                # 关闭连接
                ssl_client_socket.close()
                logger.info(f"与 {client_address} 的连接已关闭")
    except Exception as e:
        logger.error(f"启动服务器时发生错误: {e}")


# 处理客户端请求
def handle_client_request(ssl_socket):
    try:
        # 接收客户端消息
        message = ssl_socket.recv(1024).decode()
        logger.info(f"接收到客户端消息: {message}")

        # 处理消息并响应
        if message.lower() == "你好":
            response = "你好，客户端！"
        else:
            response = f"你说的是: {message}"

        # 发送响应
        ssl_socket.sendall(response.encode())
        logger.info(f"发送响应: {response}")
    except Exception as e:
        logger.error(f"接收或发送消息时发生错误: {e}")


if __name__ == "__main__":
    start_server()
