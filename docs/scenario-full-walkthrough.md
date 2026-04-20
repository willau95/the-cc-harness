# 完整跨设备场景手动走查 — Zero → N-Mac N-Agent

> 目标读者：一台什么都没装的 Mac，只在 GitHub 上看到过 this repo。
> 终点：多台 Mac 协作完成一个真实任务，你只在 dashboard 上操作。
>
> **每一步都告诉你：**
> 1. 在哪台机器、哪个窗口（终端 / dashboard / 浏览器）
> 2. 复制-粘贴的命令或点击动作
> 3. 期望看到的结果（命令输出、UI 变化）
> 4. 如果不符合期望，到哪里排查

---

## 角色设定

- **Mac-A**（你坐的这台）：主控 / CEO。dashboard 只在这台跑。
- **Mac-B**：协作 peer。会跑一个 agent 帮 Mac-A 完成任务。
- **场景**：你在做一个浏览器 3D 小游戏的官网，需要：
  - Mac-A 上：`frontend-dev` agent 写 landing page 代码
  - Mac-B 上：`seo-specialist` agent 研究 2026 年 Google 对浏览器游戏的排名因子，产出 arsenal 条目
  - 二者跨机通信，SEO 把研究结果喂给 frontend-dev
  - 你在 dashboard 上审批 arsenal 条目、监控进度、必要时 pause / 发指示

---

## ACT I — 零起点安装 Mac-A（10 分钟）

### 1.1 前置检查

**在哪里**：Mac-A，打开 `Terminal.app`

```bash
# 确认基础环境
xcode-select -p || xcode-select --install       # Command Line Tools
python3 --version                                # ≥ 3.11
node --version                                   # ≥ 20
```

**期望**：三条命令都返回版本号，不报 "command not found"。

**不符合**：
- 缺 CLT → 弹出图形安装向导，装完再继续
- 缺 Python → `brew install python@3.12`
- 缺 Node → `brew install node@22`

### 1.2 装 Claude Code（harness 的 runtime）

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude login
```

**期望**：浏览器打开 OAuth 页面，登录后终端显示 `✓ Logged in`。

**为什么**：harness 是 Claude Code 的外骨骼，不是替代品。一个 agent = 一个 `claude` 进程。

### 1.3 装 mac-fleet-control（跨机 SSH 的传输层）

```bash
git clone https://github.com/willau95/mac-fleet-control ~/mac-fleet-control
cd ~/mac-fleet-control && ./install.sh
```

**期望**：`fleet-ssh --help` 可以用。

### 1.4 装 Tailscale（跨机 VPN）

```bash
brew install --cask tailscale
open -a Tailscale
# 在 Tailscale GUI 里用同一个账户登录（Mac-A 和 Mac-B 都要用同一个）
tailscale ip -4
# 记下 Mac-A 的 Tailscale IP，例如 100.100.50.1
```

### 1.5 装 harness 本体

```bash
git clone https://github.com/willau95/the-cc-harness ~/the-cc-harness
cd ~/the-cc-harness && ./install.sh
```

**期望**：
```
✓ Installed harness CLI at ~/.local/bin/harness
✓ Built dashboard frontend
✓ Done. Run: harness dashboard
```

确认 PATH 里有：
```bash
which harness
# /Users/xxx/.local/bin/harness
harness --version
# harness 0.2.0
```

### 1.6 启动 dashboard

```bash
harness dashboard
```

**期望**：终端输出 `Uvicorn running on http://127.0.0.1:9999`。

浏览器打开 → `http://127.0.0.1:9999` → 看到一个空 Dashboard（0 agents online、0 events、0 projects）。

---

## ACT II — 把 Mac-B 接进来（10 分钟）

### 2.1 Mac-B 上做一次和 ACT I 一样的事

**在哪里**：Mac-B，`Terminal.app`

