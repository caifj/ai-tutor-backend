# 基座代码编译与隔离运行

## 职责边界

代码运行能力属于基座，不属于任何具体案例：

```text
ExecutionService
  -> CodeRunner：编译、运行、限时、采集 stdout/stderr/退出码
  -> CaseAdapter：提供测试夹具、解释运行输出、生成指标与评分
```

通用数据契约位于 `ai_tutor_backend.code_execution`：

- `PythonRunSpec`：文件列表、入口文件、参数、标准输入和资源上限。
- `PythonRunResult`：编译状态、运行状态、退出码、输出、耗时和截断标记。
- `ExecutionRuntime`：由基座放入 `ExecutionContext`，案例只调用其中的 `code_runner`。

基座不理解 ARP、算法复杂度或 SQL 等业务指标。Case 3 的模拟报文、检查项及评分规则均留在
`backend/cases/case_03_network_protocol_analyzer/` 中。

## 运行模式

`AI_TUTOR_CODE_RUNNER` 支持：

- `disabled`：默认值，不运行学生代码，案例返回沙箱不可用诊断。
- `local`：仅用于开发与自动化测试；代码会在当前机器启动子进程，禁止用于公网 Web 服务。
- `unix`：生产模式，通过 Unix Socket 调用独立沙箱容器。

生产 Web 容器配置：

```env
AI_TUTOR_CODE_RUNNER=unix
AI_TUTOR_CODE_RUNNER_SOCKET=/run/ai-tutor-sandbox/runner.sock
```

沙箱镜像定义位于 `backend/sandbox/Containerfile`。Web 容器和沙箱容器只共享 Unix Socket
目录，不共享数据库、AI Key 或学生历史代码目录。

## 生产隔离要求

运行沙箱时必须同时满足：

- 沙箱容器不配置任何业务密钥和数据库挂载。
- 禁用容器网络；Web 与沙箱仅通过共享 Unix Socket 通信。
- 根文件系统只读，`/tmp` 使用有容量上限的 tmpfs。
- 丢弃 Linux capabilities，启用 `no-new-privileges`、PID、内存和 CPU 限制。
- 每次运行使用临时目录、清洗后的环境变量和非特权 UID。
- 超时后终止整个学生进程组，并限制 stdout/stderr 大小。

示例运行参数：

```bash
docker run -d --name ai-tutor-sandbox --restart unless-stopped \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 256m --cpus 1 \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
  -v ai-tutor-sandbox-socket:/run/ai-tutor-sandbox \
  ai-tutor-sandbox:latest
```

Web 容器挂载同一个 `ai-tutor-sandbox-socket` 卷后即可使用 `unix` 模式。不得把 Docker
Socket 挂入 Web 容器，也不得在 Web 容器中启用 `local` 模式。
