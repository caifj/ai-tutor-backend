from __future__ import annotations

import ipaddress
import re
import struct
from dataclasses import dataclass


class PacketCodecError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedPacket:
    protocol: str
    source: str
    destination: str
    length: int
    summary: str
    fields: dict
    packet_hex: str


TCP_FLAG_BITS = {
    "FIN": 0x01,
    "SYN": 0x02,
    "RST": 0x04,
    "PSH": 0x08,
    "ACK": 0x10,
    "URG": 0x20,
    "ECE": 0x40,
    "CWR": 0x80,
}


def normalize_packet_hex(value: str) -> bytes:
    normalized = re.sub(r"[\s:\-]", "", value)
    if not normalized:
        raise PacketCodecError("报文十六进制内容不能为空")
    if len(normalized) % 2:
        raise PacketCodecError("十六进制报文长度必须是偶数")
    if re.search(r"[^0-9a-fA-F]", normalized):
        raise PacketCodecError("报文包含非十六进制字符")
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise PacketCodecError("无法解析十六进制报文") from exc


def build_packet(
    *,
    protocol: str,
    source_mac: str,
    destination_mac: str,
    source_ip: str,
    destination_ip: str,
    source_port: int,
    destination_port: int,
    tcp_flags: str,
    arp_operation: str,
    payload_text: str,
) -> bytes:
    protocol = protocol.upper()
    if protocol == "ARP":
        return _build_arp(
            source_mac=source_mac,
            destination_mac=destination_mac,
            source_ip=source_ip,
            destination_ip=destination_ip,
            operation=arp_operation,
        )
    if protocol == "ICMP":
        icmp = _build_icmp(payload_text.encode("utf-8"))
        ip_packet = _build_ipv4(source_ip, destination_ip, 1, icmp)
        return _ethernet(destination_mac, source_mac, 0x0800) + ip_packet
    if protocol == "TCP":
        payload = payload_text.encode("utf-8")
        tcp = _build_tcp(
            source_ip=source_ip,
            destination_ip=destination_ip,
            source_port=source_port,
            destination_port=destination_port,
            flags=tcp_flags,
            payload=payload,
        )
        ip_packet = _build_ipv4(source_ip, destination_ip, 6, tcp + payload)
        return _ethernet(destination_mac, source_mac, 0x0800) + ip_packet
    raise PacketCodecError(f"不支持构造协议：{protocol}")


def parse_packet(frame: bytes) -> ParsedPacket:
    if len(frame) < 14:
        raise PacketCodecError("以太网帧不足 14 字节")
    destination_mac = _format_mac(frame[0:6])
    source_mac = _format_mac(frame[6:12])
    ether_type = struct.unpack("!H", frame[12:14])[0]
    offset = 14
    vlan_id = None
    if ether_type == 0x8100:
        if len(frame) < 18:
            raise PacketCodecError("VLAN 以太网帧头不完整")
        vlan_tci, ether_type = struct.unpack("!HH", frame[14:18])
        vlan_id = vlan_tci & 0x0FFF
        offset = 18

    ethernet_fields = {
        "source_mac": source_mac,
        "destination_mac": destination_mac,
        "ether_type": f"0x{ether_type:04x}",
    }
    if vlan_id is not None:
        ethernet_fields["vlan_id"] = vlan_id

    if ether_type == 0x0806:
        return _parse_arp(frame, offset, ethernet_fields)
    if ether_type == 0x0800:
        return _parse_ipv4(frame, offset, ethernet_fields)
    raise PacketCodecError(f"暂不支持 EtherType 0x{ether_type:04x}")


def _build_arp(
    *,
    source_mac: str,
    destination_mac: str,
    source_ip: str,
    destination_ip: str,
    operation: str,
) -> bytes:
    source_mac_bytes = _mac_bytes(source_mac)
    destination_mac_bytes = _mac_bytes(destination_mac)
    source_ip_bytes = ipaddress.IPv4Address(source_ip).packed
    destination_ip_bytes = ipaddress.IPv4Address(destination_ip).packed
    opcode = 1 if operation == "request" else 2
    target_mac = b"\x00" * 6 if opcode == 1 else destination_mac_bytes
    arp = struct.pack(
        "!HHBBH6s4s6s4s",
        1,
        0x0800,
        6,
        4,
        opcode,
        source_mac_bytes,
        source_ip_bytes,
        target_mac,
        destination_ip_bytes,
    )
    return _ethernet(destination_mac, source_mac, 0x0806) + arp


