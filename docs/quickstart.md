# Quickstart

## 1. Install on your first Mac

```bash
git clone https://github.com/willau95/the-cc-harness.git
cd the-cc-harness
./install.sh
```

This does: `brew install syncthing` + `pip install -e .` + `harness join`.

## 2. Start Syncthing (once per machine; keep running)

```bash
syncthing      # web UI on http://localhost:8384
```

In the Syncthing UI: add `~/.harness/` as a shared folder. On your second
Mac, install the same way and exchange device IDs via the UI.

## 3. Scaffold your first agent

```bash
cd ~/projects/my-research-project
harness init --role researcher --name kevin
```

This creates `.harness/agent.yaml`, `.harness/checkpoint.jsonl`, `CLAUDE.md`,
`.claude/settings.local.json` with hooks, and `.claude/skills/harness*` copied in.

## 4. Start Claude Code

```bash
claude
```

The SessionStart hook fires and injects a wake-up pack (first session will just
say "I am researcher kevin, first start, awaiting instruction").

## 5. Ask it to do something

```
> 帮我找一篇最近的 Claude Code hooks 教程,存进 arsenal
```

The agent should:
1. Create a task via `checkpoint_update --create`
2. Use native `WebSearch` + `WebFetch`
3. `arsenal_add` with the URL as source_ref
4. Transition task to `AWAITING_REVIEW`

## 6. See the fleet

```bash
harness dashboard
```

Browser opens `http://localhost:9999`. You see:
- Metric cards (online / zombies / pending proposals / projects)
- Left: fleet (click an agent to drill in)
- Middle: selected agent's active tasks + inbox + events
- Right: global event feed + proposals queue + projects

## 7. Talk between machines

On Mac A (orchestrator folder):
```
harness send researcher-kevin-abc12345 find_hooks "find Claude Code hooks tutorial"
```

On Mac B (researcher folder), within seconds (after Syncthing sync):
the researcher's inbox will have the message. Next Claude Code turn, it can
`receive_messages` to pick it up.

## Troubleshooting

### `harness init` says "Role template not found"
Check `harness roles list`. Available: orchestrator, researcher, critic,
frontend-dev, seo-specialist. You can add more in `roles/`.

### Hooks don't fire
Verify `.claude/settings.local.json` has the hooks registered. Run manually
to test:
```bash
bash hooks/session_start.sh $PWD   # should print wake-up pack
bash hooks/on_compact.sh $PWD      # should write a digest file
```

### Dashboard shows nothing
Make sure you've run `harness init` at least once in some folder.
Check `ls ~/.harness/` — should have `registry.jsonl`, `heartbeats/`, etc.

### Messages not crossing machines
Check Syncthing UI: `~/.harness/` folder must be set up and shared. After a
sync, the `mailboxes/<other-agent>/inbox.jsonl` on this machine should show
your sent lines.
