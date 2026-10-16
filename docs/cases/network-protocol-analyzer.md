# 案例 3：网络协议分析仪

## 目标

本案例对应“计算机网络”课程，提供以下能力：

- 手动构造 ARP、ICMP、TCP 以太网报文。
- 解析单个十六进制报文。
- 导入并分析离线捕获记录。
- 在安装可选依赖和抓包驱动后执行实时抓包。
- 输出标准化抓包记录、协议字段、原始十六进制和异常流量识别结果。
- 识别 TCP SYN 端口扫描、TCP Null/Xmas 扫描、异常 SYN+FIN、ICMP 主机扫描、
  ARP 主机扫描及 ARP 地址冲突。

案例代码位于：

```text
cases/case_03_network_protocol_analyzer/
  adapter.py      底座适配、输入模型和标准输出
  codec.py        ARP/ICMP/TCP 构造与解析
  capture.py      可选实时抓包入口
  detection.py    异常流量检测规则
```

所有正式案例统一放在仓库根目录的 `cases/` 下，并由 `cases.register_cases()` 注册。演示插件仍
位于 `examples/`，不会和正式案例混放。

## 启动

正式案例包现在是默认加载项：

```powershell
cd G:\ai_code
.\.venv\Scripts\Activate.ps1
uvicorn ai_tutor_backend.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/`，模块目录会自动出现“网络协议分析仪”。

如需同时加载演示案例：

```powershell
$env:AI_TUTOR_CASE_MODULES = "cases,examples.demo_case_package"
uvicorn ai_tutor_backend.main:app --host 127.0.0.1 --port 8000
```

## 三种操作

### 1. 构造并解析报文

选择 `operation=construct`，再选择 `ARP`、`ICMP` 或 `TCP`。构造器会计算 IPv4、ICMP、
TCP 校验和，并将构造结果立即交给解析器验证。

请求示例：

```json
{
  "case_id": "network.protocol-analyzer",
  "input": {
    "operation": "construct",
    "protocol": "TCP",
    "source_mac": "02:00:00:00:00:01",
    "destination_mac": "ff:ff:ff:ff:ff:ff",
    "source_ip": "192.168.1.10",
    "destination_ip": "192.168.1.1",
    "source_port": 40000,
    "destination_port": 80,
    "tcp_flags": "SYN",
    "payload_text": "AI Tutor"
  }
}
```

### 2. 解析十六进制报文

选择 `operation=analyze`，并把完整以太网帧放入 `packet_hex`。输入可以包含空格、冒号、
连字符或换行，但不能只提供 IP/TCP 片段。

```json
{
  "case_id": "network.protocol-analyzer",
  "input": {
    "operation": "analyze",
    "packet_hex": "ffffffffffff0200000000010806..."
  }
}
```

### 3. 分析捕获记录

离线方式无需抓包权限，适合教学数据集和自动测试。选择 `operation=capture`、
`capture_source=offline`，把记录数组序列化后放入 `capture_packets_json`：

```json
[
  {
    "timestamp": "2026-10-16T10:00:00Z",
    "packet_hex": "完整以太网帧十六进制"
  },
  "也可以直接放十六进制字符串"
]
```

`scan_threshold` 控制同一来源访问多少个不同端口或主机后报告扫描，默认值为 4。

## 实时抓包

实时抓包是可选功能，避免基础安装强制依赖系统驱动。安装 Python 依赖：

```powershell
python -m pip install -e ".[capture]"
```

Windows 还需要安装 Npcap，并通常要用管理员权限启动后端。随后选择：

```json
{
  "operation": "capture",
  "capture_source": "live",
  "capture_interface": "",
  "capture_count": 20,
  "capture_timeout": 5,
  "scan_threshold": 4
}
```

实时抓包只应在本人管理或明确获准分析的网络中使用。底座限制单次最多 100 个目标协议报文、
超时最多 15 秒，避免 HTTP 请求无限占用抓包资源。

## 标准输出

输出包含两个数据集：

- `packet_records`：时间、协议、源、目标、长度、摘要、解析字段和原始报文。
- `anomaly_findings`：异常代码、严重程度、来源、目标、判定依据和处置建议。

指标包括报文总数、无效报文数、总字节数、各协议计数、异常数量和扫描阈值。所有结果均可
通过底座导出为 JSON 或 CSV。

## 限制

- 当前解析器面向 Ethernet II、可选单层 802.1Q VLAN、ARP over IPv4、IPv4 ICMP 和 IPv4 TCP。
- 暂不重组 IPv4 分片或 TCP 流，也不解析 IPv6、UDP、应用层协议或加密内容。
- 扫描检测是教学规则，不应替代生产 IDS/IPS；告警需要结合资产、时间窗口和业务流量复核。
