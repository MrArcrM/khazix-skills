# aihot · share-daily-tip 子命令规范（全量技巧与观点）

> **本文件由 fork 仓库 MrArcrM/khazix-skills 维护，不属于上游 KKKKhazix/khazix-skills。**
> 触发字面 `/aihot share-daily-tip` / `/aihot share-daily-tip YYYY-MM-DD` 时，agent 先读本文件再执行。
>
> **流程定位**：items 全量 tip → 去掉精选 → 分数过滤 → HTML → share-html → 飞书「云崖书院（日报群）」+ Slack #inbox。

## 触发条件

用户输入**字面包含** `share-daily-tip` 字符串才触发本流程：

| 子命令 | 行为 |
|---|---|
| `/aihot share-daily-tip` | 拉今日全量 tip → 去掉精选 → 保留 score >= 55 → 生成 HTML → 上传 share-html → 发链接 |
| `/aihot share-daily-tip YYYY-MM-DD` | 拉指定日期，同上 |

**字面匹配**：模糊表述（"分享技巧"、"发 tip"、"每日技巧"）不触发，避免误推送。

## 数据口径

- 数据源：AI HOT items 全量池。
- 分类：只取 `tip`（展示名：技巧与观点）。
- 时间：按北京时间自然日过滤。
- 去掉精选：`selected=true` 的条目全部排除，避免和常规 AI HOT 精选日报重复。
- 分数线：默认 `score >= 55`。
- 排序：`score` 降序；同分按发布时间倒序。
- 摘要：API `summary` 原样保留，不做 LLM 改写。

## 分享 targets（飞书 × 1 + Slack × 1）

**飞书 target**：

| label | chat_id | lark profile |
|---|---|---|
| 云崖书院（日报群） | `oc_4409cbc63ef0bfaa3359df0e4acf42d3` | `yunya` |

**Slack target**：

| label | channel_id | 工具 |
|---|---|---|
| #inbox | `C0B65DJHB2L` | Slack MCP `slack_send_message` |

硬约束：
- 飞书必须用 `--profile yunya`，不要用 lark-cli 默认 profile。
- Slack 走 MCP 工具，不要包 bash。
- 两个 target 单点失败不阻断另一个 target。

## 工作流

先解析运行目录：

```bash
SKILL_DIR="<当前加载的 aihot Skill 目录绝对路径>"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/Documents/ClaudeCodeWorkSpace}"
```

### Step 1 · 确认日期

- 先运行 `date "+%Y-%m-%d"` 拿系统当日。
- 用户没指定日期 → 默认今日。
- 用户给了 `YYYY-MM-DD` → 用该日期，先校验格式。

### Step 2 · 拉全量 tip 并过滤

```bash
mkdir -p /tmp/aihot-daily-tip
python3 "$SKILL_DIR/scripts/fetch_daily_tip_items.py" \
  "$DATE" \
  "/tmp/aihot-daily-tip/tip-$DATE.json" \
  --min-score 55
```

输出 JSON 会包含：
- `items[]`：已过滤、已排序的条目。
- `stats.selected_removed`：被去掉的精选条数。
- `stats.low_score_removed`：低于分数线的条数。

如果 `items` 为空：停，告诉用户当天没有符合条件的 tip，不上传、不推送。

### Step 3 · 渲染 HTML

HTML 文件名固定为：

```bash
"/tmp/aihot-daily-tip/AI 每日技巧&观点 $DATE.html"
```

渲染命令：

```bash
python3 "$SKILL_DIR/scripts/render_daily_tip_html.py" \
  "/tmp/aihot-daily-tip/tip-$DATE.json" \
  "/tmp/aihot-daily-tip/AI 每日技巧&观点 $DATE.html"
```

页面要求：
- 标题：`AI 每日技巧&观点 YYYY-MM-DD`
- 顶部 header / hero / toolbar 参照 `share-daily` 的 `claude-light` HTML：`h1 + 共 N 条`、内嵌 `assets/hero.jpg`、左侧信息图标 + `标题可跳转`、右侧链接图标 + `分享`。
- 展示北京时间、来源、摘要、原文链接。
- HTML 正文不展示 score；score 只用于过滤和排序。
- 顶部不展示过滤口径；底部只展示：`全量 tip · 去掉精选 · 分数 55+ · 按分数降序`。
- 不展示 raw API 参数、cursor、HTTP 状态、缓存等基础设施细节。

### Step 4 · 上传 share-html

