# aihot · share-daily 子命令规范（HTML 流程）

> **本文件由 fork 仓库 MrArcrM/khazix-skills 维护，不属于上游 KKKKhazix/khazix-skills。**
> 触发字面 `/aihot share-daily` / `/aihot share-daily YYYY-MM-DD` 时，agent 先读本文件再执行。
>
> **流程定位**：JSON → HTML → share-html → 飞书短消息（旧 markdown → PDF 流程已下线，由 test-daily 在测试群迭代稳定后 apply 过来）。test-daily.md 继续作为后续迭代沙盒，本文件是生产流程。

## 触发条件

用户输入**字面包含** `share-daily` 字符串才触发本流程：

| 子命令 | 行为 |
|---|---|
| `/aihot share-daily` | 拉今日日报 → 生成 HTML → 上传 share-html → 发链接到**分享群** |
| `/aihot share-daily YYYY-MM-DD` | 拉指定日期日报，同上 |

**字面匹配**：模糊表述（"分享日报"、"发到分享群"、"分享 daily"）**不触发**——避免误推送到生产分享群。

## 飞书 bot + 群

- **bot profile**：`ai-digest`（即 AI-Daily-Digest 飞书机器人）。所有 lark-cli 调用必须显式 `--profile ai-digest`，**不要**用默认 profile。
- **分享群 chat_id**：`oc_937244556a810e4996bfc221adb21794`（飞书显示名 "AI俱乐部核心成员群"）

## 工作流（一气呵成，任一步失败即停 + 告知用户、绝不继续）

### Step 1 · 确认日期

- `date "+%Y-%m-%d"` 拿系统当日（**不**信对话注入的 currentDate）
- 用户没指定日期 → 默认今日
- 用户给了 `YYYY-MM-DD` → 用该日期，先校验格式正确

### Step 2 · 拉数据 + role 标签

用 `fetch_daily_with_roles.py` 一步完成：
1. 抓 `/api/public/daily/$DATE` JSON
2. 抓 `/daily` SSR HTML 提取 role 映射（aihot public API/RSS/OpenAPI 都不暴露 role，唯一来源是 SSR markup）
3. 按 sourceName 在 sections 内 join role
4. 重排章节顺序为：模型 → 产品 → 技巧 → 行业 → 论文
5. 简化章节标签（"模型发布/更新" → "模型" 等）
6. 输出合并 JSON 到指定路径

```bash
SKILL_DIR=/Users/guoqu/Documents/ClaudeCodeWorkSpace/agents/honey-bee/.claude/skills/aihot
mkdir -p /tmp/aihot-daily
python3 "$SKILL_DIR/scripts/fetch_daily_with_roles.py" "$DATE" "/tmp/aihot-daily/daily-$DATE.json"
```

输出 JSON 结构：
```json
{
  "date": "YYYY-MM-DD",
  "sections": [
    {
      "label": "模型",
      "items": [
        {
          "title": "...",          // API 原 title
          "source": "...",         // API 原 sourceName（不 remix）
          "source_role": "官方·X",  // 从 /daily SSR 抓的 role-tag
          "summary": "...",        // API 原 summary，一字未改
          "url": "..."             // API 原 sourceUrl
        }
      ]
    }
  ]
}
```

role 取值集：`官方·X` / `X·KOL` / `官方` / `综合资讯` / `学术机构` / `""`（解析失败兜底）

脚本会向 stderr 打印 `wrote {path} — N items, M role matched (K missing)`，正常情况 `K=0`（24/24 命中）。

**错误处理**：
- HTTP 404（日报未生成 / 不存在）→ **告诉用户，停**："$DATE 日报还没生成（北京 8:00 后才出），要不要拉昨天？" **不要静默 fallback** 到昨日
- 其他 HTTP / 网络错误 → **告诉用户，停**
- 大量 role missing（K 远大于 0）→ aihot SSR markup 可能改版，提示用户检查 `scripts/fetch_daily_with_roles.py` 的 `ROLE_PAT` 正则

### Step 3 · LLM remix 标题（先跳过 — MVP）

> **MVP 阶段不做这步**——API 原 title 已经足够可读，先保持流程最简。
>
> 未来加这步时：agent 读 `daily-$DATE.json`，对每条 item 按"标题 remix 风格"改写 title 字段，覆写文件。规则：去营销腔/英译中/过长提炼核心/可加副标题/≤30 字。