把 1.1 ~ 1.5 全做一遍。**不要**在 Mac-B 上跑 `harness dashboard` — dashboard 只在 Mac-A 跑。

记下 Mac-B 的 Tailscale IP（`tailscale ip -4`），例如 `100.100.50.2`，和 Mac-B 的用户名（`whoami`，例如 `bob`）。

### 2.2 回 Mac-A：加 Mac-B 到 fleet

**在哪里**：Mac-A，`Terminal.app`

```bash
# 先确认能 Tailscale ping 通
tailscale ping 100.100.50.2
# Expected: pong from … via direct

# 注册 Mac-B（这会推 SSH 公钥过去；Mac-B 可能弹确认）
fleet-ssh add Mac-B 100.100.50.2 bob

# 测试跨机命令
fleet-ssh Mac-B 'echo hello from $(hostname)'
# Expected: hello from mac-b.local
```

**不符合**：
- `permission denied (publickey)` → 手动加 `~/.ssh/id_ed25519.pub` 到 Mac-B 的 `~/.ssh/authorized_keys`
- `no route to host` → 检查两台都登录了同一 Tailscale 账户

### 2.3 打开 dashboard 的 Machines 页

**在哪里**：Mac-A 浏览器，`http://127.0.0.1:9999/machines`

**期望看到**：
- 顶部 PageHelp 讲解
- 卡片网格里有：
  - `Mac-A`（带 `local` 徽章、绿点）
  - `Mac-B`（绿点、延迟 ~xxx ms、**Harness: not installed**）
- Mac-B 卡上显示警告：_SSH works but harness is missing._

**这时你在 UI 上点**：
- 点 Mac-B 卡上的 **[ Test ]** → bottom-right 弹绿色 toast `Mac-B online · xxxms`
- 点 **[ Bootstrap ]** → toast `Mac-B: peers.yaml updated (1 peers)` （把 Mac-A 的坐标教给了 Mac-B，这样 Mac-B 的 agent 之后能反向发消息过来）

### 2.4 给 Mac-B 装 harness

目前必须在终端跑（UI 不会远程 git clone — 这是故意的，避免 dashboard 对 peer 有任意写权）：

```bash
fleet-ssh Mac-B 'git clone https://github.com/willau95/the-cc-harness ~/the-cc-harness && cd ~/the-cc-harness && ./install.sh'
```

等 1-2 分钟跑完，回 Machines 页点 **Refresh**。

**期望**：Mac-B 卡变成 `Harness: harness 0.2.0`，警告框消失。

### 2.5 Mac-B 上登录 Claude Code

这一步必须本人在 Mac-B 上做（OAuth 需要浏览器）：

```
在 Mac-B 上打开 Terminal：
  claude login
  （按提示在浏览器登录）
```

这是为什么 harness 优于 API-key 方案：你在 Mac-B 上仍然用自己的 Claude Pro/Max/Teams 订阅，不需要 API credits。

---

## ACT III — Spawn 两个 agent 开干（5 分钟）

### 3.1 Spawn frontend-dev 到 Mac-A 本地

**在哪里**：Mac-A 浏览器，`/fleet`

点 **[ + Spawn Agent ]** → 弹出对话框：

| 字段 | 填什么 |
|---|---|
| Role | `frontend-dev` |
| Name | `gamedev1` |
| Folder (absolute) | `/Users/你自己/harness-test/game-dev` |
| Machine | `mads-mac-mini` (local) |
| Initial prompt (可选) | `You are building the landing page for a browser 3D game called NeonRacer. First task will come via mailbox.` |

点 **[ Spawn ]**。

**期望**：
- Dialog 关闭，toast `gamedev1 spawned`
- Fleet 列表多一条 `mads-mac-mini-gamedev1-xxxxx` · `frontend-dev` · 绿点 online

**背后发生了什么**：
1. Dashboard POST `/api/fleet/spawn` → 本地 `harness init` 在新 folder 里搭目录
2. 注册表广播到所有 peer（Mac-B 也收到了这个新 agent 的坐标）
3. Identity + mailbox + checkpoint 文件落盘

