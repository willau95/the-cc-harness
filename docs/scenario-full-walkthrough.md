# 完整手动测试走查 — Zero → N-Mac N-Agent 协作

> **目标读者**：一台什么都没装的 Mac，只在 GitHub 上看过这个 repo。
> **终点**：多台 Mac 协作完成一个真实任务，你只在 dashboard 上操作。
>
> 每一步告诉你：**在哪台机器 / 哪个窗口** · **敲什么命令或点什么按钮** · **期望看到什么** · **出错去哪查**。

## 目录

- [0 · 角色设定 + 真实场景](#0--角色设定--真实场景)
- [1 · Mac-A 从零安装（8 分钟）](#1--mac-a-从零安装8-分钟)
- [2 · Mac-B 接入 fleet（UI 主导，5 分钟）](#2--mac-b-接入-fleet-ui-主导5-分钟)
- [3 · Spawn 两个 agent（UI 操作）](#3--spawn-两个-agentui-操作)
- [4 · 真实跨机协作（15–25 分钟）](#4--真实跨机协作1525-分钟)
- [5 · Human-in-the-loop 硬控制](#5--human-in-the-loop-硬控制)
- [6 · Self-evolution: proposals 审批](#6--self-evolution-proposals-审批)
- [📊 完成度 · 当前 v0.2 支持多少](#-完成度--当前-v02-支持多少)
- [🛟 常见问题排查](#-常见问题排查)

---

## 0 · 角色设定 + 真实场景

| | |
|---|---|
| **Mac-A** | 你坐的这台。dashboard 只在这跑。 |
| **Mac-B** | 协作 peer。会跑一个 agent 帮你。 |
| **场景** | 为一个浏览器 3D 赛车游戏 `NeonRacer` 做 landing page |
| **分工** | Mac-A: `frontend-dev` 写代码 · Mac-B: `seo-specialist` 研究 2026 Google SEO 要求，写入 arsenal |
| **你的角色** | CEO — 只点 dashboard、审 arsenal、批 proposal、必要时 pause |

---

## 1 · Mac-A 从零安装（8 分钟）

### 1.1 前置（2 分钟）

```bash
# Mac-A 终端
xcode-select -p || xcode-select --install       # 图形向导，一路 OK
python3 --version                                # ≥ 3.11
node --version                                   # ≥ 20
brew --version                                   # 如缺：/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

如缺 Python/Node：
```bash
brew install python@3.12 node@22
```

### 1.2 Claude Code（runtime）

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude login       # 浏览器 OAuth
```

**为什么重要**：harness 是 Claude Code 的外骨骼，不是替代品。每个 agent 是真的 `claude` 进程，用你的订阅登录，**不需要 API credits**。

### 1.3 Tailscale + mac-fleet-control（跨机必备）

```bash
brew install --cask tailscale
open -a Tailscale       # GUI 里登录（Mac-A 和 Mac-B 用同一个账户）
tailscale ip -4         # 记下 Mac-A 的 IP，例 100.100.50.1

git clone https://github.com/willau95/mac-fleet-control ~/mac-fleet-control
cd ~/mac-fleet-control && ./install.sh
fleet-ssh --help        # 应该能用
```

### 1.4 harness 本体

```bash
git clone https://github.com/willau95/the-cc-harness ~/the-cc-harness
cd ~/the-cc-harness && ./install.sh
exec zsh                # 重载 PATH
harness --version       # → harness 0.2.0
harness dashboard       # → http://localhost:9999
```

**期望**：浏览器打开 dashboard，左侧 sidebar 有 Dashboard / Machines / Fleet / Chat / Events / Arsenal / Tasks / Proposals / Projects。当前是空的（0 agents、0 events）。

---

## 2 · Mac-B 接入 fleet（UI 主导，5 分钟）

### 2.1 Mac-B 上的一次性本机准备（只需做 1.2 + 1.3）

在 Mac-B 终端：
```bash
# Tailscale（同一个账户！）
brew install --cask tailscale && open -a Tailscale
tailscale ip -4    # 记下，例 100.100.50.2
whoami             # 记下用户名，例 bob

# Claude Code（用你自己的订阅登录）
curl -fsSL https://claude.ai/install.sh | bash
claude login
```

**这一步必须在 Mac-B 本人操作**：OAuth 需要浏览器。**不要**在 Mac-B 上装 harness、跑 dashboard — 接下来你在 Mac-A 的 UI 里远程搞定。

### 2.2 回 Mac-A：加 Mac-B 到 fleet

Mac-A 终端（只这一次，以后全部 UI 操作）：

```bash
# 测 Tailscale 通
tailscale ping 100.100.50.2

# 注册 peer（推 SSH 公钥）
fleet-ssh add Mac-B 100.100.50.2 bob

# 验证
fleet-ssh Mac-B 'echo "hello from $(hostname)"'
```

**不符合预期**：
- `permission denied (publickey)` → 手动把 `~/.ssh/id_ed25519.pub` 加到 Mac-B 的 `~/.ssh/authorized_keys`
- `no route to host` → 两台都登同一 Tailscale 账户？`tailscale status` 看

### 2.3 UI 里继续（关键！）

Mac-A 浏览器 → **`/machines`**

**期望看到**：
- `Mac-A` 卡 — `local` 徽章、绿点、Harness: `local`
- `Mac-B` 卡 — 绿点、延迟 ~XXXms、**Harness: not installed**、黄色提示框 "SSH works but harness is missing"

**点击操作**：
1. **[ Test ]** on Mac-B → bottom-right 弹绿 toast `Mac-B online · XXXms`
2. **[ Install ]** on Mac-B → 1–3 分钟等待 → toast `Mac-B: harness installed` → 卡片刷新后 Harness 变绿 ✓
3. **[ Bootstrap ]** on Mac-B → toast `Mac-B: peers.yaml updated (1 peers)` — 把 Mac-A 的坐标教给 Mac-B，这样 Mac-B 上的 agent 之后能反向 send_message 到 Mac-A

**这一步替换了以前手动 `fleet-ssh Mac-B 'git clone + install.sh'`**。

---

## 3 · Spawn 两个 agent（UI 操作）

### 3.1 frontend-dev 到 Mac-A 本地

Mac-A 浏览器 → **`/fleet`** → **[ + Spawn Agent ]**：

| 字段 | 填 |
|---|---|
| Role | `frontend-dev` |
| Name | `gamedev1` |
| Folder | `/Users/你自己/harness-test/game-dev`（绝对路径） |
| Machine | `Mac-A` (local) |
| Initial prompt (可选) | `You're building the landing page for NeonRacer, a browser 3D racing game. First task will come via mailbox. Follow Iron Laws.` |

点 **[ Spawn ]** → toast `gamedev1 spawned`。

**人肉一步**（这个省不掉）：Mac-A 新开一个终端，启动它的 claude：
```bash
cd /Users/你自己/harness-test/game-dev
claude
```

**为什么**：Claude Code 需要 TTY。dashboard 不会代你起这个进程，也不应该 —— 你必须看到 claude 在哪个终端里跑。

### 3.2 seo-specialist 到 Mac-B

回 `/fleet` → **[ + Spawn Agent ]**：

| 字段 | 填 |
|---|---|
| Role | `seo-specialist` |
| Name | `seo1` |
| Folder | `/Users/bob/harness-test/seo-agent` ← **Mac-B 上的绝对路径** |
| Machine | `Mac-B` ← 关键！换成 Mac-B |

点 **[ Spawn ]** → toast `seo1 spawned on Mac-B`。背后：dashboard 调 `fleet-ssh Mac-B 'harness init …'`，Mac-B 上的 identity 落盘 + 广播到所有 peer。

**人肉一步**（在 Mac-B 上，或 screen sharing）：
```bash
cd /Users/bob/harness-test/seo-agent
claude
```

### 3.3 验证

Mac-A 浏览器：
- `/fleet` → 2 行，都绿点 online
- `/machines` → Mac-A 卡 Agents 列 = 1，Mac-B = 1
- `/events` → 每个 agent 刚 heartbeat 的条目，Mac-B 那条带 `on Mac-B` 徽章 ✓

---

## 4 · 真实跨机协作（15–25 分钟）

### 4.1 给 frontend-dev 下任务

`/chat` → 点 `gamedev1` 进 chat 线程 → 输入：

```
任务：为 NeonRacer（浏览器 3D 赛车游戏）写 landing page。

分两步：
1. 先发 send_message 给 seo1（seo-specialist, on Mac-B）：
   subject: "seo_requirements_request"
   body: "为 NeonRacer landing page 找 2026 Google 浏览器 3D 游戏的
   SEO 核心要求。只用一手源（web.dev / developers.google.com）。
   产出 arsenal 条目我可以引用。"

2. 等 seo1 回复后，按其建议写 index.html + meta tags。

做完 send_message 到 human@dashboard 汇报。
```

点 **[ Send ]** → 消息出现（右对齐，human@dashboard）。

### 4.2 watch 它跑

Mac-A 浏览器开两个 tab：
- tab 1: `/events` — 实时流，每几秒自动刷新
- tab 2: `/arsenal` — 监控新条目

**期望时序**（每一条都带对应 agent 的 `on Mac-X` 徽章）：
```
[gamedev1]      sent_message         → seo1 (cross-machine)
[seo1, Mac-B]   received_message
[seo1, Mac-B]   tool_call: WebSearch × 3
[seo1, Mac-B]   tool_call: WebFetch × 3
[seo1, Mac-B]   arsenal_add × 3–5
[seo1, Mac-B]   sent_message         → gamedev1 (cross-machine back)
[gamedev1]      received_message
[gamedev1]      tool_call: Write (index.html)
[gamedev1]      sent_message         → human@dashboard
```

### 4.3 你作为 CEO 审 arsenal

`/arsenal` 看到几条新的 `trust: agent summary`、右侧 `on Mac-B` 徽章。

**点进一条**（例 "Mobile-First Indexing Requirements"）：
- **[ ← Back to Arsenal ]** 顶部
- Content 区显示内容
- METADATA 侧栏：Slug / Trust / Source type / Produced by / Produced at / Chain depth
- SOURCE REFS 里带可点的 web.dev 超链接
- **Trust hint** 一行："Raw agent output — not yet reviewed. Verify or retract to close the loop."

**操作**：
- 内容对了 → **[ Mark verified ]** → badge 立刻变绿 `human verified`，按钮文字变 `Verified ✓`（跨机路由到 Mac-B 的 sqlite 已更新）
- 内容错了 → **[ Retract ]** → `retracted`，agent 之后引用会看到被降级

### 4.4 frontend-dev 实现 + awaiting-review

回 `/chat/gamedev1-xxx`：看 SEO 回信（markdown 渲染，带 arsenal slug 链接）。

gamedev1 应该：
1. 读 arsenal — 优先你标 verified 的
2. 写 `index.html`、可能跑 lighthouse 自检
3. 发消息到 `human@dashboard` 说"完成了"
4. 自己 `checkpoint_set` 把 task 设为 `awaiting_review`

**查进度**：`/tasks` → gamedev1 的 task 状态走 `in_progress` → `awaiting_review`。

### 4.5 你批准交付

`/tasks` 点那条 `awaiting_review` → 读它的 `next_step` + 交付说明。

- 满意 → 回 chat `"approved, ship it"` → agent 把 task 标 `verified` → `done`
- 要改 → 回 chat 具体反馈 → task 回到 `in_progress`

---

## 5 · Human-in-the-loop 硬控制

### 5.1 Pause（看到 agent 跑偏）

`/fleet` 某 agent 行 `⋯` 菜单 → **[ Pause ]**（或直接 agent detail 页按钮）

**发生了**：dashboard 跨机在 agent folder 里 `touch .harness/paused`。下次该 agent 的任何 skill tool call 会短路返回固定的 paused 响应。claude 仍在跑，但不再写任何东西。

**UI 反馈**：amber `paused` badge、按钮变 Resume、events 多一条 `paused`。

### 5.2 通过 chat 给指示

```
chat → seo1：
我刚 pause 你了。你在抓 Reddit 帖子，那不是一手源。
只用 web.dev / developers.google.com / MDN。resume 后重来。
```

### 5.3 Resume / Kill

- **[ Resume ]** — sentinel 文件删除，下次 tool call 恢复
- **[ Kill ]** — 终极选项。pkill claude 进程，但 identity / arsenal / checkpoint / events **全部保留在磁盘**，日后可同名 respawn 继承所有历史

---

## 6 · Self-evolution: proposals 审批

### 6.1 它怎么触发

一个 agent 工作中发现可改进点（例：SEO 发现 Google Search Central 比某博客权威得多） → 调 `propose_skill_update` skill tool：

```python
propose_skill_update(
  slug="prefer-google-search-central",
  content="When citing SEO requirements, prefer developers.google.com/search/docs over blog posts.",
  rationale="Observed 3 instances where a blog's advice contradicted the official docs"
)
```

### 6.2 critic 自动 review（v0.2 新加）

proposal 被创建时，harness 自动查找第一个 `role=critic` 的在跑 agent，push 一条 `critic_review_request` 到它 inbox。critic agent 读完后 call `set_critic_verdict` tool → status 变 `critic_approved` / `needs_revision` / `rejected`。

**前提**：你得 spawn 一个 critic agent（步骤 3.x 里，role 选 `critic`）。否则 proposal 原地等。

### 6.3 你审批

`/proposals` → **Pending** tab → 看到 `critic_approved` 的 proposal
- 读 diff + rationale + critic 评语
- **[ Approve ]** → `_promote_skill()` 把 skill 真的写进 `~/.harness/skills/global/<slug>/SKILL.md`。下次 agent spawn 带上它。
- **[ Reject ]** → 归档

---

## 📊 完成度 · 当前 v0.2 支持多少

| Requirement | 状态 | 怎么测 |
|---|:---:|---|
| Zero-install 到 Mac-A 能跑 | ✅ | 按 §1 跑一遍 |
| UI 里加 Mac-B（Test + Install + Bootstrap）| ✅ | §2.3 三个按钮 |
| 跨机 spawn agent | ✅ | §3 Spawn dialog 里 Machine 选 Mac-B |
| 跨机 chat（A ↔ B） | ✅ | §4.1 |
| Arsenal 跨机聚合 + 归属机 trust 更新 | ✅ | §4.3 |
| 跨机 events 聚合视图 | ✅ | §3.3 / §4.2 events 带 `on Mac-X` 徽章 |
| Pause / Resume / Kill 跨机 | ✅ | §5 |
| PreCompact digest + SessionStart wake-up | ✅ | 自动触发；`~/.harness/logs/hook.log` 可看 |
| Task FSM proposed → done | ✅ | §4.4-4.5 |
| Proposal → critic auto-notify | ✅ v0.2 新加 | §6.2（前提 critic agent 在跑）|
| Critic agent 自己投票（不需要人接力）| ⚠️ | critic 需要被 wake 才读 inbox；待接 auto-poll |
| Claude login 也在 UI 代理 | ⚠️ | OAuth 必须浏览器；每台 Mac 还得本人登 |
| 90% dashboard-only 操作 | ✅ | 唯一终端步骤：`claude login` + `claude` 启动 TTY |

---

## 🛟 常见问题排查

| 症状 | 先查 |
|---|---|
| `/fleet` 空 | `harness status` 看本地 registry；claude login 了吗 |
| agent 绿点变灰（stale） | `/events` 看有无最近 heartbeat；超 30 分钟算 stale |
| 跨机 spawn 失败 | `/machines` 看 peer 的 Harness 列；点 [ Install ] 重装 |
| `Mark verified` 无变化 | 条目 `on Mac-B` 但 peer 的 harness < 0.2.0？点 [ Update ] |
| Chat 发出去没响应 | agent 的 claude 进程活着吗？没 TTY 就没人处理 |
| PreCompact digest 没写 | `cat ~/.harness/logs/hook.log` — 90% PATH 问题 |
| Events 看不到 Mac-B 的 | peer harness < 0.2.0 没有 `events dump-json`；点 [ Update ] |
| Proposals 一直 pending | 没有 `role=critic` 的 agent 在跑 |
| `harness` not found after install | `exec zsh` 重载 shell |

---

**下一步**：当你按这份走完一遍，哪一步不顺，回来告诉我具体症状，我对着修。