### Step 3.5 · 每日重生成 hero banner

按 `$DATE` md5 hash 从 `scripts/hero_prompts.json` 的 20 张清晨感基调池里抽一条，跑 gpt-image 生成 **1792x768（21:9 直出）** → sips 缩到 1280 宽 + jpg quality 88 → 覆盖 `assets/hero.jpg`。同一天复跑命中同一基调（hash 确定），跨天换图。

**昨日 palette 避让**：成功生成后会写 `assets/hero-state.json` 记录 `{last_date, last_id, last_palette, last_subject}`；下次跑时若 hash 命中条目的 `palette` 和昨日相同，向后滑一格继续找直到不撞 palette。治"连续两天同色调"的视觉重复（如 5-16/5-17 两条 Cornflower Blue 撞蓝船）。失败不写 state，保持和实际 `hero.jpg` 一致。

```bash
python3 "$SKILL_DIR/scripts/gen_hero.py" "$DATE"
```

耗时 ~60-90s（gpt-image API 一张约 30-60s + sips 几秒），成本 ¥0.30/张。

**这一步是 Step 1-6 全流程里唯一一个失败不阻断的例外**——hero 只是装饰，gpt-image 偶发失败 / 网络抖动 / quota 用完时，脚本退出非 0 且**不修改** `assets/hero.jpg`，沿用前一天那张继续 Step 4。具体处理：

```bash
if ! python3 "$SKILL_DIR/scripts/gen_hero.py" "$DATE"; then
  echo "⚠️ hero 重生成失败，沿用昨日 hero.jpg 继续" >&2
fi
```

**基调池**：20 张清晨感 hand-drawn 插画（2026-05-15 curated）—— 薄荷绿 4 张 / 蓝色系 5 张 / 紫色 2 张 / 粉桃 4 张 / 海泡沫 2 张 / 桉绿 1 张 / 杏色 1 张 / 春绿 1 张。新增/删除基调改 `hero_prompts.json` 即可。

### Step 4 · 渲染 HTML

```bash
python3 "$SKILL_DIR/scripts/render_daily_html.py" \
  "/tmp/aihot-daily/daily-$DATE.json" \
  "/tmp/aihot-daily/AI HOT日报-$DATE.html"
```

默认主题 `claude-light`（Claude 亮色）。换主题加 `--theme <name>`：

```bash
python3 "$SKILL_DIR/scripts/render_daily_html.py" \
  "/tmp/aihot-daily/daily-$DATE.json" \
  "/tmp/aihot-daily/AI HOT日报-$DATE.html" \
  --theme claude-light

# 列出所有可用主题
python3 "$SKILL_DIR/scripts/render_daily_html.py" --list-themes
```

输出 self-contained HTML，预期 ~180KB（含 base64 内嵌 hero banner）。

**用户没指定主题就走默认 `claude-light`**——除非明确说「换主题 / 用 X 主题发」之类，绝不主动切换。

**主题包结构**（在 `themes/<name>/` 下）：
- `template.html.j2` — Jinja2 模板，HTML 骨架
- `style.css` — 完整 CSS
- `meta.json` — `{name, label, description, default, hero_pool}`

**模板 context**（所有主题共享同一份契约，主题不能反向要求脚本加字段）：
- `title` / `date` / `total` / `section_stats` — 报头数据
- `hero_uri` — base64 data URI（空串表示无 hero）
- `sections[]` — 每段含 `label` 和 `entries[]`
- `entries[i]` — `{idx, title, url, badge, src_body, summary_html}`
  - 注意：`summary_html` 已经 escape + linkify 过，模板里要 `| safe`
  - 字段叫 `entries` 不叫 `items`：Jinja2 里 `dict.items` 是 method 会劫持属性访问
- `css` — 主题 CSS 字符串，模板里 `<style>{{ css | safe }}</style>` 嵌入

**claude-light 主题渲染特性**（视觉迭代 v2 定稿 2026-05-15）：

布局结构：
- 暖米底 `#f0eee6`（Anthropic 招牌色）+ 显式 `<meta name="color-scheme" content="light">` 强制亮色
- container max-width 720px
- 垂直顺序：居中标题(h1) + 居中 meta → 12px → hero → 18px → toolbar → 56px → 章节内容
- 整体「报头区 + 正文区」分明

