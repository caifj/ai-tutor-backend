"""案例 3 正确样例：覆盖报文构造、捕获、解析和扫描识别。

本文件用于代码静态评测演示，后端不会导入或执行它。
"""

from collections import defaultdict

from scapy.all import ARP, ICMP, IP, TCP, Ether, sniff


def build_arp_packet(source_ip: str, target_ip: str):
    """构造 ARP 请求报文。"""
    return Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(
        op=1,
        psrc=source_ip,
        pdst=target_ip,
    )


def build_icmp_packet(source_ip: str, target_ip: str):
    """构造 ICMP Echo Request 报文。"""
    return IP(src=source_ip, dst=target_ip) / ICMP(type=8, code=0)


def build_tcp_packet(source_ip: str, target_ip: str, target_port: int):
    """构造带 SYN 标志的 TCP 探测报文。"""
    return IP(src=source_ip, dst=target_ip) / TCP(
        sport=40000,
        dport=target_port,
        flags="S",
    )


def capture_packets(interface: str | None = None, count: int = 20):
    """在限定数量和超时时间内捕获报文。"""
    return sniff(iface=interface, count=count, timeout=5, store=True)


def parse_arp_packet(packet) -> dict:
    """解析 ARP 地址和操作类型。"""
    arp = packet[ARP]
    return {
        "protocol": "ARP",
        "operation": int(arp.op),
        "source_ip": arp.psrc,
        "source_mac": arp.hwsrc,
        "target_ip": arp.pdst,
        "target_mac": arp.hwdst,
    }


def parse_icmp_packet(packet) -> dict:
    """解析 ICMP 类型、代码及通信端点。"""
    ip = packet[IP]
    icmp = packet[ICMP]
    return {
        "protocol": "ICMP",
        "source_ip": ip.src,
        "target_ip": ip.dst,
        "type": int(icmp.type),
        "code": int(icmp.code),
    }


def parse_tcp_packet(packet) -> dict:
    """解析 TCP 端口和标志位。"""
    ip = packet[IP]
    tcp = packet[TCP]
    return {
        "protocol": "TCP",
        "source_ip": ip.src,
        "target_ip": ip.dst,
        "source_port": int(tcp.sport),
        "target_port": int(tcp.dport),
        "flags": str(tcp.flags),
    }


def parse_packet(packet) -> dict | None:
    """按协议分派到对应解析函数。"""
    if packet.haslayer(ARP):
        return parse_arp_packet(packet)
    if packet.haslayer(ICMP):
        return parse_icmp_packet(packet)
    if packet.haslayer(TCP):
        return parse_tcp_packet(packet)
    return None


def detect_port_scan(packets, threshold: int = 4) -> list[dict]:
    """识别同一来源访问多个不同目标端口的 SYN 扫描。"""
    unique_ports: dict[str, set[int]] = defaultdict(set)
    for packet in packets:
        if packet.haslayer(IP) and packet.haslayer(TCP):
            tcp = packet[TCP]
            if str(tcp.flags) == "S":
                unique_ports[packet[IP].src].add(int(tcp.dport))

    anomalies = []
    for source, ports in unique_ports.items():
        if len(ports) >= threshold:
            anomalies.append(
                {
                    "type": "TCP_SYN_PORT_SCAN",
                    "source": source,
                    "distinct_ports": sorted(ports),
                }
            )
    return anomalies


def analyze_network(interface: str | None = None) -> dict:
    """捕获并输出结构化抓包记录和异常识别结果。"""
    packets = capture_packets(interface=interface)
    packet_records = []
    for packet in packets:
        record = parse_packet(packet)
        if record is not None:
            packet_records.append(record)

    anomaly_findings = detect_port_scan(packets)
    return {
        "packet_records": packet_records,
        "anomaly_findings": anomaly_findings,
    }