**你现在要做的唯一人肉步骤**：打开 Mac-A 一个新终端，启动它的 `claude`：

```bash
cd /Users/你自己/harness-test/game-dev
claude
```

Claude Code 启动，它的 hooks 会自动打心跳、fleet 页面上绿点保持住。不要关这个终端。

### 3.2 Spawn seo-specialist 到 Mac-B

**在哪里**：Mac-A 浏览器，再次点 **[ + Spawn Agent ]**

| 字段 | 填什么 |
|---|---|
| Role | `seo-specialist` |
| Name | `seo1` |
| Folder | `/Users/bob/harness-test/seo-agent`（Mac-B 上的绝对路径） |
| Machine | **Mac-B** ← 这里选 Mac-B，不是 local |

点 **[ Spawn ]**。

**期望**：toast `seo1 spawned on Mac-B`，Fleet 里多一条 `Mac-B-seo1-xxxxx`。

**背后发生了什么**：
- `/api/fleet/spawn` 检测到 machine != local → 走 `remote.spawn_remote_agent`
- fleet-ssh 到 Mac-B 跑 `harness init`
- peers.yaml 再次广播
- 本地 registry 也登记这个 remote agent

**人肉步骤**：在 Mac-B 上（用 Terminal 或 Screen Sharing）：
```bash
cd /Users/bob/harness-test/seo-agent
claude
```

### 3.3 在 Fleet 页看两个绿点

浏览器 `/fleet`：两条 agent，都 online。Machines 页：两台 Mac 的 `Agents` 列都是 1。

---

## ACT IV — 真的跑起来：跨机协作（15–25 分钟）

### 4.1 Dashboard 发第一条指令给 frontend-dev

**在哪里**：Mac-A 浏览器，`/chat`

点 `mads-mac-mini-gamedev1-xxxxx` 进入 chat 线程。在底部输入：

```
任务：为 NeonRacer（浏览器 3D 赛车游戏）写 landing page。

做这两件事：
1. 发消息给 seo1（角色 seo-specialist，在 Mac-B 上）——
   subject: "seo_requirements_request"
   body: "我要给 NeonRacer 做 landing page。帮我找 2026 年 Google
   对浏览器 3D 游戏的 SEO 核心要求，最好是 web.dev 或 Google
   Search Central 的一手资料。产出 arsenal 条目我可以引用。"
2. 等 SEO 回复后，按其建议写 index.html + meta tags。

准备好了就开始。
```

点 **[ Send ]**。

**期望**：
- 你的消息出现在 chat 里（右对齐，human@dashboard）
- 几秒内 `gamedev1` 的 claude 进程收到 hook 通知，开始执行：
  - 调 `send_message` tool → subject "seo_requirements_request" → recipient seo1
  - 跨机路由：本地 mailbox 写不了 Mac-B → 走 fleet-ssh 把 envelope 推到 Mac-B 的 `~/.harness/mailbox/seo1-xxx/inbox.jsonl`

**去哪看是否真的发出去了**：`/events` → 过滤 `gamedev1` → 应该看到 `sent_message`，body 里有 to=`seo1-xxxxx`。

### 4.2 SEO agent 在 Mac-B 收件、研究、回信

这一步完全是 agent 自主：

1. `seo1` 的 claude session 收到 hook 通知 → wake-up pack 里看到新 inbound message
2. `seo1` 调 `WebSearch` + `WebFetch` → 读 web.dev 和 Google Search Central 的 2026 指南
3. 每抓到一个可引用的源，调 `arsenal_add` → 创建 trust=`agent_summary` 的条目
4. 最后调 `send_message` 回给 `gamedev1`，body 里列 arsenal slug + 主要结论