Hero banner：
- base64 内嵌 `assets/hero.jpg`，**21:9 直出**（gpt-image `--size 1792x768`，CSS `aspect-ratio: 21/9; object-fit: cover` 几乎无裁切），圆角 8px（移动端 6px）
- 主题：每日按 $DATE hash 从 20 张清晨感基调池抽一条（Step 3.5 已经覆盖好 hero.jpg）
- 全部走"清晨明快 + 与暖米底反差"的色调（薄荷/蓝/紫/粉桃/海泡沫…）— 排除深夜墨色 / cream oat / 烟橙姜黄

Toolbar（hero 正下方）：
- 左：`ⓘ 标题可跳转` — info icon + 浅灰提示文字
- 右：`🔗 分享` 按钮 — 链接 icon + 纯文字、无 border、淡灰色，向内收 8px padding
- 点击「分享」复制 `window.location.href` → 文字切「已复制」+ 砖橙色 1.8s → 自动恢复
- 用 `navigator.clipboard.writeText` 主路径 + `document.execCommand('copy')` 兜底（非 secure context）

正文 article 排版：
- long-form 段落式（**无卡片**、无阴影、无圆角边框、无外框）
- 每条 item 用细横线 `--rule-soft` `#e8e6dc` 分隔
- **编号大数字改成右上角水印**：`position: absolute`、56px（移动端 42px）、`rgba(20,20,19,0.045)` 极淡、`font-weight: 800`、`letter-spacing: -0.04em`、`z-index: 0`、`pointer-events: none`
- body `padding-right: 64px`（移动端 48px）让正文文字跟水印数字**在垂直方向上不重叠**

标题与信源：
- 标题点击跳 sourceUrl（默认黑色无下划线，hover 变砖橙）— 不显示「原文 →」
- 信源 = 徽章（`官方·X` 等）+ API 原 sourceName 主体（@handle 完整保留）

Summary 处理：
- API 原文照抄（一字不改）
- summary 内 URL 自动 linkify：虚线下划线、跟正文同色、hover 才变橙
- hashtag 弱化为浅灰小字（0.88em, opacity 0.6）

章节：
- 章节竖条统一砖橙 `#c46849`，不分章节配色（试过 5 章专色太花，已撤回）
- 章节版块标签简化（模型/产品/技巧/行业/论文）
- header meta：`共 N 条 · 模型 X · 产品 Y · 技巧 Z · 行业 W · 论文 V`，不写"数据来源"

其它：
- 没有 lead 段（即使 API 返回 `lead` 也不渲染）
- 没有 hr 横线分隔（试过 hero 下紧贴一条淡横线，效果太碎，撤回）

**错误**：脚本失败 → **告诉用户，停**

### Step 5 · 上传 share-html

走 `/share-html` skill 的核心逻辑（cp 到数据目录加 6 位 hash 防猜 → wrangler 部署 → 拿 URL → 写 share log）：

```bash
SHARE_DIR=~/Documents/ClaudeCodeWorkSpace/data/share-html
HASH=$(openssl rand -hex 3)
SLUG="ai-hot-daily-$DATE-$HASH"
TARGET="$SHARE_DIR/${SLUG}.html"
cp "/tmp/aihot-daily/AI HOT日报-$DATE.html" "$TARGET"

# wrangler 需要 node v22+，nvm 装在 ~/.nvm/versions/node/v22.20.0/
export PATH=~/.nvm/versions/node/v22.20.0/bin:$PATH
cd "$SHARE_DIR" && wrangler pages deploy . \
  --project-name gqshare \
  --commit-dirty=true \
  --branch main

URL="https://share.guoqu4akr.com/${SLUG}.html"
TS=$(date "+%Y-%m-%dT%H:%M:%S")
echo "{\"ts\":\"$TS\",\"source\":\"/tmp/aihot-daily/AI HOT日报-$DATE.html\",\"slug\":\"$SLUG\",\"url\":\"$URL\"}" >> ~/Documents/ClaudeCodeWorkSpace/data/cf-meta/share_log.jsonl
```

⚠️ share log **绝不**写进 `$SHARE_DIR` —— wrangler 全量上传该目录，log 会变成公网可读，泄露所有历史分享链接。永远 append 到 `~/Documents/ClaudeCodeWorkSpace/data/cf-meta/share_log.jsonl`（外部）。

**错误**：wrangler 失败 → **告诉用户，停**，留 HTML 在本地

### Step 6 · 发飞书分享群（短文本消息）

