import os
import re
import json
import html
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ==============================
# 配置
# ==============================

SOURCE_REPO = "DuckBurnIncense/xin-wen-lian-bo"
SOURCE_BRANCH = "master"

# DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()

# # 可以在这里更换模型
# AI_MODEL = os.environ.get("AI_MODEL", "deepseek-v4-pro")

# AI_API_URL = "https://api.deepseek.com/chat/completions"


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

AI_MODEL = os.environ.get(
    "AI_MODEL",
    "openrouter/free"
)

AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"



OUTPUT_DIR = "site"
FEED_FILE = os.path.join(OUTPUT_DIR, "feed.xml")
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.html")

MAX_HISTORY = 30


# ==============================
# 网络请求
# ==============================

def http_get(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 news-lianbo-ai-rss"
        }
    )

    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def github_api_get(url):
    req = Request(
        url,
        headers={
            "User-Agent": "news-lianbo-ai-rss",
            "Accept": "application/vnd.github+json"
        }
    )

    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# ==============================
# 找到最新一期新闻联播
# ==============================

def find_latest_news_file():
    print("正在查找最新一期《新闻联播》……")

    tree_url = (
        f"https://api.github.com/repos/"
        f"{SOURCE_REPO}/git/trees/{SOURCE_BRANCH}?recursive=1"
    )

    data = github_api_get(tree_url)

    candidates = []

    for item in data.get("tree", []):
        path = item.get("path", "")

        # 匹配 news/20260901.md 这种文件
        match = re.fullmatch(r"news/(\d{8})\.md", path)

        if match:
            date_str = match.group(1)
            candidates.append((date_str, path))

    if not candidates:
        raise RuntimeError("没有找到新闻联播 Markdown 文件")

    candidates.sort(reverse=True)

    latest_date, latest_path = candidates[0]

    print(f"找到最新一期：{latest_date}")
    print(f"文件：{latest_path}")

    return latest_date, latest_path


# ==============================
# 下载新闻联播原文
# ==============================

def download_news(date_str):
    raw_url = (
        f"https://raw.githubusercontent.com/"
        f"{SOURCE_REPO}/{SOURCE_BRANCH}/news/{date_str}.md"
    )

    print(f"正在下载：{raw_url}")

    text = http_get(raw_url)

    if not text.strip():
        raise RuntimeError("下载到的新闻联播内容为空")

    return text, raw_url


# ==============================
# 调用 api
# ==============================

def call_ai(news_text, date_str):
    # if not DEEPSEEK_API_KEY:
    #     raise RuntimeError(
    #         "没有找到 DEEPSEEK_API_KEY，请检查 GitHub Secrets"
    #     )
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "没有找到 OPENROUTER_API_KEY，请检查 GitHub Secrets"
        )
    system_prompt = """
你是一名专业的新闻编辑。

你的任务是阅读当天完整的《新闻联播》文字稿，
整理成适合普通人快速阅读的“每日新闻重点笔记”。

要求：

1. 从整期节目中筛选最值得关注的 5～8 条新闻。
2. 按重要性排序，而不是机械按照节目播出顺序。
3. 每条新闻都回答：
   - 发生了什么？
   - 为什么值得关注？
4. 语言简洁、客观、清楚。
5. 不要添加新闻原文没有的信息。
6. 不要虚构数字、人物、事件或因果关系。
7. 不要把自己的推测写成事实。
8. 对经济、科技、国际、民生等重要信息注意覆盖。
9. 对“国内联播快讯”“国际联播快讯”可以合并成若干条，不必全部展开。
10. 最后写一个“今日一句话总结”。

请使用以下格式：

# 今日新闻联播重点

## 1. 新闻标题

**发生了什么：**
用 2～4 句话说明。

**为什么值得关注：**
用 1～3 句话说明。

## 2. 新闻标题

**发生了什么：**
……

**为什么值得关注：**
……

……

# 今日一句话总结

……

不要输出与任务无关的内容。
"""

    user_prompt = f"""
今天是 {date_str}。

以下是今天的《新闻联播》完整文字稿：

--------------------
{news_text}
--------------------

请根据整期内容制作“今日新闻联播 AI 重点笔记”。
"""

    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt.strip()
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": 0.2,
        "stream": False
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = Request(
        AI_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            # "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/",
            "X-Title": "News Lianbo AI RSS",
            "User-Agent": "news-lianbo-ai-rss"
        },
        method="POST"
    )

    print("正在调用 DeepSeek AI……")

    try:
        with urlopen(req, timeout=180) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"DeepSeek API 调用失败：HTTP {e.code}\n{error_body}"
        )
    except URLError as e:
        raise RuntimeError(
            f"无法连接 DeepSeek API：{e}"
        )

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"DeepSeek 返回结果格式异常：{json.dumps(result, ensure_ascii=False)[:2000]}"
        )

    if not content.strip():
        raise RuntimeError("AI 返回了空内容")

    return content.strip()


