# 部署文档（Deployment Guide）

本文档说明如何将「RAG 智能问答 Agent」从代码仓库部署到一台目标机器并稳定运行，适用于现场交付 / 项目交接场景。

## 1. 项目简介

基于 Function-Calling 的 ReAct 多工具智能体，覆盖本地知识库问答（RAG）、联网检索、网页精读、文生图，并内置短期 + 长期双记忆。架构上拆分两个进程：

| 进程 | 作用 |
| --- | --- |
| `tool_server.py` | FastAPI 工具服务，提供联网搜索 / 网页抓取（含 SSRF 防护），监听 `127.0.0.1:8000` |
| `agent.py` | 主程序，ReAct 决策循环，调用工具服务与本地向量库 |

## 2. 前置要求

- Python 3.9+（推荐 3.10 / 3.11）
- 能访问外网（用于安装依赖、调用模型与联网搜索 API）
- 已准备好模型 API Key（火山方舟 Ark）与 Tavily API Key

## 3. 目录结构（关键文件）

```
├── agent.py          # 主程序（ReAct 决策循环 + 工具调度 + 双记忆）
├── tool_server.py    # FastAPI 工具服务（联网搜索 / 网页抓取）
├── chroma.py         # 知识库入库脚本（增量 + 脏数据清理）
├── requirements.txt  # 依赖清单
├── .env.example      # 环境变量模板（复制为 .env 后填写）
├── DEPLOY.md         # 本文档
└── README.md         # 项目说明与功能演示
```

## 4. 部署步骤

### 步骤 1：获取代码

```bash
git clone https://github.com/dengyu-han/react-rag-agent.git
cd react-rag-agent
```

> 目标机无外网 / 无 git 时，可将仓库整体打包拷贝到目标机后解压。

### 步骤 2：创建虚拟环境

```bash
# Windows（PowerShell / CMD）
python -m venv venv

# Linux / macOS
python3 -m venv venv
```

### 步骤 3：激活虚拟环境

```bash
# Windows（PowerShell）
venv\Scripts\Activate.ps1
# Windows（CMD）
venv\Scripts\activate.bat

# Linux / macOS
source venv/bin/activate
```

> 激活成功后命令行前缀出现 `(venv)`，表示后续命令都在隔离环境内执行。

### 步骤 4：安装依赖

```bash
pip install -r requirements.txt
```

> 安装缓慢 / 网络受限时可指定国内镜像：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 步骤 5：配置环境变量

```bash
# 复制模板为 .env
# Windows
copy .env.example .env
# Linux / macOS
cp .env.example .env
```

编辑 `.env`，填入真实密钥：

```
API_KEY=<火山方舟 Ark API Key>
TAVILY_API_KEY=<Tavily API Key>
```

| 变量 | 说明 | 必要性 |
| --- | --- | --- |
| `API_KEY` | 火山方舟 Ark 模型 API Key，用于主对话与文生图 | 必填 |
| `TAVILY_API_KEY` | Tavily 联网搜索 Key，知识库未命中时兜底 | 可选（不需联网可留空） |

> ⚠️ `.env` 已加入 `.gitignore`，不会上传仓库，密钥仅存在于目标机本地。

### 步骤 6：准备知识库（可选，按需）

需要本地知识库问答时，编辑 `chroma.py` 中的 `file_list`，替换为业务文档路径（支持 `.pdf` / `.txt`），然后运行入库：

```bash
python chroma.py
```

向量数据持久化到 `./chroma_db` 目录。文档变更后重跑即可增量更新，已删除文件对应的切片会被自动清理。

### 步骤 7：启动服务

需两个终端（或后台运行），按顺序启动：先起工具服务，再起主程序。

```bash
# 终端 1：启动工具服务（监听 127.0.0.1:8000）
python tool_server.py

# 终端 2：启动主程序
python agent.py
```

### 步骤 8：验证运行

```bash
# 验证工具服务可达
curl -X POST http://127.0.0.1:8000/tools/web_search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 1}'
```

- 主程序启动后，输入一个知识库相关问题，观察是否正确召回并作答。
- 查看 `agent_run.log` 日志，确认工具调用链路正常。

## 5. 常见问题排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'xxx'` | 依赖未装或未激活虚拟环境 | 确认已激活 `(venv)` 后重跑 `pip install -r requirements.txt` |
| `未配置 TAVILY_API_KEY` | `.env` 未复制或未填 | 检查 `.env` 是否存在且变量名正确 |
| 模型调用鉴权失败 | `API_KEY` 无效 | 核对火山方舟控制台 Key，确认账户有额度 |
| 端口被占用 | 8000 端口已有进程 | 结束占用进程，或修改 `tool_server.py` 中的 `port` |
| 程序读不到 `.env` | 启动目录不对 | 在包含 `.env` 的项目根目录下启动 |
| 检索不到知识库内容 | 未执行入库 / 文档格式不符 | 完成步骤 6，确认文档为 `.pdf` / `.txt` 且路径正确 |

## 6. 注意事项

- 模型服务地址（`base_url`）与模型名硬编码在 `agent.py` 中（火山方舟 Ark）。切换到自研 / 其他模型服务时，需同步修改 `agent.py` 内的 `base_url` 与模型名。
- 保持环境可复现：本地新增依赖后，用 `pip freeze > requirements.txt` 更新清单。