**在哪里看**：`/events` 实时刷新，会依次出现：
- `seo1 · received_message` (刚收到)
- `seo1 · tool_call webSearch ×3`
- `seo1 · arsenal_add` (重复几条)
- `seo1 · sent_message` (给 gamedev1 回信)

### 4.3 你作为 CEO 审核 arsenal 条目

**在哪里**：`/arsenal`

几分钟后，`/arsenal` 页面里会出现 3–5 条 `trust: agent summary`、`on Mac-B` 的条目。

**点进每一条**（Back 按钮、hint 提示、按钮 disabled 状态都在那里）：
- 看内容和 source_refs（web.dev 链接）
- 如果内容靠谱 → **[ Mark verified ]** → badge 变绿色 `human verified`
- 如果 agent 瞎编了 → **[ Retract ]** → `retracted`，之后引用方会看到 trust 降级

**为什么这步重要**：agent 只能产出 `agent_summary`。从 `agent_summary` → `human_verified` 的唯一通道是你。这是 human-in-the-loop 的锚点。

### 4.4 frontend-dev 收到回信 + 实现

回到 `/chat/mads-mac-mini-gamedev1-xxx`，能看到 SEO 的回信（markdown 渲染的要点 + arsenal 链接）。

frontend-dev 收到后应该：
1. 读 arsenal 里被你标 verified 的条目优先（低信任的绕开）
2. 写 `index.html`
3. 运行 lighthouse 自检
4. `send_message` 回 `human@dashboard` 说"做完了"

**查任务进度**：`/tasks` → 应该有 frontend-dev 的一条 task，state 经历 `in_progress` → `awaiting_review`。

### 4.5 人工确认最终交付

frontend-dev 在 `awaiting_review` 状态时，你：

**在 `/tasks`** 里点那条 task（状态 `awaiting_review`）→ 读它的 `next_step` 或交付说明
→ 如果满意，在 chat 里回 "approved, ship it" → agent 把 task 标 `verified` → `done`
→ 如果要改，回 "改这些点：…" → task 回到 `in_progress`

这就是 Iron Law 里的 "nothing ships without human OK"。

---

## ACT V — Pause / Resume / Kill（人在 loop 的硬控制）

### 5.1 发现 agent 跑偏要停下

场景：你看到 seo1 在抓一堆根本不相关的网页 / 在死循环。

**在哪里**：`/fleet` 或 `/agents/seas-imac-3-seo1-xxx`

点 agent 行最右侧的 `…` 菜单或 detail 页的 **[ Pause ]** 按钮。

**发生了什么**：
- dashboard POST `/api/agents/{id}/pause`
- 跨机路由到 Mac-B，在 seo1 的 folder 里 `touch .harness/paused`
- 下一次 seo1 的任何 skill tool call（send_message / arsenal_add / checkpoint_set 等）会在 `_common.py._check_pause()` 短路，返回固定的 paused 响应
- agent 的 claude 仍在跑但不会做任何写操作

**UI 反馈**：badge 变 amber `paused`，按钮变 **[ Resume ]**，events 里多一条 `paused`。

### 5.2 发消息告诉它往哪走

```
(chat 发给 seo1):
我让你停下了。你刚才在抓 reddit 帖子，那不是一手资料。
只看 web.dev / developers.google.com / 官方 Chrome / MDN。
重新来，我 resume 你。
```

### 5.3 Resume

点 **[ Resume ]**（原来 Pause 的位置），sentinel 文件被删除，下一次 tool call 恢复正常。

### 5.4 Kill（终极选项）

如果这个 agent 已经没救了：

- `/agents/xxx` → **[ Kill ]** → 弹确认框
- 确认后：dashboard 调 `harness kill` → 在那台机器上 `pkill -f "claude.*agent_xxx"`（精确 match folder path）
- **身份保留**：agent_id、folder、arsenal、checkpoint 都保留在磁盘。你以后可以同名 respawn 继承历史。

---

## ACT VI — Self-evolution: Proposals（选做，展示最后一块拼图）

