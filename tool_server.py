# tool_server.py
# pip install fastapi uvicorn httpx beautifulsoup4 python-dotenv
import os
import socket
import ipaddress
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

app = FastAPI()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TIMEOUT = 15.0

# ========== SSRF 防护：DNS 解析真实 IP + 网段校验 ==========
def _is_internal_ip(ip_str: str) -> bool:      #该函数返回TRUE为危险地址
    """判断一个 IP 是否是回环 / 私有内网 / 链路本地（云元数据）地址。"""
    try:
        ip = ipaddress.ip_address(ip_str)   #格式正确返回flase
    except ValueError:
        return True  # 解析失败，按危险处理
    return (
        ip.is_loopback        # 127.0.0.0/8   本地回环
        or ip.is_private      # 10/8, 172.16/12, 192.168/16 等   内网
        or ip.is_link_local   # 169.254.0.0/16（含 169.254.169.254）  元数据网
        or ip.is_multicast    #组播地址
        or ip.is_reserved     #互联网保留地址，不能正常访问公网
    )


def is_safe_url(url: str) -> bool:
    """
    校验 URL 是否安全：
    1. 解析域名 -> 拿到全部真实 IP（防 DNS 绕过）
    2. 任意一个 IP 是内网/回环/链路本地地址，直接拒绝
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        return False
    # 只允许 http/https
    if parsed.scheme not in ("http", "https"):
        return False
    # 如果 host 本身就是 IP，不需要 DNS 解析
    try:
        ipaddress.ip_address(host)           #host本身就是地址而非域名
        return not _is_internal_ip(host)     #不是危险地址:false, 就return not false,反之
    except ValueError:
        pass
    # 域名：DNS 解析拿全部 IP
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # DNS 解析失败，拒绝
    ips = {info[4][0] for info in addr_infos}
    if not ips:
        return False
    # 只要任意一个 IP 是内网地址，就拒绝（防 DNS 轮询混淆）
    for ip in ips:
        if _is_internal_ip(ip):
            return False
    return True


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class FetchRequest(BaseModel):
    url: str


@app.post("/tools/web_search")
def web_search(req: SearchRequest):
    """Tavily 联网搜索"""
    if not TAVILY_API_KEY:
        return {"error": "未配置 TAVILY_API_KEY"}

    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": req.query,
                "max_results": req.max_results,
                "search_depth": "basic",
            },
        )
        r.raise_for_status()
        data = r.json()  #此时是r对应的取得的结果 json不是上面那个json

    result_list = []

    for item in data.get("results"):
    # 每次循环，新建一个字典，追加进列表
     new_dict = {
        "title": item.get("title"),
        "content": item.get("content"),
        "url": item.get("url"),
        "score": item.get("score")
    }
    result_list.append(new_dict)

    return result_list


@app.post("/tools/web_fetch")
def web_fetch(req: FetchRequest):
    """网页正文抓取，DNS 解析真实 IP 做 SSRF 防护。"""
    if not is_safe_url(req.url):
        return {"error": "禁止访问内网/本地/云元数据地址，URL 不安全"}

    headers = {   #告诉网站是哪个地址在访问
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36"
    }
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            r = client.get(req.url, headers=headers)  #网站同时也会回复对应headers
            r.raise_for_status()
    except Exception as e:
        return {"error": f"抓取失败: {str(e)}"}

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return {"url": req.url, "text": text[:6000]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tool_server:app", host="127.0.0.1", port=8000)