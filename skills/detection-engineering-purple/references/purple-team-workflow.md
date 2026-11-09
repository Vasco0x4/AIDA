# Purple-team workflow — emulate → detect → tune → measure

The operational loop for turning attacker techniques into validated detections.
Defensive; inherits `safe-testing-doctrine`. Emulation runs **only** in a lab or
a deconflicted, authorized environment with benign atomics.

## 0. Plan the exercise (before touching a keyboard)

Purple teaming is red + blue working **together in real time** (as opposed to a
black-box red-team test where blue is unaware). SANS' Purple Team Exercise
Framework (PTEF) frames it as a repeatable, threat-intel-driven cycle.

- **Pick a threat model, not random techniques.** Choose an adversary or a set of
  ATT&CK techniques relevant to the org (from CTI, prior incidents, crown-jewel
  risk, or an emulation plan like MITRE's APT3/APT29/FIN6 plans).
- **Build the technique list** as ATT&CK IDs. Map each to the offensive skill in
  this base that describes it (e.g. T1558.003 Kerberoasting ->
  `active-directory-attack-paths`).
- **Deconfliction & RoE.** Agree scope, window, start/stop signals, a safe-word to
  abort, who watches the SIEM, and how findings are logged. In production the SOC
  must know an *exercise* is running so an emulated technique isn't escalated as a
  real breach (and vice-versa — a real intrusion during the window isn't dismissed
  as "just the exercise"). Keep an out-of-band channel.
- **Success criteria.** For each technique define what "detected" means: telemetry
  present? alert fired? correct severity? time-to-detect acceptable?

## 1. Emulation tooling

### Atomic Red Team (Red Canary)
Open-source library of small, single-technique tests ("atomics") mapped directly
to ATT&CK. Each atomic is a focused, minutes-long test with documented
prerequisites, an execution command, and a **cleanup** step. Best for *precise,
per-technique* validation — "does T1003.001 LSASS dump fire my rule?".

- Structure: one YAML per technique (`T1055.yaml`) with numbered tests, each with
  `executor` (command-prompt/powershell/sh/bash), `input_arguments`, and
  `cleanup_command`.
- Runner: `Invoke-AtomicRedTeam` (PowerShell) —
  `Invoke-AtomicTest T1558.003 -GetPrereqs` then `Invoke-AtomicTest T1558.003`,
  and **always** `Invoke-AtomicTest T1558.003 -Cleanup` afterwards.
- Purple use: run one atomic, watch the SIEM, record telemetry + alert, tune,
  re-run. Keep runs benign (test SPNs, canary files, spawned `calc`/`whoami`).

### MITRE Caldera
Automated adversary-emulation *platform* — an agent (implant) + a planner that
chains ATT&CK-mapped "abilities" into an operation. Ships hundreds of procedures
and can import the Atomic library (via a plugin). Best for *chained, end-to-end*
scenarios ("run a whole APT29-style operation and see which stages we catch").

- Native ATT&CK mapping: operations export back to ATT&CK for coverage reporting.
- Purple use: run a scripted adversary profile against a lab range, then compare
  the techniques executed vs the techniques alerted.

### Choosing
- **Atomic Red Team** = surgical single-technique unit tests, fast, easy cleanup —
  the default for detection unit-testing.
- **Caldera** = multi-step campaign / kill-chain emulation, automation, agents.
- Other tools in the space: Red Canary's stimulus + others; commercial BAS
  (Breach & Attack Simulation) platforms do this continuously.

## 2. Observe telemetry (the step teams skip)

After emulating, **first ask "was anything logged at all?"** before asking "did a
rule fire?". Open the raw telemetry (Sysmon Operational log, Security log,
EDR raw events, cloud trail) and find the events the technique should have
produced.

- **No events** = **telemetry gap**. Stop — fix collection (enable the audit
  policy / Sysmon rule / cloud log / forwarder), then re-emulate. See
  `logging-and-sigma.md`.
- **Events present** = proceed to detection assessment. Note exactly which event
  IDs / fields carry the signal — that becomes the Sigma `logsource` + `detection`.

## 3. Assess detection

Did an existing rule fire? Check the SIEM alerts for the emulation window.
- **Fired, correct** — record as covered; validate severity & time-to-detect.
- **Fired, but noisy/wrong** — tune (step 5).
- **Didn't fire** — detection gap; write a new rule (step 5).

## 4–5. Write / tune the detection

Write it as **Sigma** (portable, vendor-neutral) targeting the *behavior* you
observed, then convert to your SIEM. Full mechanics in `logging-and-sigma.md`.
Concrete per-technique logic in `detections-for-base-attacks.md`.

- Anchor on the highest-Pyramid-of-Pain signal available (behavior > tool >
  artifact > IOC) so the rule survives attacker changes.
- Write the rule, then immediately consider false positives: what legitimate admin
  activity looks identical? Add `filter`/exclusion selections and a
  `condition: selection and not filter`.

## 6. Re-test

Re-run the *same atomic*. Confirm the rule fires. Then run a couple of benign
"lookalike" legitimate actions to check the FP rate. Iterate until the rule fires
on the technique and stays quiet on legitimate use. Record the final rule + the
atomic that validates it — that pairing is a **detection unit test**.

## 7. Measure coverage & report

### ATT&CK Navigator
Web app for annotating the ATT&CK matrix as a **heatmap layer**. Build layers for:
- **Emulated** — techniques you ran.
- **Telemetry** — techniques you have logging for.
- **Detection** — techniques with a validated, firing rule.
Score/colour each cell; the gap between "emulated" and "detection" layers is your
work backlog. Layers can be combined (e.g. detection layer minus telemetry layer
reveals techniques you alert on but can't actually see — brittle rules).

### DeTT&CT (Detect Tactics, Techniques & Combat Threats)
Rijksoverheid/MB-authored framework + tooling to score **data-source quality and
visibility**, then derive detection coverage, all as ATT&CK Navigator layers. It
forces the honest question the Navigator alone hides: *how good is the logging
behind each "covered" technique?* Use it to:
- Inventory data sources (per ATT&CK data source / component) and rate their
  quality, completeness, retention, and consistency.
- Produce a **visibility** layer (what can you even see) and a **detection** layer
  (what do you alert on), and compare against **threat-actor** layers to prioritize.

### Reporting the outcome (feeds `security-reporting`)
Deliver, per technique:
- ATT&CK ID + name, mapped offensive skill, emulation used (atomic/Caldera ability).
- Telemetry result (logged? which events?) — flag gaps as findings.
- Detection result (rule fired? new rule written? FP notes).
- Pyramid-of-Pain level of the detection (behavior vs IOC = durability).
- Time-to-detect and recommended severity.
- **Gap findings** with remediation: "Enable *Audit Directory Service Access* +
  deploy Sigma rule X to detect DCSync (T1003.006); currently no telemetry."

A good purple-team report is a coverage heatmap + a prioritized backlog of
logging and detection improvements, each with a validating atomic so the blue
team can regression-test after fixing.

## Maturity progression
1. **Ad-hoc** — run atomics, eyeball logs.
2. **Repeatable** — technique list + Navigator layers, tracked per exercise.
3. **Detection-as-code** — rules in git, tested against atomics in CI (see
   `logging-and-sigma.md`), coverage tracked over time.
4. **Continuous** — automated emulation on a schedule (Caldera/BAS) with alerting
   on *coverage regressions*, not just intrusions.