# ==============================
# Markdown → 简单 HTML
# ==============================

def markdown_to_html(text):
    lines = text.splitlines()

    result = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        escaped = html.escape(line)

        if escaped.startswith("### "):
            result.append(
                f"<h3>{escaped[4:]}</h3>"
            )
        elif escaped.startswith("## "):
            result.append(
                f"<h2>{escaped[3:]}</h2>"
            )
        elif escaped.startswith("# "):
            result.append(
                f"<h1>{escaped[2:]}</h1>"
            )
        elif escaped.startswith("**") and escaped.endswith("**"):
            result.append(
                f"<p><strong>{escaped[2:-2]}</strong></p>"
            )
        else:
            # 简单处理 **文字**
            escaped = re.sub(
                r"\*\*(.+?)\*\*",
                r"<strong>\1</strong>",
                escaped
            )

            result.append(
                f"<p>{escaped}</p>"
            )

    return "\n".join(result)


# ==============================
# RSS XML
# ==============================

def xml_escape(text):
    return html.escape(text, quote=True)


def make_rss_item(date_str, ai_summary, source_url):
    title = f"📺 {date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 新闻联播 AI 重点"

    description = f"""
<div>
{markdown_to_html(ai_summary)}

<hr>

<p>
<strong>原始文字稿：</strong>
<a href="{xml_escape(source_url)}">
查看央视新闻联播文字稿
</a>
</p>

<p>
来源项目：
<a href="https://github.com/DuckBurnIncense/xin-wen-lian-bo">
DuckBurnIncense/xin-wen-lian-bo
</a>
</p>
</div>
"""

    pub_date = datetime.strptime(
        date_str, "%Y%m%d"
    ).replace(
        hour=11,
        minute=0,
        second=0,
        tzinfo=timezone.utc
    ).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    return f"""
<item>
<title>{xml_escape(title)}</title>
<link>{xml_escape(source_url)}</link>
<guid isPermaLink="false">xin-wen-lian-bo-ai-{date_str}</guid>
<pubDate>{pub_date}</pubDate>
<description><![CDATA[
{description}
]]></description>
</item>
"""


# ==============================
# 生成 RSS
# ==============================

def update_rss(date_str, ai_summary, source_url):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    new_item = make_rss_item(
        date_str,
        ai_summary,
        source_url
    )

    existing_items = []

    if os.path.exists(FEED_FILE):
        with open(
            FEED_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            old_feed = f.read()

        matches = re.findall(
            r"<item>.*?</item>",
            old_feed,
            re.S
        )

        existing_items = matches

    # 避免重复插入同一天
    existing_items = [
        item
        for item in existing_items
        if f"xin-wen-lian-bo-ai-{date_str}" not in item
    ]

    all_items = [new_item] + existing_items
    all_items = all_items[:MAX_HISTORY]

    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "").split("/", 1)[-1]

    base_url = (
        f"https://{owner}.github.io/{repo}"
        if owner and repo
        else ""
    )

    feed_url = f"{base_url}/feed.xml"

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>📺 新闻联播 AI 重点</title>
<link>{xml_escape(base_url)}</link>
<description>央视《新闻联播》每日 AI 重点笔记</description>
<language>zh-CN</language>
<generator>news-lianbo-ai-rss</generator>
<ttl>1440</ttl>
{''.join(all_items)}
</channel>
</rss>
"""

    with open(
        FEED_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(rss)

    # 生成一个非常简单的首页
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>新闻联播 AI RSS</title>
<style>
body {{
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.7;
}}
.box {{
    background: #f5f5f5;
    padding: 16px;
    border-radius: 10px;
    word-break: break-all;
}}
code {{
    word-break: break-all;
}}
</style>
</head>
<body>
<h1>📺 新闻联播 AI 重点 RSS</h1>

<p>
这是一个自动生成的《新闻联播》AI 重点 RSS。
</p>

<h2>RSS 地址</h2>

<div class="box">
<a href="{xml_escape(feed_url)}">{xml_escape(feed_url)}</a>
</div>

<h2>说明</h2>

<p>
每天自动读取最新的《新闻联播》文字稿，
使用 AI 提炼最值得关注的新闻重点。
</p>

<p>
目前保留最近 {MAX_HISTORY} 期。
</p>
</body>
</html>
"""

    with open(
        INDEX_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(index_html)

    print(f"RSS 已生成：{FEED_FILE}")


# ==============================
# 主程序
# ==============================

def main():
    print("=" * 60)
    print("新闻联播 AI RSS")
    print("=" * 60)

    date_str, _ = find_latest_news_file()

    news_text, source_url = download_news(date_str)

    print(f"原文长度：{len(news_text)} 字符")

    ai_summary = call_ai(
        news_text,
        date_str
    )

    print("AI 总结生成完成。")
    print(ai_summary)

    update_rss(
        date_str,
        ai_summary,
        source_url
    )

    print("=" * 60)
    print("任务完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
