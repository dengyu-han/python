from openai import OpenAI
from datetime import datetime
import json
import chromadb
import logging
import httpx
import base64
from dotenv import load_dotenv
import os
import hashlib

load_dotenv()

import openai
# ========== 日志配置 ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("agent_run.log", encoding="UTF-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="jihe")
mem_col = chroma_client.get_or_create_collection(name= "long_term_memory" )

def image_to_base64(image_path:str) ->str:
   """读取本地图片，转为火山方舟可用的带前缀base64字符串"""
   with open(image_path, "rb")as f:
    image_info = f.read() #二进制读取
    base64_text = base64.b64encode(image_info).decode("utf-8")
    return f"data:image/jpeg;base64,{base64_text}"
   
#-------短记忆功能区--------
def _summarize(old_history, client:openai):
    """调用LLM萃取摘要,LLM无效时,利用文本拼接兜底"""
    conversation = ""
    for msg in old_history:
        role = msg.get("role")
        content = msg.get("content") or ""
        conversation += f"{role} + {content}"

    prompt = f"""请将老历史的记录萃取成带有精华的摘要,删除多余的废话,180字,不要编造虚伪的信息进入，
    对应的历史记录:{conversation},直接输出摘要内容,不要多余描述"""

    try:
        resp = client.chat.completions.create(
            model="Doubao-Seed-Evolving",
            messages=[{"role": "system", "content": "你是摘要精选助手,只输出精简摘要"},
                      {"role": "user", "content": prompt}],
            temperature=0.1,
            timeout=10
        )
        res = resp.choices[0].message.content.strip()
        return {"role": "assistant", "content": res}
    except Exception as e:
        print(f"调用LLM无效:{e} 保底使用文字拼接")
        content = "\n".join(m.get("content")[:60] for m in old_history if m.get("content"))
        return {"role": "assistant", "content": content[:180]}

MAX_MESSAGE = 7

def build_short_memory(history):
    """超窗时把最旧的簇原地替换成一条摘要,不返回新列表,外部chat_history同步生效"""
    if len(history) <= MAX_MESSAGE:
        return history

    keep = MAX_MESSAGE - 1   #保留一位存摘要,其余为最新历史记录
    latest_msg = history[-keep:]
    old = history[:len(history) - keep]
    if old:
        latest_msg.insert(0, _summarize(old,client))
    history[:] = latest_msg
    