1. 某个 agent 在工作中发现了一个更好的做法（例：它发现 fetch Google Search Central 比 MDN 更权威），调 `propose_skill_update` 工具
2. 另一个 `critic` 角色 agent 自动被触发，读 proposal、评估、投 `critic_approved` 或 `rejected`
3. 只有 `critic_approved` 的才出现在 dashboard 的 `/proposals`
4. 你：读 diff、点 **[ Approve ]** → 改动真的被写进 skill 文件；或 **[ Reject ]** → 归档
5. 下次对应 agent spawn 时就会带上新版 skill

---

## 当前完成度对照表

| Requirement | 状态 | 可测路径 |
|---|---|---|
| Zero-install onboarding (Mac-A) | ✅ | `./install.sh` 一步 |
| Install on Mac-B via fleet-ssh | ⚠️ | 需要手动 `fleet-ssh Mac-B 'git clone + install'`（dashboard 一键装 peer harness 是 P2） |
| Cross-machine spawn | ✅ | `/fleet` → Spawn Agent → machine dropdown |
| Cross-machine messaging (chat, A→B) | ✅ | 已端到端验证（Opus 4.7 ↔ Opus 4.5） |
| Arsenal aggregation across peers | ✅ | `/arsenal` 自动合并 |
| Arsenal trust routing to owning peer | ✅ | Mark verified 现在真的写到正确的机器 |
| Pause / Resume / Kill (cross-machine) | ✅ | 走 sentinel + fleet-ssh 组合 |
| Events aggregated view | ⚠️ | 目前只看本地 events；跨机 events 合并待做 |
| Tasks FSM（proposed→done） | ✅ | schema + transitions 在位 |
| Proposals critic pipeline | ⚠️ | schema 完整，critic agent 自动触发链路待接 |
| PreCompact digest + wake-up pack | ✅ | hook 落盘，SessionStart `additionalContext` 注入已验证 |
| Machines management UI | ✅ | `/machines` — 新加的这个 |
| Dashboard-only operation (no terminal) | ⚠️ | 90% — 只有首次 `claude` 启动 + peer 装机需要终端 |

**"90% dashboard-only"** 的意思：
- 必须在终端做的事：第一次 `claude login`（OAuth 要浏览器）、`fleet-ssh Mac-B 'install'` 推装包
- 可以在 dashboard 做：spawn / pause / resume / kill / 发指令 / 审 arsenal / 批 proposal / 看 events / 看 tasks / 看 projects / 管 machines

---

## 常见问题排查

| 症状 | 先查 |
|---|---|
| `/fleet` 空着 | `harness status` 看本地 registry 有没有条目；登录了 claude 吗 |
| agent 绿点变灰 | `/events` 看有没有 heartbeat；超过 30 分钟无心跳算 stale |
| 跨机 spawn 失败 | `/machines` 页看那台 peer 的 Harness 列；`fleet-ssh PeerName 'harness --version'` 直接测 |
| arsenal 条目点 Mark verified 无变化 | 先看是不是 `on PeerName` 条目，peer 需要 harness ≥ 0.1.1 |
| chat 消息发出去没反应 | agent 的 claude 进程活着吗？PreCompact hook 在 inbox 堆积时会自动唤醒，但 claude 必须在跑 |
| PreCompact digest 没写 | `~/.harness/logs/hook.log` 看 hook 是否触发；PATH 问题占 90% |

---

## 下一步（Phase D 之后的 P1）

1. **Dashboard 一键给 peer 装 harness**（替代 ACT II.2.4）
2. **跨机 events 合并视图**（用和 arsenal 一样的 aggregate 套路）
3. **Critic agent 自动触发链路**（proposal → critic 派发 → 结果回传）
4. **Claude login 代理**（dashboard 触发 OAuth、代填到 peer）
5. **Budget/quota 监控**（每个 agent 的 token 消耗实时展示）
