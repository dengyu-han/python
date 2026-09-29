from datetime import datetime
import os
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools.retriever import create_retriever_tool
from langchain_chroma import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from openai import OpenAI
import httpx
from langchain_openai import ChatOpenAI

load_dotenv()

@tool
def get_current_time():
    """获取当前系统时间，用户询问日期、时间的时候调用"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

@tool
def generate_picture(prompt:str, save_path:str, image_list=None):
    """
    根据提示词生成图片，可以传入参考图。
    :param prompt: 图片生成提示词
    :param save_path: 图片保存本地路径
    :param image_list: 参考图片base64数组，为空则纯文生图
    """
    if image_list is None:
        image_list = []
    extra_body = {}
    if image_list:
        # 火山方舟通过 extra_body.image 传参考图（URL / base64 数组）
        extra_body["image"] = image_list
    
    image_client = OpenAI(
        api_key=os.getenv("API_KEY"),
        base_url="https://ark.cn-beijing.volces.com/api/v3",
    )
    res = image_client.images.generate(
        prompt=prompt,
        model="doubao-seedream-5-0-lite-260128",
        response_format="url",
        extra_body=extra_body or None,
    )
    url  = res.data[0].url
    image_bytes = httpx.get(url).content
    with open(save_path,"wb") as f:
         f.write(image_bytes)
    return {"success" : True, "path" : save_path}

if __name__ == "__main__":
    embedding = FastEmbedEmbeddings(model_name="BAAI/bge-small-zh-v1.5")
    vector_db = Chroma(
        collection_name= "jihe",
        embedding_function=embedding,
        persist_directory="./langchain_chroma_db"
    )
    retriever = vector_db.as_retriever(search_kwargs={"k" : 3})
    rag_tool = create_retriever_tool(
        retriever,
        name="document search",
        description="当用户问题需要查询本地文档、知识库、文件资料时调用，返回相关文档片段。用于查找与问题相关的文件信息，每次返回最相关的3条文档片段。如果需要验证资料内容或找不到相关信息，不要编造，直接返回未找到。"
    )
    tools= [rag_tool, get_current_time, generate_picture]

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个智能助手，可以根据需求调用工具。回答问题优先使用本地文档检索，没有信息再使用其他工具，不要编造内容。\n规则：调用工具并获得结果后，必须立即基于结果给出最终回答，禁止重复调用同一个工具或无关工具；如果工具结果已足够回答问题，不要再次调用工具。"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    llm = ChatOpenAI(
        openai_api_key=os.getenv("API_KEY"),
        openai_api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
        model="ark-code-latest",
        temperature= 0
    )
    agent = create_openai_tools_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent = agent,
        tools = tools,
        max_iterations = 5,
        handle_parsing_errors =True,
        verbose = True
    )
    while True:
        user_input = input("You:")
        if user_input == "exit":
             print("bye,have a good day")
             break
        res = agent_executor.invoke({"input": user_input})
        print(f"Agent:{res}")
