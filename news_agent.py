"""
雙 Agent 資訊整理機器人 (Google Gemini 版)
- Agent 1: 科技新聞 (Gemini + Google Search Grounding)
- Agent 2: arXiv AI 最新論文 (Gemini + Google Search Grounding)
- 結果透過 Discord Webhook 傳送
"""

import os
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ============================================================
# 設定區（從環境變數讀取，不要直接寫在這裡）
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

NEWS_COUNT = 8
PAPER_COUNT = 8
MODEL = "gemini-2.0-flash"
# ============================================================

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def call_gemini(system_prompt: str, user_prompt: str) -> str:
    """呼叫 Gemini API，啟用 Google Search Grounding"""
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }

    resp = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API 錯誤 {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"無法解析 Gemini 回應: {data}") from e


def parse_json_from_text(text: str) -> list:
    """從文字中提取 JSON 陣列"""
    text = re.sub(r"```json|```", "", text).strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError(f"無法解析 JSON，回應內容: {text[:400]}")
    return json.loads(match.group(0))


def run_news_agent() -> list[dict]:
    """Agent 1: 搜尋最新科技新聞"""
    print("🔍 [科技新聞 Agent] 啟動中...")

    system_prompt = f"""你是一個科技新聞整理 Agent。請使用 Google Search 搜尋今日最新重要科技新聞。
回傳嚴格的 JSON 陣列，每筆包含：
- title: 新聞標題（繁體中文）
- source: 新聞來源（英文，例如 TechCrunch）
- summary: 3句以內摘要（繁體中文）
- tags: 從 ["AI","半導體","科技公司","產品","政策","其他"] 中選1-2個
- url: 原文連結（若有）

只回傳 JSON 陣列，不要任何其他文字或 markdown。共 {NEWS_COUNT} 則。"""

    user_prompt = f"今天是 {datetime.now().strftime('%Y年%m月%d日')}，請搜尋今日最重要科技新聞並整理成 JSON 陣列。"

    text = call_gemini(system_prompt, user_prompt)
    news = parse_json_from_text(text)
    print(f"✅ [科技新聞 Agent] 完成，取得 {len(news)} 則")
    return news


def run_arxiv_agent() -> list[dict]:
    """Agent 2: 搜尋 arXiv 最新 AI 論文"""
    print("🔬 [arXiv Agent] 啟動中...")

    system_prompt = f"""你是一個 arXiv AI 論文整理 Agent。請搜尋 arXiv 上最近發布的重要 AI/ML 論文。
回傳嚴格的 JSON 陣列，每筆包含：
- title: 英文原標題
- authors: 作者（最多3人，其餘用 et al.）
- summary: 2-3句說明貢獻（繁體中文）
- tags: 從 ["LLM","Vision","RL","Agent","Multimodal","Safety","Reasoning","Other"] 中選1-2個
- arxiv_id: arXiv ID，例如 2504.12345

只回傳 JSON 陣列，不要任何其他文字或 markdown。共 {PAPER_COUNT} 篇。"""

    user_prompt = f"今天是 {datetime.now().strftime('%Y年%m月%d日')}，請搜尋近期 arXiv 最值得關注的 AI 論文並整理成 JSON 陣列。"

    text = call_gemini(system_prompt, user_prompt)
    papers = parse_json_from_text(text)
    print(f"✅ [arXiv Agent] 完成，取得 {len(papers)} 篇")
    return papers


def send_to_discord(payload: dict) -> bool:
    """傳送訊息到 Discord Webhook"""
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
        tags = item.get("tags", [])
        color = TAG_COLORS.get(tags[0] if tags else "其他", 0x6B7280)
        tag_str = "  ".join(f"`{t}`" for t in tags)
        embed = {
            "title": item.get("title", "無標題")[:256],
            "description": item.get("summary", "")[:1024],
            "color": color,
            "fields": [
                {"name": "來源", "value": item.get("source", "未知")[:256], "inline": True},
                {"name": "標籤", "value": tag_str or "`其他`", "inline": True},
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
        tags = item.get("tags", [])
        color = TAG_COLORS.get(tags[0] if tags else "Other", 0x6B7280)
        tag_str = "  ".join(f"`{t}`" for t in tags)
        arxiv_id = item.get("arxiv_id", "")
        embed = {
            "title": item.get("title", "No title")[:256],
            "description": item.get("summary", "")[:1024],
            "color": color,
            "fields": [
                {"name": "作者", "value": item.get("authors", "Unknown")[:256], "inline": True},
                {"name": "領域", "value": tag_str or "`Other`", "inline": True},
            ],
        }
        if arxiv_id:
            embed["url"] = f"https://arxiv.org/abs/{arxiv_id}"
            embed["fields"].append({"name": "arXiv", "value": f"`{arxiv_id}`", "inline": True})
        embeds.append(embed)
    return embeds


def send_news_report(news_list: list[dict]):
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    send_to_discord({
        "embeds": [{
            "title": "📡  今日科技新聞摘要",
            "description": f"由 **科技新聞 Agent** 整理，共 {len(news_list)} 則\n🕐 {now_str}",
            "color": 0x1D4ED8,
            "footer": {"text": "Powered by Gemini 2.0 Flash + Google Search"},
        }]
    })
    time.sleep(0.5)
    embeds = build_news_embeds(news_list)
    for i in range(0, len(embeds), 10):
        send_to_discord({"embeds": embeds[i:i+10]})
        time.sleep(0.5)


def send_papers_report(paper_list: list[dict]):
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    send_to_discord({
        "embeds": [{
            "title": "🔬  arXiv 最新 AI 論文",
            "description": f"由 **arXiv Agent** 整理，共 {len(paper_list)} 篇\n🕐 {now_str}",
            "color": 0x7C3AED,
            "footer": {"text": "Powered by Gemini 2.0 Flash + Google Search"},
        }]
    })
    time.sleep(0.5)
    embeds = build_paper_embeds(paper_list)
    for i in range(0, len(embeds), 10):
        send_to_discord({"embeds": embeds[i:i+10]})
        time.sleep(0.5)


def main():
    print("=" * 50)
    print("🚀  雙 Agent 資訊整理機器人啟動")
    print(f"📅  {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print("=" * 50)

    if not GEMINI_API_KEY:
        print("❌  找不到 GEMINI_API_KEY，請設定環境變數或 GitHub Secret")
        return
    if not DISCORD_WEBHOOK_URL:
        print("❌  找不到 DISCORD_WEBHOOK_URL，請設定環境變數或 GitHub Secret")
        return

    news_result = None
    papers_result = None
    errors = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_news = executor.submit(run_news_agent)
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
        send_to_discord({
            "embeds": [{
                "title": "⚠️  部分 Agent 執行失敗",
                "description": "\n".join(errors)[:1024],
                "color": 0xEF4444,
            }]
        })

    print("\n🎉  執行完畢！")


if __name__ == "__main__":
    main()