只发两行：`📝 AI HOT 日报 MM/DD` + `🔗 URL`。**不要**塞内容摘要——长内容点链接看，群消息保持清爽（≤10 字描述规则，遵循 share-html skill 约定）。

```bash
SHORT_DATE=$(date -j -f "%Y-%m-%d" "$DATE" "+%m/%d" 2>/dev/null || date -d "$DATE" "+%m/%d")
MSG="📝 AI HOT 日报 ${SHORT_DATE}
🔗 ${URL}"
lark-cli --profile ai-digest im +messages-send \
  --chat-id oc_937244556a810e4996bfc221adb21794 \
  --text "$MSG" \
  --as bot
```

**`--profile ai-digest` 必加**——少了会用默认 Claude Code App bot 发，分享群里 AI-Daily-Digest 才是预期发送方。

**`--chat-id` 一定是分享群 `oc_937244556a810e4996bfc221adb21794`**——别误用测试群 ID。share-daily 的核心语义就是发分享群，发错群比不发更糟。

**错误**：lark-cli 失败 → **告诉用户，留 HTML 在本地** `/tmp/aihot-daily/AI HOT日报-$DATE.html` + URL，让他手动转发

### Step 7 · 回报

成功后给用户：
- "share-daily ✅ 已发分享群"
- `URL`：$URL
- `message_id`：lark-cli 返回值
- `HTML 体积`：KB
- `role 命中`：N/N（fetch 脚本输出）

**不要**把端点路径 / curl 命令 / wrangler 输出 / lark-cli 完整 JSON 泄漏到回复里。

## 常见错误对应

| 现象 | 根因 | 处置 |
|---|---|---|
| fetch 报 HTTP 404 | 日报未生成（北京 8:00 前）/ 日期不存在 | 告知用户，问要不要拉昨日 |
| fetch 报 HTTP 403 | UA 未带 / curl 默认 UA 被 nginx 黑名单挡 | 检查 `fetch_daily_with_roles.py` 里的 `UA` 常量 |
| role matched 远小于 total | aihot 网站 SSR markup 改版 | 检查 `ROLE_PAT` 正则；临时可继续，role 为空时脚本自动 fallback 到 `parse_source()` 三段式徽章（X / RSS / 网页）|
| render 报 hero 文件不存在 | `assets/hero.jpg` 被误删 | 不影响渲染（脚本会跳过 hero block），但页面顶部少一块。重生成见下方"资产清单" |
| wrangler 报 "Project not found" | gqshare 项目被误删 | 重建：`wrangler pages project create gqshare --production-branch main` |
| lark-cli 报 token 错误 | ai-digest profile token 失效 | 告知用户运行 `lark-cli --profile ai-digest auth login` |
| 飞书消息发出但群里没看到 | bot 不在分享群里 | 告知用户把 AI-Daily-Digest 加进分享群 |

## 资产清单

- `scripts/fetch_daily_with_roles.py` — 拉数据 + SSR HTML role 注入 + 章节重排 + 标签简化
- `scripts/render_daily_html.py` — JSON → self-contained HTML，加载 `themes/<name>/` 用 Jinja2 渲染（数据准备 + linkify + 徽章/hashtag 在脚本，CSS/HTML 在主题）
- `scripts/gen_hero.py` — 按 $DATE hash 从基调池抽一条（撞昨日 palette 时向后滑窗）→ gpt-image 21:9 直出 → sips 压缩 → 覆盖 hero.jpg；失败不阻断（exit ≠ 0 时 hero.jpg 和 hero-state.json 都不动）
- `scripts/hero_prompts.json` — 20 张清晨感基调池（curated 2026-05-15）；新增/删除基调改这里
- `assets/hero.jpg` — 顶部 banner，1280 宽 ~100-150KB；由 gen_hero.py 每日覆盖（21:9 jpg quality 88）
- `assets/hero-state.json` — 最近一次成功生成的 `{last_date, last_id, last_palette, last_subject}`，用于跨天 palette 避让
- `themes/<name>/` — 主题包；目前有 `claude-light`（默认）。新增主题见下方「扩展主题」

**手动测试某一天的 hero**：

```bash
SKILL_DIR=/Users/guoqu/Documents/ClaudeCodeWorkSpace/agents/honey-bee/.claude/skills/aihot
python3 "$SKILL_DIR/scripts/gen_hero.py" 2026-05-15  # 任意日期；同日 hash 命中同一基调
# 看新 hero
open "$SKILL_DIR/assets/hero.jpg"
```

