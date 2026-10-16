from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class LiveCaptureUnavailableError(RuntimeError):
    pass


def capture_live_packets(*, interface: str, count: int, timeout: int) -> list[dict[str, Any]]:
    """Capture ARP/ICMP/TCP frames through optional Scapy/Npcap support."""

    try:
        from scapy.all import ARP, ICMP, TCP, sniff
    except ImportError as exc:
        raise LiveCaptureUnavailableError(
            "实时抓包需要安装可选依赖：python -m pip install -e '.[capture]'"
        ) from exc

    try:
        packets = sniff(
            iface=interface or None,
            count=count,
            timeout=timeout,
            store=True,
            lfilter=lambda packet: ARP in packet or ICMP in packet or TCP in packet,
        )
    except Exception as exc:
        raise LiveCaptureUnavailableError(
            "实时抓包启动失败；Windows 通常需要安装 Npcap 并以管理员权限运行。"
        ) from exc

    captured_at = datetime.now(UTC).isoformat()
    return [
        {
            "timestamp": getattr(packet, "time", captured_at).__str__(),
            "packet_bytes": bytes(packet),
        }
        for packet in packets
    ]
