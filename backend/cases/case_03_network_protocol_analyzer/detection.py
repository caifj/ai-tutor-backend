from __future__ import annotations

from collections import defaultdict

from .codec import ParsedPacket


def detect_anomalies(packets: list[ParsedPacket], threshold: int) -> list[dict]:
    findings: list[dict] = []
    syn_ports: dict[tuple[str, str], set[int]] = defaultdict(set)
    icmp_targets: dict[str, set[str]] = defaultdict(set)
    arp_targets: dict[str, set[str]] = defaultdict(set)
    arp_owners: dict[str, set[str]] = defaultdict(set)

    for packet in packets:
        fields = packet.fields
        if packet.protocol == "TCP":
            flags = set(fields["tcp_flags"])
            source_ip = fields["source_ip"]
            destination_ip = fields["destination_ip"]
            destination_port = fields["destination_port"]
            if "SYN" in flags and "ACK" not in flags:
                syn_ports[(source_ip, destination_ip)].add(destination_port)
            if not flags:
                findings.append(
                    _finding(
                        "TCP_NULL_SCAN",
                        "high",
                        source_ip,
                        destination_ip,
                        f"发送至端口 {destination_port} 的 TCP 报文未设置任何标志",
                        "检查源主机并结合防火墙日志确认是否为 Null Scan。",
                    )
                )
            if {"FIN", "PSH", "URG"}.issubset(flags):
                findings.append(
                    _finding(
                        "TCP_XMAS_SCAN",
                        "high",
                        source_ip,
                        destination_ip,
                        f"端口 {destination_port} 同时设置 FIN/PSH/URG",
                        "检查源主机并阻断非业务需要的异常 TCP 探测。",
                    )
                )
            if {"SYN", "FIN"}.issubset(flags):
                findings.append(
                    _finding(
                        "INVALID_TCP_FLAGS",
                        "medium",
                        source_ip,
                        destination_ip,
                        f"端口 {destination_port} 同时设置 SYN 与 FIN",
                        "核查报文生成程序或潜在规避检测行为。",
                    )
                )
        elif packet.protocol == "ICMP" and fields["icmp_type"] == 8:
            icmp_targets[fields["source_ip"]].add(fields["destination_ip"])
        elif packet.protocol == "ARP":
            arp_owners[fields["sender_ip"]].add(fields["sender_mac"])
            if fields["operation"] == "request":
                arp_targets[fields["sender_ip"]].add(fields["target_ip"])

    for (source, target), ports in sorted(syn_ports.items()):
        if len(ports) >= threshold:
            findings.append(
                _finding(
                    "TCP_SYN_PORT_SCAN",
                    "high",
                    source,
                    target,
                    f"观察到 {len(ports)} 个不同目标端口：{', '.join(map(str, sorted(ports)))}",
                    "限制连接速率，并结合资产清单确认扫描是否经过授权。",
                )
            )
    for source, targets in sorted(icmp_targets.items()):
        if len(targets) >= threshold:
            findings.append(
                _finding(
                    "ICMP_HOST_SWEEP",
                    "medium",
                    source,
                    "多个主机",
                    f"ICMP Echo Request 覆盖 {len(targets)} 个目标地址",
                    "检查是否为授权存活探测，并评估 ICMP 速率限制。",
                )
            )
    for source, targets in sorted(arp_targets.items()):
        if len(targets) >= threshold:
            findings.append(
                _finding(
                    "ARP_HOST_SWEEP",
                    "medium",
                    source,
                    "本地网段",
                    f"ARP Request 覆盖 {len(targets)} 个目标地址",
                    "确认是否为资产发现任务，并排查未知扫描终端。",
                )
            )
    for address, macs in sorted(arp_owners.items()):
        if len(macs) > 1:
            findings.append(
                _finding(
                    "ARP_IP_CONFLICT",
                    "high",
                    ", ".join(sorted(macs)),
                    address,
                    f"同一 IPv4 地址由 {len(macs)} 个 MAC 地址声明",
                    "核验地址冲突，并排查 ARP 欺骗或网关冒充。",
                )
            )
    return findings


def _finding(
    code: str,
    severity: str,
    source: str,
    target: str,
    evidence: str,
    recommendation: str,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "source": source,
        "target": target,
        "evidence": evidence,
        "recommendation": recommendation,
    }
