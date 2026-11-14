# BEP – Foosball-playing robot

Bachelor End Project (TU/e) on a foosball table with an IR touch frame (USB HID) for ball sensing and a differential BLDC drive per rod over EtherCAT. The research question asks what limits interception performance (sensing latency, prediction error or actuator response) and how much compensating the dominant limit improves the block rate as ball speed increases. Runs Feb–Jun 2027, 10 credits.

## Where things live

| Where | What |
|---|---|
| Task board (GitHub Projects "Task board") | What's left to do |
| `notes/journal/` | Daily log of what I did and found |
| `notes/meetings.md` | Supervisor meetings |
| `notes/decisions.md` | Decisions and why |
| `notes/literature.md` | Related work |
| `experiments/` | Every measurement: setup, data, result |
| `planning/` | Proposal versions and the living plan |
| `src/` | Code (ROS 2) |
| `paper/` | Paper (from March) |

## Habits

- Put the issue number in commit messages, e.g. `IR raw dump results (#1)`.
- Every measurement gets its own folder in `experiments/`.