#======长期记忆区域======
def save_long_memory(user_query:str, ai_reply:str):
    """将一轮对话的历史存入向量库中"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"[ {now_str} ] user:{user_query}/AI:{ai_reply}"
    mem_id = "id" + hashlib.md5(content.encode()).hexdigest()[:12]

    mem_col.upsert(    #去重
        documents=[content],
        ids=[mem_id],
        metadatas=[{"time": now_str}]
    )
    clean_expired_memory(30)
    print("完成记忆入库")

def recall_long_memory(query):
    try:
        res = mem_col.query(
            query_texts=[query],
            n_results=3,
            include=["documents"]
        )
        return res["documents"][0]
    except Exception as e:
        print(f"检索异常:{e}")
        return []

def build_long_memory_context(query):
    res = recall_long_memory(query)
    if not res:
        return ""
    block = "以下是检索出的相关历史记忆,可供参考"
    return block + "\n".join(f"{r}" for r in res)


def clean_expired_memory(days=30):
    """清理超过指定天数的长期记忆,防止向量库无限膨胀"""
    try:
        all_data = mem_col.get(include=["metadatas"])
        ids = all_data["ids"]
        metas = all_data["metadatas"]
        if not ids:
            return 0
        now = datetime.now()
        expired = []
        for mid, meta in zip(ids, metas):
            t_str = (meta or {}).get("time")
            if not t_str:
                continue
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    t = datetime.strptime(t_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                continue
            if (now - t).days > days:
                expired.append(mid)
        if expired:
            mem_col.delete(ids=expired)
        return len(expired)
    except Exception as e:
        logger.error(f"清理过期记忆失败:{e}")
        return 0

       
# ========== 工具函数 ==========
def get_current_time():
    logger.info("调用工具 get_current_time")
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
def calculate_add(a, b):
    logger.info(f"调用工具 calculate_add a={a}, b={b}")
    return a + b
# RAG函数：移除return_distances，兼容旧版chromadb
def rag(query: str):
    logger.info(f"进入检索功能，查询：{query}")
    result = collection.query(
        query_texts=[query],
        n_results=2
    )
    docs = result["documents"][0]
    logger.info(f"检索得到片段: {docs}")
    content = "\n".join(docs)
    return content

def image_generate(prompt:str,  save_path:str,image_path:str =None):
    """ 根据关键词以及参考图生成对应图片 
    prompt:图片生成提示词
    save_path:保存图片地址
    image_path:传入的参考图地址，如果没有参考图就是文生图
    """
    image_list = []
    if image_path is not None:
     image_base64 = image_to_base64(image_path)
     image_list.append(image_base64)

    extra_body = {}   #火山方舟需要
    if image_list:
        extra_body["image"] = image_list

    image_client = OpenAI(
        api_key= os.getenv("API_KEY"),
        base_url="https://ark.cn-beijing.volces.com/api/v3"
    )

    res = image_client.images.generate(
        prompt= prompt,
        model="doubao-seedream-5-0-lite-260128",
        response_format= "url",
        extra_body=extra_body or None,
    )
    url = res.data[0].url

    image_bytes = httpx.get(url).content
    with open(save_path,"wb")as f:
        f.write(image_bytes)

    return {"success": True, "path": save_path}


def web_search(query: str, max_results:int=5):
    logger.info(f"调用联网搜索工具 query={query}")
    with httpx.Client(timeout=20) as client:
        resp = client.post("http://127.0.0.1:8000/tools/web_search", json={
            "query": query,
            "max_results": max_results
        })
    return resp.text

def web_fetch(url: str):
    logger.info(f"调用网页抓取工具 url={url}")
    with httpx.Client(timeout=20) as client:
        resp = client.post("http://127.0.0.1:8000/tools/web_fetch", json={
            "url": url
        })
    return resp.text
# ========== 工具注册 & 工具描述【已经优化！】 ==========
tools_registry = {
    "get_current_time": get_current_time,
    "calculate_add": calculate_add,
    "rag": rag,
    "web_search": web_search,
    "web_fetch": web_fetch,
    "image_generate": image_generate
}
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "仅当用户明确询问当前时间、日期、星期时调用。用户问产品、配置、文档、数学以外问题，禁止调用此工具！",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_add",
            "description": "仅用户明确要求两个数字相加求和时调用。其他任何场景，禁止调用！",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "第一个数字"},
                    "b": {"type": "number", "description": "第二个数字"}
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag",
            "description": "检索本地文档知识库。**优先调用 rag 检索本地文档知识库。无论你主观猜测本地是否存在相关内容，都先调用 rag。拿到 rag 返回结果后，再评估是否需要调用 web_search。**。用户询问时间、加法计算，禁止调用rag。检索不到信息直接使用你的知识回答，禁止重复调用rag。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询语句"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索。仅当问题需要最新信息、实时信息、本地知识库没有答案时调用。优先使用rag查本地文档，本地文档没有再调用web_search。不要无意义搜索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "返回结果数量，默认5"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "抓取指定网页的正文内容。必须先调用web_search拿到url之后，才可以调用web_fetch精读网页。不允许直接编造url。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的网页地址"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function":{
            "name": "image_generate",
            "description": "根据关键词和参考图生成对应图片,如果没有参考图就是文生图，必须拿到对应url中的图片内容，不能随意编造",
            "parameters":{
                "type":"object",
                "properties":{
                    "prompt":{"type": "string", "description": "生成图片的关键词"},
                    "save_path":{"type": "string", "description" : "保存生成图片的地址"},
                    "image_path": {"type": "string", "description": "传入的参考图地址"}
                },
                "required": ["prompt", "save_path"]
            }
        }
    }
]
# ========== 客户端与系统提示词【优化】 ==========
client = OpenAI(
    api_key= os.getenv("API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/coding/v3"
)
SYSTEM_AGENT_DECISION = {
    "role": "system",
    "content": """你是ReAct Agent助手，严格遵守下面工具调用规则：