def _build_icmp(payload: bytes) -> bytes:
    header = struct.pack("!BBHHH", 8, 0, 0, 1, 1)
    checksum = internet_checksum(header + payload)
    return struct.pack("!BBHHH", 8, 0, checksum, 1, 1) + payload


def _build_tcp(
    *,
    source_ip: str,
    destination_ip: str,
    source_port: int,
    destination_port: int,
    flags: str,
    payload: bytes,
) -> bytes:
    flag_bits = parse_tcp_flags(flags)
    offset_and_flags = (5 << 12) | flag_bits
    header = struct.pack(
        "!HHIIHHHH",
        source_port,
        destination_port,
        0,
        0,
        offset_and_flags,
        65535,
        0,
        0,
    )
    pseudo_header = (
        ipaddress.IPv4Address(source_ip).packed
        + ipaddress.IPv4Address(destination_ip).packed
        + struct.pack("!BBH", 0, 6, len(header) + len(payload))
    )
    checksum = internet_checksum(pseudo_header + header + payload)
    return header[:16] + struct.pack("!H", checksum) + header[18:]


def _build_ipv4(source_ip: str, destination_ip: str, protocol: int, payload: bytes) -> bytes:
    source = ipaddress.IPv4Address(source_ip).packed
    destination = ipaddress.IPv4Address(destination_ip).packed
    total_length = 20 + len(payload)
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        0,
        0,
        64,
        protocol,
        0,
        source,
        destination,
    )
    checksum = internet_checksum(header)
    return header[:10] + struct.pack("!H", checksum) + header[12:] + payload


def _ethernet(destination_mac: str, source_mac: str, ether_type: int) -> bytes:
    return _mac_bytes(destination_mac) + _mac_bytes(source_mac) + struct.pack("!H", ether_type)


def _parse_arp(frame: bytes, offset: int, ethernet_fields: dict) -> ParsedPacket:
    if len(frame) < offset + 28:
        raise PacketCodecError("ARP 报文头不完整")
    htype, ptype, hlen, plen, opcode, sender_mac, sender_ip, target_mac, target_ip = struct.unpack(
        "!HHBBH6s4s6s4s", frame[offset : offset + 28]
    )
    if htype != 1 or ptype != 0x0800 or hlen != 6 or plen != 4:
        raise PacketCodecError("仅支持以太网/IPv4 ARP 报文")
    source = str(ipaddress.IPv4Address(sender_ip))
    destination = str(ipaddress.IPv4Address(target_ip))
    operation = {1: "request", 2: "reply"}.get(opcode, f"opcode_{opcode}")
    fields = {
        **ethernet_fields,
        "operation": operation,
        "sender_mac": _format_mac(sender_mac),
        "sender_ip": source,
        "target_mac": _format_mac(target_mac),
        "target_ip": destination,
    }
    summary = (
        f"ARP 请求：谁拥有 {destination}？"
        if opcode == 1
        else f"ARP 响应：{source} 位于 {fields['sender_mac']}"
    )
    return ParsedPacket(
        protocol="ARP",
        source=source,
        destination=destination,
        length=len(frame),
        summary=summary,
        fields=fields,
        packet_hex=frame.hex(),
    )


def _parse_ipv4(frame: bytes, offset: int, ethernet_fields: dict) -> ParsedPacket:
    if len(frame) < offset + 20:
        raise PacketCodecError("IPv4 报文头不完整")
    version_ihl = frame[offset]
    version = version_ihl >> 4
    ihl = (version_ihl & 0x0F) * 4
    if version != 4 or ihl < 20 or len(frame) < offset + ihl:
        raise PacketCodecError("IPv4 版本或头长度无效")
    total_length = struct.unpack("!H", frame[offset + 2 : offset + 4])[0]
    if total_length < ihl or len(frame) < offset + total_length:
        raise PacketCodecError("IPv4 报文声明长度超过实际帧长度")
    ttl = frame[offset + 8]
    protocol_number = frame[offset + 9]
    source_ip = str(ipaddress.IPv4Address(frame[offset + 12 : offset + 16]))
    destination_ip = str(ipaddress.IPv4Address(frame[offset + 16 : offset + 20]))
    header = frame[offset : offset + ihl]
    ip_fields = {
        **ethernet_fields,
        "ip_version": 4,
        "ip_header_length": ihl,
        "ip_total_length": total_length,
        "ttl": ttl,
        "source_ip": source_ip,
        "destination_ip": destination_ip,
        "ip_checksum_valid": internet_checksum(header) == 0,
    }
    transport_offset = offset + ihl
    packet_end = offset + total_length
    if protocol_number == 1:
        return _parse_icmp(
            frame, transport_offset, packet_end, source_ip, destination_ip, ip_fields
        )
    if protocol_number == 6:
        return _parse_tcp(frame, transport_offset, packet_end, source_ip, destination_ip, ip_fields)
    raise PacketCodecError(f"IPv4 上层协议 {protocol_number} 暂不支持")