**扩充基调池**：编辑 `scripts/hero_prompts.json` 的 `candidates` 数组，加新 entry（id / palette / subject / body）。`common_head` 和 `common_tail` 通用约束保持不变（极简手绘 + 黑描边 + 21:9 + 无文字）。改完不需要 redeploy，下次跑 gen_hero.py 自动用新池子。

## 扩展主题

新加一个主题 `<name>`：

1. `mkdir themes/<name>` 创建目录
2. 写三个文件：
   - `meta.json` — `{"name": "<name>", "label": "中文短名", "description": "...", "default": false, "hero_pool": "morning-soft"}`
   - `style.css` — 完整 CSS（不要再用 f-string 转义，原样写）
   - `template.html.j2` — Jinja2 模板，必须 `<style>{{ css | safe }}</style>` 嵌入 CSS，循环 `{% for section in sections %} {% for item in section.entries %}`，`{{ item.summary_html | safe }}` 拿已 linkify 的 HTML
3. `python3 scripts/render_daily_html.py --list-themes` 验证出现在列表里
4. `python3 scripts/render_daily_html.py daily.json out.html --theme <name>` 渲染测试

**主题契约硬约束**：
- 模板只能消费固定 context 字段（`title / date / total / section_stats / hero_uri / sections / css`），**不能反向要求脚本加字段**——否则主题间会漂移、新加主题就得改脚本
- `summary_html` 已含 HTML 标签（`<a class="inline-link">` / `<span class="hashtag">`），主题 CSS 必须给这两个 class 准备样式（参考 claude-light/style.css）
- 不要把 `.default` 设成多个主题——`list_themes()` 按 default 排序时只取第一个，多了行为未定义
- 主题里**禁止**写 JS 业务逻辑——share-btn 那段脚本目前固化在模板，所有主题都复制（暂时算约定，将来做太多主题再抽 partial）

## 不要做

- **不要**在用户没明说 `share-daily` 字符串时触发本流程
- **不要**把 share-daily 默认发到测试群（核心语义就是发分享群 `oc_937244556a810e4996bfc221adb21794`）
- **不要**改写 API summary 文本（"原样照抄"是硬约束）
- **不要**渲染 `lead` 段（即使 API 返回了 `lead` 字段也跳过）
- **不要**主动加章节内"⚠️ 跟前一天重合" / "今日 N 条" / "数据来源" 等装饰性提示
- **不要**自动调度 cron / launchd 跑本流程——用户每次手动 `/aihot share-daily` 才跑
- **不要**用默认 lark-cli profile（必须 `--profile ai-digest`）
- **不要**回退到旧 PDF 流程（已下线，统一走 HTML + share-html）

## 决策记录

- **2026-05-09**：创建 share-daily / test-daily 子命令规范，markdown → PDF 流程，章节顺序"模型→产品→技巧→行业→论文"
- **2026-05-09**：PDF 链接高亮 + 章节空行两个首发问题修复（URL 用 `[URL](URL)` 显式 link 触发 typst 蓝色高亮，章节前必须空行避免 pandoc 把 `## XX` 当 URL 行延续）
- **2026-05-15**：HTML 流程在测试群迭代稳定后 apply 到 share-daily，PDF 流程下线。test-daily.md 作为后续迭代沙盒保留。详细视觉/流程决策见 test-daily.md "决策记录" 节
  - 废弃 PDF：日报作为一次性消费品，HTML（可点跳转、移动端响应式、share-html 链接看完即焚）比 PDF 附件体验好
  - 跳过 markdown 中间步：JSON → HTML 直出，agent 关注语义层（fetch + 可选 remix），脚本关注视觉层（CSS / 排版 / linkify / 徽章）
  - role 字段双抓：aihot public API 不暴露 role，唯一来源是 `/daily` SSR HTML 正则提取。多 200ms 一次 GET 换"官方·X / X·KOL / 综合资讯 / 学术机构"精细分类，值得
  - hero banner 每日 hash 抽签换图（gpt-image 21:9 直出，¥0.30/天，失败沿用昨日不阻断）
  - 视觉：暖米底 `#f0eee6` + long-form + 章节统一砖橙竖条 + 编号水印 + 标题即链接 + summary 一字不改
