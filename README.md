# Python TLS Socket 通信示例

一个用于演示 Python `socket`、TLS/SSL 与 Tkinter 的本地客户端—服务器通信项目。服务端在本机 `127.0.0.1:8081` 上监听；客户端发送一条文本消息后，服务端返回问候语或原样回显。

> 此项目用于本地学习与演示。客户端为方便连接自签名证书而关闭了证书和主机名校验，**请勿直接用于生产环境**。

## 功能

- TLS 加密的 TCP 服务端与命令行客户端
- Tkinter 图形客户端
- 自签名证书和私钥生成脚本
- 基于 `cryptography.fernet` 的独立加解密工具函数

## 项目结构

```text
.
├── client_script.py          # 命令行 TLS 客户端
├── generate_cert.py          # 在当前目录生成证书与私钥的脚本
├── client/
│   ├── client.py             # Tkinter TLS 客户端
│   └── client_gui.py         # 基础 Tkinter 界面示例
├── common/
│   ├── encryption.py         # Fernet 加解密工具
│   └── logger.py             # 日志工具
└── server/
    ├── server.py             # TLS 回显服务端
    └── cert_generator.py     # 为服务端生成证书与私钥
```

## 环境要求

- Python 3.12（其他较新的 Python 3 版本通常也可使用）
- `cryptography`

安装依赖：

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install cryptography
```

## 运行

先在一个终端启动服务端。证书生成脚本会在 `server/` 目录中生成服务端所需的 `server.pem` 和 `server.key`：

```bash
cd server
python cert_generator.py
python server.py
```

然后在项目根目录的另一个终端运行命令行客户端：

```bash
python client_script.py
```

输入 `你好` 时，服务端会回复 `你好，客户端！`；输入其他文本时，会返回 `你说的是: <输入内容>`。

也可以启动图形客户端：

```bash
python client/client.py
```

## 配置说明

代码当前直接使用 `127.0.0.1:8081`。项目中保留了若干 `config.ini` 示例文件，但现有服务端与客户端尚未读取这些文件；如需改动地址或端口，请同时修改对应 Python 文件中的常量。

## TLS 文件与日志

运行后产生的私钥（`.key`）、证书（`.pem`）、日志、虚拟环境和 IDE 设置均不纳入版本控制。请在每台需要运行服务端的设备上重新生成本地证书，且不要将私钥上传到公开仓库。