```bash
SHARE_DIR="$WORKSPACE_ROOT/data/share-html"
HASH=$(openssl rand -hex 3)
SLUG="ai-hot-daily-tip-$DATE-$HASH"
SOURCE="/tmp/aihot-daily-tip/AI 每日技巧&观点 $DATE.html"
TARGET="$SHARE_DIR/${SLUG}.html"
cp "$SOURCE" "$TARGET"

export PATH=~/.nvm/versions/node/v22.20.0/bin:$PATH
cd "$SHARE_DIR" && wrangler pages deploy . \
  --project-name gqshare \
  --commit-dirty=true \
  --branch main

URL="https://share.guoqu4akr.com/${SLUG}.html"
TS=$(date "+%Y-%m-%dT%H:%M:%S")
echo "{\"ts\":\"$TS\",\"source\":\"$SOURCE\",\"slug\":\"$SLUG\",\"url\":\"$URL\",\"kind\":\"aihot-share-daily-tip\"}" >> "$WORKSPACE_ROOT/data/cf-meta/share_log.jsonl"
```

share log 绝不写进 `$SHARE_DIR`，避免公网泄露历史分享链接。

### Step 5 · 推 2 个分享 target

消息只保留两行：

```text
🧠 AI 每日技巧&观点 MM/DD
🔗 URL
```

**5a · 飞书「云崖书院（日报群）」**

```bash
SHORT_DATE=$(date -j -f "%Y-%m-%d" "$DATE" "+%m/%d" 2>/dev/null || date -d "$DATE" "+%m/%d")
MSG="🧠 AI 每日技巧&观点 ${SHORT_DATE}
🔗 ${URL}"

lark-cli --profile yunya im +messages-send \
  --chat-id oc_4409cbc63ef0bfaa3359df0e4acf42d3 \
  --text "$MSG" \
  --as bot
```

**5b · Slack #inbox**

由 LLM 直接调用 Slack MCP `slack_send_message`：

- `channel_id="C0B65DJHB2L"`
- `message=$MSG`

失败只记录，不阻断另一处成功 target。

### Step 6 · 回报

成功后给用户：
- `share-daily-tip ✅ 已推 N/2 个 target`
- target 状态：`✅ 云崖书院（日报群）` / `✅ Slack #inbox`
- URL
- HTML 体积
- 条目数、分数线、去掉精选条数

不要把 curl、wrangler、lark-cli JSON、Slack MCP 原始返回贴给用户。

## 常见错误对应

| 现象 | 根因 | 处置 |
|---|---|---|
| fetch 报 HTTP 403 | API 请求没带浏览器 UA | 检查 `fetch_daily_tip_items.py` 的 `UA` |
| `items` 为空 | 当天没有非精选且 score >= 55 的 tip | 告知用户，不上传、不推送 |
| wrangler 失败 | Cloudflare Pages 部署问题 / node 版本不对 | 留本地 HTML，报告失败 |
| lark-cli token 错 | `yunya` profile 失效 | 提醒 `lark-cli --profile yunya auth login` |
| 飞书发出但群里没看到 | bot 不在群里或 chat_id 变了 | 检查云崖书院日报群和 yunya bot |
| Slack 报 `not_in_channel` | Slack bot 未加入 #inbox | 邀请 bot 进频道 |

## 资产清单

- `scripts/fetch_daily_tip_items.py` — 拉全量 tip、过滤 selected、score、北京时间日期，并排序。
- `scripts/render_daily_tip_html.py` — JSON → self-contained HTML。

## 不要做

- 不要在用户没明说 `share-daily-tip` 字符串时触发本流程。
- 不要把精选条目混进来。
- 不要把 score < 55 的条目混进来。
- 不要改写 API summary。
- 不要推送到 AI 俱乐部核心成员群或日报群。
- 不要自动调度 cron / launchd。
- 不要回退到 PDF 流程。

## 决策记录

- **2026-06-15**：新增 `share-daily-tip`，用于把 AI HOT 全量 `tip` 中非精选且 score >= 55 的内容，按 score 降序整理成 HTML，推飞书「云崖书院（日报群）」+ Slack #inbox。HTML 文件名固定为 `AI 每日技巧&观点 $DATE.html`。
- **2026-06-15**：确认「云崖书院」分享 target 使用日报群 `oc_4409cbc63ef0bfaa3359df0e4acf42d3`，不是旧的「云崖书院筑基斋」`oc_9019463d0066f4f23f1811217d9dae96`。
