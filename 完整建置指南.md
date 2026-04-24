# 完整建置指南：雙 Agent 每日資訊機器人

## 目錄結構（你的 repo 長這樣）

```
你的-repo/
├── news_agent.py                        # 主程式
├── .gitignore                           # 防止上傳金鑰
└── .github/
    └── workflows/
        └── daily_news.yml               # 自動排程設定
```

---

## STEP 1：取得 Gemini API Key（免費）

1. 用瀏覽器開啟 https://aistudio.google.com/apikey
2. 用 Google 帳號登入
3. 點擊右上角「**Create API key**」
4. 選「**Create API key in new project**」
5. 複製產生的 Key（格式像 `AIzaSyXXXXXXX`）
6. 先暫時貼到記事本備用

---

## STEP 2：取得 Discord Webhook URL

1. 打開 Discord，進入你想接收通知的**頻道**
2. 對頻道點右鍵 → **編輯頻道**
3. 左側選單點 **整合（Integrations）**
4. 點 **Webhooks** → **建立 Webhook**
5. 幫 Webhook 取個名字（例如：「AI 新聞機器人」）
6. 點「**複製 Webhook URL**」
7. URL 格式像 `https://discord.com/api/webhooks/1234567890/abcdefg...`
8. 貼到記事本備用

---

## STEP 3：建立 GitHub 帳號（已有可跳過）

1. 前往 https://github.com/signup
2. 填入 Email、密碼、使用者名稱
3. 驗證信箱

---

## STEP 4：建立 GitHub Repository

1. 登入 GitHub 後，點右上角「**+**」→「**New repository**」
2. 填寫：
   - Repository name：`daily-news-agent`（或任何名字）
   - 選 **Public** 或 **Private** 都可以（建議 Private）
   - 勾選「**Add a README file**」
3. 點「**Create repository**」

---

## STEP 5：上傳程式碼

### 方法 A：直接在 GitHub 網頁上傳（不需要 Git）

**上傳 `news_agent.py`：**
1. 在 repo 頁面點「**Add file**」→「**Upload files**」
2. 把 `news_agent.py` 拖進去
3. 點「**Commit changes**」

**建立 workflow 資料夾和檔案：**
1. 點「**Add file**」→「**Create new file**」
2. 在檔案名稱欄位輸入：`.github/workflows/daily_news.yml`
   （輸入 `/` 會自動建立資料夾）
3. 把 `daily_news.yml` 的內容貼進去
4. 點「**Commit changes**」

**建立 `.gitignore`：**
1. 同上，新增檔案名稱 `.gitignore`
2. 把 `.gitignore` 內容貼進去
3. Commit

### 方法 B：用 Git 指令（需要先安裝 Git）

```bash
# 複製你的 repo（把 your-username 換成你的 GitHub 名稱）
git clone https://github.com/your-username/daily-news-agent.git
cd daily-news-agent

# 複製本專案的三個檔案進去
# news_agent.py
# .gitignore
# .github/workflows/daily_news.yml

# 推上去
git add .
git commit -m "新增雙 Agent 機器人"
git push
```

---

## STEP 6：設定 GitHub Secrets（存放 API Key）

**這步驟非常重要！** 絕對不能把 API Key 直接寫在程式碼裡。

1. 在你的 repo 頁面，點上方的「**Settings**」
2. 左側選單找到「**Secrets and variables**」→「**Actions**」
3. 點「**New repository secret**」

**新增第一個 Secret：**
- Name：`GEMINI_API_KEY`
- Secret：貼上你的 Gemini API Key（`AIzaSyXXXXX`）
- 點「**Add secret**」

**新增第二個 Secret：**
- Name：`DISCORD_WEBHOOK_URL`
- Secret：貼上你的 Discord Webhook URL
- 點「**Add secret**」

設定完成後應該看到兩個 Secret 都在列表裡（值會被隱藏，這是正常的）。

---

## STEP 7：手動測試執行

不用等到明天早上，現在就可以測試：

1. 在 repo 頁面點上方的「**Actions**」
2. 左側點「**雙 Agent 每日資訊整理**」
3. 點右側「**Run workflow**」→「**Run workflow**」（綠色按鈕）
4. 等待約 30-60 秒
5. 看到綠色勾勾 ✅ 代表成功
6. 去 Discord 確認有收到訊息！

如果出現紅色 ✗，點進去可以看錯誤訊息。

---

## STEP 8：確認排程設定

`daily_news.yml` 裡的排程：

```yaml
- cron: '0 1 * * *'   # 每天 UTC 01:00 = 台灣時間 09:00
```

如果想改時間，格式是 `分 時 * * *`（UTC 時間）：

| 想要的台灣時間 | UTC 時間 | cron 設定 |
|--------------|---------|-----------|
| 早上 8:00 | 00:00 | `0 0 * * *` |
| 早上 9:00 | 01:00 | `0 1 * * *` |
| 晚上 9:00 | 13:00 | `0 13 * * *` |

---

## 常見問題

**Q：Actions 沒有自動跑怎麼辦？**
GitHub Actions 的免費帳號在 repo 長時間沒有 commit 時可能會暫停排程。
解決方法：偶爾 commit 一次，或用手動觸發測試。

**Q：Gemini API Key 額度用完了怎麼辦？**
免費版每天 1500 次請求，每次執行只用 2 次，一年都用不完。

**Q：想改成每天兩次怎麼辦？**
```yaml
- cron: '0 1 * * *'   # 早上 9 點
- cron: '0 10 * * *'  # 晚上 6 點
```

**Q：程式碼需要更新怎麼辦？**
直接在 GitHub 網頁上編輯 `news_agent.py` 並 commit，下次執行就會用新版本。
