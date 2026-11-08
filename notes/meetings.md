# Meeting notes

Newest first. Each meeting: who, what was said, decisions, action items.
Open action items also go on the Task board.

---

## Jake – 8 Oct 2026

**Points**
- Next step: define goals, requirements and a Gantt chart.
- Jake can act as supervisor from EE and will contact Tijs Donkers to be the official supervisor.
- Amritam might be interested if the project uses event cameras.

**Action items**
- [x] Write a project draft / proposal (sent to Jake)
- [x] Jake contacts Tijs Donkers (Tijs agreed)

---

## Rene (head of robotics) – advice

> Date to check: the notes say 29 Sept, the project summary says 12 Oct.

**Advice**
- Use the current hardware: the IR touch frame and the differential actuator.
- Refresh rate and latency are not a big problem; compensate in software with prediction.
- If the IR frame proves a serious limit, add another sensor or camera.
- Portability, robustness and not breaking easily matter long-term, but are not my task now.
- First write a project proposal: requirements, goals, checkpoints, milestones.
- Need a daily supervisor, maybe from RBT or CST.
- Build on previous research instead of reinventing it.
- A good BEP needs academic scope and depth. Whether the robot plays matters less than the research question, especially for a 9.
- Keep asking "why" during the project.
- Talk to people: Elise for the actuator, Jordy for perception and the world model.

**Prepared agenda for this meeting**
1. Jordy's paper covers static localization and self-calibration; what comes next? Are there latency measurements?
2. Pitch: end goal is a robot a human can play against, with a research question inside that integration work.
3. Candidate question: does velocity estimation plus delay-compensated prediction improve interception over the paper's reactive alignment, as ball speed increases? An end-to-end latency budget as a supporting result.
4. Deliverable order: a goalie that reliably blocks shots, then more rods, then the kick. Early cutoff for hardware work to leave weeks for measurements and writing.
5. Which version to target: basic, robust in one place, or transportable. (Outcome: basic, on existing hardware.)
6. What would make this an excellent BEP rather than just a working one?
7. Timeline: Jake approaches the EE supervisor, question locked end of October, proposal in by early December.

---

## Jordy – 14 Sept 2026

**Points**
- Explained earlier work on similar projects.
- Three possible approaches: basic; robust in one place; robust and also mobile and easily transportable.
- Talk to more people to find the requirements: Peter, Ruud, Harrie, Rene.
- A combined BEP with another student is possible.
- On vacation, back at the end of October.

**Action items**
- [ ] Talk to Peter, Ruud and Harrie about requirements
- [x] Talk to Rene
- [ ] Decide on a combined BEP (e.g. with an ME student)

---

## Jake – 8 Sept 2026

**Points**
- Very positive about the idea; a BEP can be done on this.
- Needs a supervisor from EE, maybe one from ME, and support from the table's owners.
- Make a concrete description of the BEP idea (proposal).
- I can start the BEP unofficially before February.

**Action items**
- [x] Write a concrete proposal

---

## Early project notes

- Existing foosball table with an IR touch frame for ball sensing.
- The IR frame has high latency and **filtered output**, so it needs good software (ball perception, prediction) to be usable.
- Existing differential actuator setup that moves the rod linearly and rotates it.
- My tasks: ball perception, ball prediction, closed-loop control of the rod drive (minimize settling time), and integrating mechanics, electronics and software.
- Early goal idea: ball perception detects balls accurately up to a maximum speed of x m/s (x still to set).
