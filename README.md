# 基于 RAG 与工具调度的 ReAct 智能体 Agent

基于 Function-Calling 构建的多功能智能体，由大模型自主决策工具调度，覆盖**本地知识库问答**与**联网信息检索**两大能力，并支持提示词 + 参考图生图。

## 技术栈

Python · FastAPI · ChromaDB · Function-Calling · httpx / BeautifulSoup

## 目录结构

```
├── agent.py            主程序（ReAct 决策循环 + Function-Calling 工具调度）
├── tool_server.py      FastAPI 工具服务（联网搜索 / 网页抓取，含 SSRF 防护）
├── chroma.py           向量库增量入库与脏分片管理
```

## 核心特性

- **向量库增量与脏分片管理**：PDF / TXT 解析分片；MD5 校验文件变更实现增量入库，自动清理已删除文件对应的向量分片，避免全量重建与数据冗余。
- **多工具模块化设计**：联网搜索、网页抓取封装为独立 FastAPI 服务，Agent 决策逻辑与网络 IO 解耦；新增工具仅需注册描述 Schema。
- **工具调度策略**：本地知识库优先、联网检索兜底，未覆盖问题时自动联网，控制无效远程请求。
- **SSRF 安全防护**：网页抓取前先做域名预解析、获取全部真实 IP 并校验网段，拦截内网 / 回环 / 云元数据地址，规避内网资源越权访问。
- **手写 Agent 与 LangChain 对照**：手写原生 Agent 实现，并与 LangChain 封装方案对照，理解工具调用底层逻辑。

## 运行方式

1. 配置 `.env`：

   ```
   API_KEY=<你的模型 API Key>
   TAVILY_API_KEY=<你的 Tavily API Key>
   ```

2. 启动工具服务：

   ```bash
   python tool_server.py
   ```

3. 另开终端启动主程序：

   ```bash
   python agent.py
   ```