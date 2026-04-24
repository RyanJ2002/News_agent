"""
雙 Agent 資訊整理機器人 (Tavily + arXiv + Groq 版)
- Agent 1: 科技新聞 (Tavily 搜尋 + Groq 整理)
- Agent 2: arXiv AI 論文 (arXiv 官方 API + Groq 整理)
- 結果透過 Discord Webhook 傳送

取得免費 API Key:
  Groq  : https://console.groq.com
  Tavily: https://tavily.com
"""

import os
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

GROQ_API_KEY        = os.environ.get("GROQ_API_KEY", "")
TAVILY_API_KEY      = os.environ.get("TAVILY_API_KEY", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

NEWS_COUNT  = 8
PAPER_COUNT = 8
MODEL       = "llama-3.3-70b-versatile"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ── Groq ─────────────────────────────────────────────────────

def call_groq(system_prompt: str, user_prompt: str) -> str:
    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "temperature": 0.3,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API 錯誤 {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"無法解析 Groq 回應: {data}") from e


def parse_json_from_text(text: str) -> list:
    text = re.sub(r"```json|```", "", text).strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError(f"無法解析 JSON，回應: {text[:400]}")
    return json.loads(match.group(0))


# ── Tavily 搜尋 ──────────────────────────────────────────────

def tavily_search(query: str, max_results: int = 10) -> list[dict]:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Tavily API 錯誤 {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("results", [])


# ── arXiv 官方 API ───────────────────────────────────────────

def arxiv_search(query: str, max_results: int = 20) -> list[dict]:
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    resp = requests.get(
        f"https://export.arxiv.org/api/query?{params}",
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"arXiv API 錯誤 {resp.status_code}")

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title    = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
        summary  = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
        authors  = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        link     = entry.findtext("atom:id", "", ns).strip()
        arxiv_id = link.split("/abs/")[-1] if "/abs/" in link else ""
        papers.append({
            "title":    title,
            "summary":  summary[:600],
            "authors":  authors,
            "arxiv_id": arxiv_id,
        })
    return papers


# ── Agent 1：科技新聞 ─────────────────────────────────────────

def run_news_agent() -> list[dict]:
    print("🔍 [科技新聞 Agent] Step 1: Tavily 搜尋中...")
    today = datetime.now().strftime("%Y-%m-%d")
    raw = tavily_search(f"tech news AI semiconductor {today}", max_results=15)
    print(f"   Tavily 取得 {len(raw)} 筆原始結果")

    search_text = "\n\n".join([
        f"標題: {r.get('title','')}\n來源: {r.get('url','')}\n內容: {r.get('content','')[:300]}"
        for r in raw
    ])

    print("🔍 [科技新聞 Agent] Step 2: Groq 整理中...")
    system_prompt = f"""你是科技新聞整理 Agent。根據以下搜尋結果整理成 JSON 陣列。
每筆包含：
- title: 新聞標題（繁體中文）
- source: 來源網站名稱（英文）
- summary: 3句以內摘要（繁體中文）
- tags: 從 ["AI","半導體","科技公司","產品","政策","其他"] 選1-2個
- url: 原文連結

只回傳 JSON 陣列，不要任何其他文字或 markdown。共 {NEWS_COUNT} 則。"""

    user_prompt = f"今天是 {datetime.now().strftime('%Y年%m月%d日')}。\n\n搜尋結果：\n{search_text}"

    text = call_groq(system_prompt, user_prompt)
    news = parse_json_from_text(text)
    print(f"✅ [科技新聞 Agent] 完成，取得 {len(news)} 則")
    return news


# ── Agent 2：arXiv 論文 ───────────────────────────────────────

def run_arxiv_agent() -> list[dict]:
    print("🔬 [arXiv Agent] Step 1: arXiv 官方 API 搜尋中...")
    raw_papers = arxiv_search(
        "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV",
        max_results=20,
    )
    print(f"   arXiv 取得 {len(raw_papers)} 篇原始論文")

    papers_text = "\n\n".join([
        f"標題: {p['title']}\n"
        f"作者: {', '.join(p['authors'][:3])}{' et al.' if len(p['authors']) > 3 else ''}\n"
        f"arXiv ID: {p['arxiv_id']}\n"
        f"摘要: {p['summary'][:400]}"
        for p in raw_papers
    ])

    print("🔬 [arXiv Agent] Step 2: Groq 整理中...")
    system_prompt = f"""你是 arXiv AI 論文整理 Agent。從以下論文中選出最值得關注的，整理成 JSON 陣列。
每筆包含：
- title: 英文原標題
- authors: 作者（最多3人，其餘用 et al.）
- summary: 2-3句說明論文貢獻（繁體中文）
- tags: 從 ["LLM","Vision","RL","Agent","Multimodal","Safety","Reasoning","Other"] 選1-2個
- arxiv_id: arXiv ID（從原資料複製，不要修改）

只回傳 JSON 陣列，不要任何其他文字或 markdown。選出最重要的 {PAPER_COUNT} 篇。"""

    user_prompt = f"今天是 {datetime.now().strftime('%Y年%m月%d日')}。\n\n最新論文列表：\n{papers_text}"

    text = call_groq(system_prompt, user_prompt)
    papers = parse_json_from_text(text)
    print(f"✅ [arXiv Agent] 完成，取得 {len(papers)} 篇")
    return papers


# ── Discord ──────────────────────────────────────────────────

def send_to_discord(payload: dict) -> bool:
    resp = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        print(f"⚠️  Discord 錯誤: {resp.status_code} - {resp.text[:200]}")
        return False
    return True


def build_news_embeds(news_list: list[dict]) -> list[dict]:
    TAG_COLORS = {
        "AI": 0x3B82F6, "半導體": 0x8B5CF6, "科技公司": 0x10B981,
        "產品": 0xF59E0B, "政策": 0xEF4444, "其他": 0x6B7280,
    }
    embeds = []
    for item in news_list:
        tags  = item.get("tags", [])
        color = TAG_COLORS.get(tags[0] if tags else "其他", 0x6B7280)
        embed = {
            "title":       item.get("title", "無標題")[:256],
            "description": item.get("summary", "")[:1024],
            "color":       color,
            "fields": [
                {"name": "來源", "value": item.get("source", "未知")[:256], "inline": True},
                {"name": "標籤", "value": "  ".join(f"`{t}`" for t in tags) or "`其他`", "inline": True},
            ],
        }
        url = item.get("url", "")
        if url and url.startswith("http"):
            embed["url"] = url
        embeds.append(embed)
    return embeds


def build_paper_embeds(paper_list: list[dict]) -> list[dict]:
    TAG_COLORS = {
        "LLM": 0x6366F1, "Vision": 0x14B8A6, "RL": 0xF97316,
        "Agent": 0x8B5CF6, "Multimodal": 0xEC4899, "Safety": 0xEF4444,
        "Reasoning": 0x3B82F6, "Other": 0x6B7280,
    }
    embeds = []
    for item in paper_list:
        tags     = item.get("tags", [])
        color    = TAG_COLORS.get(tags[0] if tags else "Other", 0x6B7280)
        arxiv_id = item.get("arxiv_id", "")
        embed = {
            "title":       item.get("title", "No title")[:256],
            "description": item.get("summary", "")[:1024],
            "color":       color,
            "fields": [
                {"name": "作者", "value": item.get("authors", "Unknown")[:256], "inline": True},
                {"name": "領域", "value": "  ".join(f"`{t}`" for t in tags) or "`Other`", "inline": True},
            ],
        }
        if arxiv_id:
            embed["url"] = f"https://arxiv.org/abs/{arxiv_id}"
            embed["fields"].append({"name": "arXiv", "value": f"`{arxiv_id}`", "inline": True})
        embeds.append(embed)
    return embeds


def send_news_report(news_list: list[dict]):
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    send_to_discord({"embeds": [{
        "title":       "📡  今日科技新聞摘要",
        "description": f"由 **科技新聞 Agent** 整理，共 {len(news_list)} 則\n🕐 {now_str}",
        "color":       0x1D4ED8,
        "footer":      {"text": "Tavily Search + Groq Llama 3.3 70B"},
    }]})
    time.sleep(0.5)
    embeds = build_news_embeds(news_list)
    for i in range(0, len(embeds), 10):
        send_to_discord({"embeds": embeds[i:i+10]})
        time.sleep(0.5)


def send_papers_report(paper_list: list[dict]):
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    send_to_discord({"embeds": [{
        "title":       "🔬  arXiv 最新 AI 論文",
        "description": f"由 **arXiv Agent** 整理，共 {len(paper_list)} 篇\n🕐 {now_str}",
        "color":       0x7C3AED,
        "footer":      {"text": "arXiv Official API + Groq Llama 3.3 70B"},
    }]})
    time.sleep(0.5)
    embeds = build_paper_embeds(paper_list)
    for i in range(0, len(embeds), 10):
        send_to_discord({"embeds": embeds[i:i+10]})
        time.sleep(0.5)


# ── 主程式 ────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("🚀  雙 Agent 資訊整理機器人啟動")
    print(f"📅  {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print("=" * 50)

    missing = []
    if not GROQ_API_KEY:        missing.append("GROQ_API_KEY")
    if not TAVILY_API_KEY:      missing.append("TAVILY_API_KEY")
    if not DISCORD_WEBHOOK_URL: missing.append("DISCORD_WEBHOOK_URL")
    if missing:
        print(f"❌  缺少環境變數: {', '.join(missing)}")
        return

    news_result   = None
    papers_result = None
    errors        = []

    # 兩個 Agent 並行執行（Groq 額度充裕，不需要等待）
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_news   = executor.submit(run_news_agent)
        future_papers = executor.submit(run_arxiv_agent)
        futures = {future_news: "news", future_papers: "papers"}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if name == "news":
                    news_result = result
                else:
                    papers_result = result
            except Exception as e:
                errors.append(f"[{name}] {e}")
                print(f"⚠️  Agent 錯誤 ({name}): {e}")

    print("\n📤  傳送到 Discord...")

    if news_result:
        send_news_report(news_result)
        print(f"✅  科技新聞已傳送（{len(news_result)} 則）")

    if papers_result:
        send_papers_report(papers_result)
        print(f"✅  arXiv 論文已傳送（{len(papers_result)} 篇）")

    if errors:
        send_to_discord({"embeds": [{
            "title":       "⚠️  部分 Agent 執行失敗",
            "description": "\n".join(errors)[:1024],
            "color":       0xEF4444,
        }]})

    print("\n🎉  執行完畢！")


if __name__ == "__main__":
    main()