1. get_current_time：仅用户明确问时间、日期、星期才调用，其余场景禁止调用。
2. calculate_add：仅用户做两个数字加法才调用，其余场景禁止调用。
3. rag：只有答案存在本地文档才调用。本地文档不存在的内容，不要调用rag。
4. web_search：**优先查本地rag，本地文档没有答案，且需要最新/实时信息，才调用联网搜索**。不要重复搜索相同query。
5. web_fetch：必须先调用web_search拿到网页url，才可以调用，用来精读网页原文。不能编造url。

 如果用户问题不需要调用任何工具，直接输出最终回答，不要调用任何工具。
不要强行调用工具，禁止无理由触发工具。
"""
}

chat_history = []
# ========== Agent核心逻辑==========
def get_reply(user_msg, history):
    logger.info(f"初始化完成，用户问题:{user_msg}")
    max_count = 5
    Loop_count = 0
    history.append({"role": "user", "content": user_msg})

    lmc = build_long_memory_context(user_msg)
    sys_msg = SYSTEM_AGENT_DECISION
    if lmc:
        # 把召回的长期记忆追加到system提示词
        sys_msg = {
            "role": "system",
            "content": sys_msg["content"] + "\n" + lmc
        }

    while Loop_count < max_count:
        Loop_count += 1
        # 短期记忆:每一轮LLM请求前压缩会话历史(原地修改)
        build_short_memory(history)
        logger.info(f"即将开启第:{Loop_count}轮LLM调用，判断是否需要工具")
        resp = client.chat.completions.create(
            model="Doubao-Seed-Evolving",
            messages=[sys_msg] + history,
            tools=tools,
            tool_choice="auto"
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            logger.info("大模型无需调用工具，直接返回模型回答，不再额外请求LLM")
            AI_reply = msg.content
            history.append({"role": "assistant", "content": AI_reply})
            save_long_memory(user_msg, AI_reply)
            return AI_reply
        
        # 执行工具调用分支
        logger.info(f"需要工具,本轮while循环中使用:{len(msg.tool_calls)}个工具")
        history.append(msg.model_dump())
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
                logger.info(f"执行工具 {func_name}, args={args}")
                target_func = tools_registry[func_name]
                res = target_func(**args)
            except Exception as e:
                logger.error(f"工具调用异常:{e}")
                res = f"tools call error:{e}"
            history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(res)
            })
    # 达到最大循环次数兜底
    logger.warning(f"达到最大循环次数{max_count}，强制收尾")
    final_resp = client.chat.completions.create(
        model="Doubao-Seed-Evolving",
        messages=[sys_msg] + history 
    )
    AI_reply = final_resp.choices[0].message.content
    logger.info(f"【兜底模型输出】>>> {AI_reply} <<<")
    history.append({"role": "assistant", "content": AI_reply})
    save_long_memory(user_msg, AI_reply)
    return AI_reply

# ========== 主循环 ==========
if __name__ == "__main__":
    cleaned = clean_expired_memory(30)
    if cleaned:
        logger.info(f"启动时已清理 {cleaned} 条过期长期记忆")
    while True:
        user_input = input("You:")
        if user_input == "exit":
            logger.info("agent:bye")
            break
        elif user_input == "history":
            logger.info(f"get the history:{chat_history}")
            continue
        elif user_input == "clear":
            chat_history.clear()
            logger.info("history cleared")
            continue
        reply = get_reply(user_input, chat_history)
        print(f"agent:{reply}")