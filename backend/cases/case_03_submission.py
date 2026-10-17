"""Example student submission for the case 3 static grader.

This file is analyzed as source text. The AI tutor backend never imports it.
"""

from collections import defaultdict

from scapy.all import ARP, ICMP, IP, TCP, Ether, sniff


def build_arp_packet(source: str, target: str):
    """Build an ARP request."""
    return Ether() / ARP(psrc=source, pdst=target)


def build_icmp_packet(source: str, target: str):
    """Build an ICMP echo request."""
    return IP(src=source, dst=target) / ICMP(type=8)


def build_tcp_packet(source: str, target: str, port: int):
    """Build a TCP SYN packet."""
    return IP(src=source, dst=target) / TCP(dport=port, flags="S")


def capture_packets(count: int = 20):
    """Capture a bounded packet sample."""
    return sniff(count=count, timeout=5)


def parse_arp_packet(packet):
    """Extract ARP addresses."""
    return {"source": packet[ARP].psrc, "target": packet[ARP].pdst}


def parse_icmp_packet(packet):
    """Extract ICMP type and code."""
    return {"type": packet[ICMP].type, "code": packet[ICMP].code}


def parse_tcp_packet(packet):
    """Extract TCP ports and flags."""
    return {
        "source_port": packet[TCP].sport,
        "target_port": packet[TCP].dport,
        "flags": str(packet[TCP].flags),
    }


def detect_port_scan(packets, threshold: int = 4):
    """Report sources contacting many distinct destination ports."""
    unique_ports = defaultdict(set)
    for packet in packets:
        if packet.haslayer(TCP) and packet[TCP].flags == "S":
            unique_ports[packet[IP].src].add(packet[TCP].dport)
    return [source for source, ports in unique_ports.items() if len(ports) >= threshold]


def analyze_packets() -> dict:
    """Return structured packet records and anomaly findings."""
    packets = capture_packets()
    packet_records = [
        parse_tcp_packet(packet) for packet in packets if packet.haslayer(TCP)
    ]
    anomaly_findings = detect_port_scan(packets)
    return {
        "packet_records": packet_records,
        "anomaly_findings": anomaly_findings,
    }
