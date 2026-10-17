HARNESS_SOURCE = r'''
import json
import runpy
import sys
import types

MARKER = "__AI_TUTOR_CASE3_RESULT__"


class _Layer:
    defaults = {}

    def __init__(self, **fields):
        values = {**self.defaults, **fields}
        for key, value in values.items():
            setattr(self, key, value)

    def __truediv__(self, other):
        return _Packet([self]) / other


class Ether(_Layer):
    defaults = {"src": "00:00:00:00:00:01", "dst": "ff:ff:ff:ff:ff:ff"}


class ARP(_Layer):
    defaults = {
        "op": 1,
        "psrc": "0.0.0.0",
        "pdst": "0.0.0.0",
        "hwsrc": "00:00:00:00:00:01",
        "hwdst": "00:00:00:00:00:00",
    }


class IP(_Layer):
    defaults = {"src": "0.0.0.0", "dst": "0.0.0.0"}


class ICMP(_Layer):
    defaults = {"type": 8, "code": 0, "id": 1}


class TCP(_Layer):
    defaults = {"sport": 40000, "dport": 80, "flags": "S", "seq": 1}


class _Packet:
    def __init__(self, layers=None):
        self.layers = list(layers or [])

    def __truediv__(self, other):
        if isinstance(other, _Packet):
            return _Packet([*self.layers, *other.layers])
        return _Packet([*self.layers, other])

    def __getitem__(self, layer_type):
        for layer in self.layers:
            if isinstance(layer, layer_type):
                return layer
        raise IndexError(layer_type)

    def haslayer(self, layer_type):
        return any(isinstance(layer, layer_type) for layer in self.layers)


def sniff(*args, **kwargs):
    del args, kwargs
    return []


def _install_scapy_stub():
    scapy_module = types.ModuleType("scapy")
    all_module = types.ModuleType("scapy.all")
    for name, value in {
        "Ether": Ether,
        "ARP": ARP,
        "IP": IP,
        "ICMP": ICMP,
        "TCP": TCP,
        "sniff": sniff,
    }.items():
        setattr(all_module, name, value)
    scapy_module.all = all_module
    sys.modules["scapy"] = scapy_module
    sys.modules["scapy.all"] = all_module


def _safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


checks = []
observations = {}


def _record(check_id, title, operation):
    try:
        value = operation()
        passed, evidence, observation = value
        checks.append(
            {
                "check_id": check_id,
                "title": title,
                "passed": bool(passed),
                "evidence": str(evidence),
            }
        )
        if observation is not None:
            observations[check_id] = _safe(observation)
    except BaseException as exc:
        checks.append(
            {
                "check_id": check_id,
                "title": title,
                "passed": False,
                "evidence": f"{type(exc).__name__}: {exc}",
            }
        )


def _required(namespace, name):
    value = namespace.get(name)
    if not callable(value):
        raise AssertionError(f"未提供可调用函数 {name}")
    return value


def _build_arp(namespace):
    packet = _required(namespace, "build_arp_packet")("10.0.0.1", "10.0.0.2")
    passed = packet.haslayer(ARP) and packet[ARP].psrc == "10.0.0.1" and packet[ARP].pdst == "10.0.0.2"
    return passed, "已执行 ARP 构造并核对源/目标地址", {"psrc": packet[ARP].psrc, "pdst": packet[ARP].pdst}


def _build_icmp(namespace):
    packet = _required(namespace, "build_icmp_packet")("10.0.0.1", "10.0.0.2")
    passed = packet.haslayer(ICMP) and packet[ICMP].type == 8
    return passed, "已执行 ICMP 构造并核对 Echo Request 类型", {
        "source": packet[IP].src,
        "target": packet[IP].dst,
        "type": packet[ICMP].type,
        "code": packet[ICMP].code,
    }


def _build_tcp(namespace):
    packet = _required(namespace, "build_tcp_packet")("10.0.0.1", "10.0.0.2", 443)
    passed = packet.haslayer(TCP) and packet[TCP].dport == 443 and "S" in str(packet[TCP].flags)
    return passed, "已执行 TCP 构造并核对目标端口与 SYN 标志", {
        "source": packet[IP].src,
        "target": packet[IP].dst,
        "dport": packet[TCP].dport,
        "flags": str(packet[TCP].flags),
    }


def _parse_arp(namespace):
    packet = Ether() / ARP(psrc="10.0.0.3", pdst="10.0.0.4")
    value = _required(namespace, "parse_arp_packet")(packet)
    passed = isinstance(value, dict) and "10.0.0.3" in str(value) and "10.0.0.4" in str(value)
    return passed, "使用模拟 ARP 报文执行解析", value


def _parse_icmp(namespace):
    packet = IP(src="10.0.0.3", dst="10.0.0.4") / ICMP(type=3, code=1)
    value = _required(namespace, "parse_icmp_packet")(packet)
    passed = isinstance(value, dict) and "3" in str(value) and "1" in str(value)
    return passed, "使用模拟 ICMP 报文执行解析", value


def _parse_tcp(namespace):
    packet = IP(src="10.0.0.3", dst="10.0.0.4") / TCP(sport=12345, dport=443, flags="S")
    value = _required(namespace, "parse_tcp_packet")(packet)
    passed = isinstance(value, dict) and "12345" in str(value) and "443" in str(value)
    return passed, "使用模拟 TCP 报文执行解析", value


def _capture(namespace):
    value = _required(namespace, "capture_packets")(count=1)
    return isinstance(value, (list, tuple)), "已在替身抓包环境中执行有限次捕获", {"captured": len(value)}


def _detect_scan(namespace):
    packets = [
        IP(src="192.0.2.10", dst="192.0.2.20") / TCP(dport=port, flags="S")
        for port in (21, 22, 80, 443)
    ]
    value = _required(namespace, "detect_port_scan")(packets, threshold=4)
    passed = bool(value) and "192.0.2.10" in str(value)
    return passed, "输入 4 个不同目标端口的 SYN 报文并检查告警", value


def _structured_output(namespace):
    function = namespace.get("analyze_network") or namespace.get("analyze")
    if not callable(function):
        raise AssertionError("未提供 analyze_network 或 analyze 函数")
    value = function()
    passed = isinstance(value, dict) and "packet_records" in value and "anomaly_findings" in value
    return passed, "已执行分析入口并检查结构化输出字段", value


try:
    _install_scapy_stub()
    submitted = runpy.run_path("student.py")
    _record("BUILD_ARP", "运行验证：构造 ARP 报文", lambda: _build_arp(submitted))
    _record("BUILD_ICMP", "运行验证：构造 ICMP 报文", lambda: _build_icmp(submitted))
    _record("BUILD_TCP", "运行验证：构造 TCP 报文", lambda: _build_tcp(submitted))
    _record("CAPTURE_PACKETS", "运行验证：有限抓包", lambda: _capture(submitted))
    _record("PARSE_ARP", "运行验证：解析 ARP 报文", lambda: _parse_arp(submitted))
    _record("PARSE_ICMP", "运行验证：解析 ICMP 报文", lambda: _parse_icmp(submitted))
    _record("PARSE_TCP", "运行验证：解析 TCP 报文", lambda: _parse_tcp(submitted))
    _record("DETECT_SCAN", "运行验证：端口扫描识别", lambda: _detect_scan(submitted))
    _record("STRUCTURED_OUTPUT", "运行验证：结构化输出", lambda: _structured_output(submitted))
    payload = {"checks": checks, "observations": observations}
except BaseException as exc:
    payload = {
        "checks": checks,
        "observations": observations,
        "load_error": f"{type(exc).__name__}: {exc}",
    }

print(MARKER + json.dumps(payload, ensure_ascii=False, default=str))
'''
