"""案例 3 错误样例：代码可解析，但没有完成规定功能。

该样例故意保留错误设计，用于观察未通过项和安全警告。
"""

import socket


def capture():
    # 错误：普通 TCP 套接字不是协议分析所需的原始抓包接口，也没有数量或超时限制。
    connection = socket.socket()
    connection.connect(("127.0.0.1", 80))
    return connection.recv(1024)


def parse(data):
    # 错误：仅把字节转成字符串，没有解析 ARP、ICMP 或 TCP 字段。
    return str(data)


def run(user_expression):
    # 错误：没有构造三类报文、没有扫描检测，也没有规定的结构化输出。
    raw_data = capture()
    print(parse(raw_data))
    return eval(user_expression)