def _parse_icmp(
    frame: bytes,
    offset: int,
    packet_end: int,
    source_ip: str,
    destination_ip: str,
    ip_fields: dict,
) -> ParsedPacket:
    if packet_end < offset + 8:
        raise PacketCodecError("ICMP 报文头不完整")
    icmp_type, code, checksum, identifier, sequence = struct.unpack(
        "!BBHHH", frame[offset : offset + 8]
    )
    names = {0: "Echo Reply", 3: "Destination Unreachable", 8: "Echo Request", 11: "Time Exceeded"}
    type_name = names.get(icmp_type, f"Type {icmp_type}")
    fields = {
        **ip_fields,
        "icmp_type": icmp_type,
        "icmp_type_name": type_name,
        "icmp_code": code,
        "icmp_checksum": f"0x{checksum:04x}",
        "icmp_checksum_valid": internet_checksum(frame[offset:packet_end]) == 0,
        "identifier": identifier,
        "sequence": sequence,
        "payload_length": max(packet_end - offset - 8, 0),
    }
    return ParsedPacket(
        protocol="ICMP",
        source=source_ip,
        destination=destination_ip,
        length=len(frame),
        summary=f"ICMP {type_name} {source_ip} → {destination_ip}",
        fields=fields,
        packet_hex=frame.hex(),
    )


def _parse_tcp(
    frame: bytes,
    offset: int,
    packet_end: int,
    source_ip: str,
    destination_ip: str,
    ip_fields: dict,
) -> ParsedPacket:
    if packet_end < offset + 20:
        raise PacketCodecError("TCP 报文头不完整")
    (
        source_port,
        destination_port,
        sequence,
        acknowledgement,
        offset_flags,
        window,
        checksum,
        urgent,
    ) = struct.unpack("!HHIIHHHH", frame[offset : offset + 20])
    header_length = ((offset_flags >> 12) & 0x0F) * 4
    if header_length < 20 or packet_end < offset + header_length:
        raise PacketCodecError("TCP 头长度无效")
    flag_bits = offset_flags & 0x01FF
    flags = [name for name, bit in TCP_FLAG_BITS.items() if flag_bits & bit]
    segment = frame[offset:packet_end]
    pseudo_header = (
        ipaddress.IPv4Address(source_ip).packed
        + ipaddress.IPv4Address(destination_ip).packed
        + struct.pack("!BBH", 0, 6, len(segment))
    )
    fields = {
        **ip_fields,
        "source_port": source_port,
        "destination_port": destination_port,
        "sequence_number": sequence,
        "acknowledgement_number": acknowledgement,
        "tcp_header_length": header_length,
        "tcp_flags": flags,
        "tcp_flag_bits": flag_bits,
        "window_size": window,
        "urgent_pointer": urgent,
        "tcp_checksum": f"0x{checksum:04x}",
        "tcp_checksum_valid": internet_checksum(pseudo_header + segment) == 0,
        "payload_length": max(packet_end - offset - header_length, 0),
    }
    flag_text = ",".join(flags) if flags else "NONE"
    return ParsedPacket(
        protocol="TCP",
        source=f"{source_ip}:{source_port}",
        destination=f"{destination_ip}:{destination_port}",
        length=len(frame),
        summary=f"TCP [{flag_text}] {source_ip}:{source_port} → {destination_ip}:{destination_port}",
        fields=fields,
        packet_hex=frame.hex(),
    )


def parse_tcp_flags(value: str) -> int:
    names = [item for item in re.split(r"[\s,|+]+", value.upper().strip()) if item]
    unknown = sorted(set(names) - set(TCP_FLAG_BITS))
    if unknown:
        raise PacketCodecError(f"未知 TCP 标志：{', '.join(unknown)}")
    result = 0
    for name in names:
        result |= TCP_FLAG_BITS[name]
    return result


def internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return (~total) & 0xFFFF


def _mac_bytes(value: str) -> bytes:
    normalized = re.sub(r"[:-]", "", value)
    if not re.fullmatch(r"[0-9a-fA-F]{12}", normalized):
        raise PacketCodecError(f"MAC 地址格式无效：{value}")
    return bytes.fromhex(normalized)


def _format_mac(value: bytes) -> str:
    return ":".join(f"{part:02x}" for part in value)
