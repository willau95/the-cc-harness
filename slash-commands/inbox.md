---
description: Read any new messages waiting in this agent's inbox and respond to them.
---

Check your inbox immediately. Run:

```
python3 .claude/skills/harness/tools/receive_messages.py
```

For each unread message:
1. Read the `from` / `subject` / `body` carefully.
2. If it's a task or instruction, address it before resuming your previous
   work. Set a checkpoint task with `checkpoint_set.py` if it's nontrivial.
3. If it's a question, answer via `send_message.py` back to the sender.
4. If it's blocker-relief (human unblocking you), update the blocked task's
   state and continue.

Do not report "no messages" if the inbox was empty — just say so briefly and
return to what you were doing. Do not invent messages.
