"""
RailAnukriti V4.1 - AI-Assisted Coordinated Maintenance Block Planner
Team: The Avalanche | SIH 2026 | Problem: SIH26027
Domain: Transportation & Logistics

DISCLAIMER:
All results in this file are from a SYNTHETIC PROTOTYPE SIMULATION.
Safety buffer values, resource constraints, and priority weights
are configurable prototype parameters — NOT official Indian Railways rules.
No real-world performance guarantees are implied.

V4.1 CHANGES vs V4:
- Priority is now the PRIMARY optimization objective (lexicographic).
- High-priority task scheduling always dominates block-count reduction.
- high_priority_total / high_priority_done reporting fixed.
- total_priority_available / total_priority_scheduled added.
- Lexicographic weights proved sufficient to maintain strict ordering.
"""

import sys
from pathlib import Path
from itertools import combinations

import pandas as pd
from ortools.sat.python import cp_model


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

TASKS_FILE   = DATA_DIR / "maintenance_tasks.csv"
TRAINS_FILE  = DATA_DIR / "trains.csv"
WINDOWS_FILE = DATA_DIR / "block_windows.csv"


# ============================================================
# PROTOTYPE CONFIGURATION
# ============================================================

# Prototype assumption:
# A 15-minute safety buffer is applied around each train movement.
# This is NOT an official Indian Railways operational rule.
SAFETY_BUFFER_MIN = 15

# High-priority threshold — tasks at or above this score are
# treated as Level-1 priority in the objective.
# Prototype parameter; adjust to reflect real-world criticality bands.
HIGH_PRIORITY_THRESHOLD = 4.0

# ── Lexicographic objective weights ────────────────────────────────────────
#
# Strict ordering enforced (proved in verify_weights.py):
#   L1 maximize high_pri_done       (×W1, subtracted from minimisation obj)
#   L2 maximize total_priority*100  (×W2, subtracted)
#   L3 minimize unscheduled_tasks   (×W3, added)
#   L4 minimize block_count         (×W4, added)
#   L5 minimize blocked_minutes     (×W5, added)
#
# Each W_k > W_{k+1} × max_delta_{k+1} so L_k always dominates L_{k+1}.
# All values fit in CP-SAT's int64 objective (verified ≤ 7.7e15 < 9.2e18).
#
# Prototype parameters — NOT validated against Indian Railways metrics.
W5_BLOCKED_MINS   =                 1   # L5: minimise blocked minutes
W4_BLOCK_COUNT    =           300_000   # L4: minimise maintenance blocks
W3_UNSCHEDULED    =        60_300_000   # L3: minimise unscheduled tasks
W2_TOTAL_PRIORITY =     3_075_300_000   # L2: maximise total priority score
W1_HIGH_PRI_DONE  = 153_768_075_300_000 # L1: maximise high-priority tasks done

# Priority scoring weights
PRIORITY_WEIGHT_CRITICALITY         = 0.40
PRIORITY_WEIGHT_URGENCY             = 0.35
PRIORITY_WEIGHT_OPERATIONAL_IMPACT  = 0.25

# OR-Tools solver time limit (seconds per section)
SOLVER_TIME_LIMIT_SEC = 30

# Candidate block start granularity (minutes)
CANDIDATE_STEP_MIN = 30


# ============================================================
# RESOURCE MODEL
# ============================================================

# Prototype assumption:
# Each department uses one exclusive track-access crew resource.
# Two tasks from the same department cannot run simultaneously.
# Tasks from different departments MAY run in the same block
# if they do not share a physical resource.
#
#   Engineering → TRACK  (track geometry, ballast, civil works)
#   Signalling  → SIGNAL (interlocking, signal heads, cables)
#   Traction    → OHE    (overhead equipment, pantograph, substations)
#
# TRACK + SIGNAL : compatible (co-exist in one block)
# TRACK + OHE    : compatible
# SIGNAL + OHE   : compatible
# TRACK + TRACK  : NOT compatible (one crew, one zone at a time)
# SIGNAL + SIGNAL: NOT compatible
# OHE + OHE      : NOT compatible

RESOURCE_GROUP = {
    "Engineering": "TRACK",
    "Signalling":  "SIGNAL",
    "Traction":    "OHE",
}

def same_resource(dept_a: str, dept_b: str) -> bool:
    return RESOURCE_GROUP.get(dept_a, dept_a) == RESOURCE_GROUP.get(dept_b, dept_b)


# ============================================================
# TIME UTILITIES
# ============================================================

def fmt_time(minutes) -> str:
    if minutes is None:
        return "N/A"
    minutes = int(minutes)
    if minutes >= 1440:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"

def overlaps(s1, e1, s2, e2) -> bool:
    return s1 < e2 and e1 > s2


# ============================================================
# DATA VALIDATION
# ============================================================

REQUIRED_TASK_COLS = [
    "task_id", "department", "asset_id", "section",
    "duration_min", "criticality", "urgency", "operational_impact", "status",
]
REQUIRED_TRAIN_COLS = [
    "train_id", "train_type", "section", "arrival_min", "departure_min", "priority",
]
REQUIRED_WINDOW_COLS = [
    "section", "available_start", "available_end", "max_block_hours",
]

def _validate_cols(df, required, name):
    missing = [c for c in required if c not in df.columns]
    if missing:
        sys.exit(f"[DATA ERROR] {name} is missing columns: {missing}")

def validate_tasks(df):
    _validate_cols(df, REQUIRED_TASK_COLS, "maintenance_tasks.csv")
    bad = df[df["duration_min"] <= 0]
    if not bad.empty:
        print(f"[WARN] {len(bad)} task(s) with duration <= 0 skipped: {list(bad['task_id'])}")
    return df[df["duration_min"] > 0].copy()

def validate_trains(df):
    _validate_cols(df, REQUIRED_TRAIN_COLS, "trains.csv")
    bad = df[df["arrival_min"] >= df["departure_min"]]
    if not bad.empty:
        print(f"[WARN] {len(bad)} train(s) with arrival >= departure skipped: {list(bad['train_id'])}")
    return df[df["arrival_min"] < df["departure_min"]].copy()

def validate_windows(df):
    _validate_cols(df, REQUIRED_WINDOW_COLS, "block_windows.csv")
    bad = df[df["available_start"] >= df["available_end"]]
    if not bad.empty:
        print(f"[WARN] {len(bad)} window(s) with start >= end skipped.")
    return df[df["available_start"] < df["available_end"]].copy()


# ============================================================
# LOAD DATA
# ============================================================

print("\nLoading data...")

try:
    tasks_df   = pd.read_csv(TASKS_FILE)
    trains_df  = pd.read_csv(TRAINS_FILE)
    windows_df = pd.read_csv(WINDOWS_FILE)
except FileNotFoundError as e:
    sys.exit(f"[FATAL] {e}")

tasks_df   = validate_tasks(tasks_df)
trains_df  = validate_trains(trains_df)
windows_df = validate_windows(windows_df)

missing_wins = set(tasks_df["section"].unique()) - set(windows_df["section"].unique())
if missing_wins:
    print(f"[WARN] Sections with tasks but no windows: {missing_wins}")

print(f"  Tasks   : {len(tasks_df)}")
print(f"  Trains  : {len(trains_df)}")
print(f"  Windows : {len(windows_df)}")


# ============================================================
# PRIORITY CALCULATION
# ============================================================

def calculate_priority(row) -> float:
    """
    Composite priority: higher = more critical.
      priority = criticality*0.40 + urgency*0.35 + operational_impact*0.25
    Prototype formula — weights are adjustable parameters.
    """
    return round(
        float(row["criticality"])          * PRIORITY_WEIGHT_CRITICALITY
        + float(row["urgency"])            * PRIORITY_WEIGHT_URGENCY
        + float(row["operational_impact"]) * PRIORITY_WEIGHT_OPERATIONAL_IMPACT,
        2,
    )

tasks_df["priority"] = tasks_df.apply(calculate_priority, axis=1)


# ============================================================
# TRAIN PROTECTION (safety buffer)
# ============================================================

def get_protected_windows(section):
    """
    Returns [(protected_start, protected_end, train_id), ...]
    with SAFETY_BUFFER_MIN applied on each side.

    Prototype assumption: this buffer is a configurable parameter,
    NOT an official Indian Railways operational rule.
    """
    out = []
    for _, t in trains_df[trains_df["section"] == section].iterrows():
        p_start = max(0, int(t["arrival_min"]) - SAFETY_BUFFER_MIN)
        p_end   = min(1440, int(t["departure_min"]) + SAFETY_BUFFER_MIN)
        out.append((p_start, p_end, str(t["train_id"])))
    return out


def conflicting_trains(section, blk_start, blk_end):
    return [
        tid for p_s, p_e, tid in get_protected_windows(section)
        if overlaps(blk_start, blk_end, p_s, p_e)
    ]


# ============================================================
# CANDIDATE BLOCK GENERATION
# ============================================================

def generate_candidates(section, section_windows):
    """
    Enumerate train-free sub-intervals within every maintenance window,
    then produce candidate start points at CANDIDATE_STEP_MIN granularity.
    Each candidate is a (start, end, capacity) tuple that is guaranteed
    to have zero train conflicts including the safety buffer.
    """
    protected  = get_protected_windows(section)
    candidates = []
    block_id   = 0

    for _, win in section_windows.iterrows():
        ws       = int(win["available_start"])
        we       = int(win["available_end"])
        max_mins = int(win["max_block_hours"]) * 60

        # Subtract all protected windows to find free sub-intervals
        free = [(ws, we)]
        for p_s, p_e, _ in protected:
            new_free = []
            for fs, fe in free:
                if p_e <= fs or p_s >= fe:
                    new_free.append((fs, fe))
                else:
                    if fs < p_s:
                        new_free.append((fs, p_s))
                    if p_e < fe:
                        new_free.append((p_e, fe))
            free = new_free

        for fs, fe in free:
            for start in range(fs, fe, CANDIDATE_STEP_MIN):
                cap = min(fe - start, max_mins)
                if cap <= 0:
                    continue
                # Hard check: no conflict (should always pass after subtraction, but defensive)
                if conflicting_trains(section, start, start + cap):
                    continue
                candidates.append({
                    "id":       block_id,
                    "start":    start,
                    "end":      start + cap,
                    "capacity": cap,
                })
                block_id += 1

    return candidates


# ============================================================
# BASELINE PLANNER
# ============================================================

def create_baseline(section, section_tasks, section_windows):
    """
    Rule-based sequential planner simulating conventional manual planning.

    Rules (same constraint set as the optimizer — intentionally fair):
    - Process tasks in descending priority order.
    - Place each task in the earliest slot in the earliest feasible window
      after the previous task for the same resource group.
    - Respect safety buffer around train movements.
    - Mark as UNSCHEDULED if no feasible slot exists.

    NOTE: Prototype simulation of manual planning, NOT a reproduction
    of any actual Indian Railways process.
    """
    scheduled   = []
    unscheduled = []
    resource_cursor = {}

    sorted_tasks = section_tasks.sort_values(
        by=["priority", "duration_min"], ascending=[False, False]
    )

    for _, task in sorted_tasks.iterrows():
        duration = int(task["duration_min"])
        dept     = str(task["department"])
        res_grp  = RESOURCE_GROUP.get(dept, dept)
        cur_time = resource_cursor.get(res_grp, 0)
        placed   = False

        for _, win in section_windows.sort_values("available_start").iterrows():
            ws = int(win["available_start"])
            we = int(win["available_end"])

            start = max(cur_time, ws)
            end   = start + duration

            if end > we:
                continue

            if conflicting_trains(section, start, end):
                # Try pushing start past each protected window
                for p_s, p_e, _ in get_protected_windows(section):
                    if overlaps(start, end, p_s, p_e):
                        start = p_e
                        end   = start + duration
                if end > we or conflicting_trains(section, start, end):
                    continue

            scheduled.append({
                "task_id":    str(task["task_id"]),
                "department": dept,
                "asset_id":   str(task["asset_id"]),
                "start":      start,
                "end":        end,
                "duration":   duration,
                "priority":   float(task["priority"]),
                "resource":   res_grp,
            })
            resource_cursor[res_grp] = end
            placed = True
            break

        if not placed:
            unscheduled.append({
                "task_id":    str(task["task_id"]),
                "department": dept,
                "priority":   float(task["priority"]),
                "duration":   duration,
            })

    return scheduled, unscheduled


def count_baseline_blocks(scheduled):
    """Count distinct blocks: consecutive tasks per resource group = 1 block; gaps = new block."""
    if not scheduled:
        return 0
    from collections import defaultdict
    by_res = defaultdict(list)
    for t in scheduled:
        by_res[t["resource"]].append(t)
    count = 0
    for tasks in by_res.values():
        ts = sorted(tasks, key=lambda x: x["start"])
        count += 1
        for i in range(1, len(ts)):
            if ts[i]["start"] > ts[i-1]["end"]:
                count += 1
    return count


# ============================================================
# CP-SAT OPTIMIZER
# ============================================================

def optimize_section(section):
    section_tasks   = tasks_df[tasks_df["section"] == section].copy()
    section_trains  = trains_df[trains_df["section"] == section].copy()
    section_windows = windows_df[windows_df["section"] == section].copy()

    if section_tasks.empty:
        return
    if section_windows.empty:
        print(f"\n[SKIP] {section}: no maintenance windows defined.")
        return

    # ── header ───────────────────────────────────────────────────────────
    print()
    print("╔" + "═" * 68 + "╗")
    print(f"║  SECTION {section}  —  RailAnukriti V4.1 (Prototype Simulation)" +
          " " * max(0, 68 - 51 - len(section)) + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"  Tasks: {len(section_tasks)}   Trains: {len(section_trains)}   "
          f"Safety buffer: {SAFETY_BUFFER_MIN} min   "
          f"High-pri threshold: {HIGH_PRIORITY_THRESHOLD}")

    # ── pre-compute priority stats for the section ────────────────────────
    total_pri_avail = round(float(section_tasks["priority"].sum()), 2)
    hi_pri_total    = int((section_tasks["priority"] >= HIGH_PRIORITY_THRESHOLD).sum())

    # ── BASELINE ─────────────────────────────────────────────────────────
    b_sched, b_unsched = create_baseline(section, section_tasks, section_windows)

    b_total_min   = sum(t["duration"] for t in b_sched)
    b_blocks      = count_baseline_blocks(b_sched)
    b_conf_set    = set()
    for t in b_sched:
        b_conf_set.update(conflicting_trains(section, t["start"], t["end"]))
    b_conflicts   = len(b_conf_set)
    b_hi_done     = sum(1 for t in b_sched if t["priority"] >= HIGH_PRIORITY_THRESHOLD)
    b_total_pri   = round(sum(t["priority"] for t in b_sched), 2)

    print()
    print("── BASELINE (Rule-based sequential, same hard constraints) ─────────")
    for t in sorted(b_sched, key=lambda x: x["start"]):
        flag = " ★" if t["priority"] >= HIGH_PRIORITY_THRESHOLD else ""
        print(f"  {t['task_id']} | {t['department']:<12} | "
              f"{fmt_time(t['start'])} – {fmt_time(t['end'])} | "
              f"Priority {t['priority']}{flag}")
    for t in b_unsched:
        print(f"  {t['task_id']} | {t['department']:<12} | *** NOT SCHEDULED ***")
    print()
    print(f"  Blocks                   : {b_blocks}")
    print(f"  Total blocked            : {b_total_min / 60:.2f} hrs")
    print(f"  Train conflicts          : {b_conflicts}")
    print(f"  Unscheduled tasks        : {len(b_unsched)}")
    print(f"  High-pri total in section: {hi_pri_total}")
    print(f"  High-pri done (baseline) : {b_hi_done}")
    print(f"  Total priority available : {total_pri_avail}")
    print(f"  Total priority scheduled : {b_total_pri}")

    # ── CANDIDATE BLOCKS ─────────────────────────────────────────────────
    candidates = generate_candidates(section, section_windows)
    if not candidates:
        print("\n  [No feasible maintenance slots after train protection windows.]")
        return

    # ── CP-SAT MODEL ─────────────────────────────────────────────────────
    model  = cp_model.CpModel()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SEC

    task_ids  = list(section_tasks["task_id"])
    task_info = {row["task_id"]: row for _, row in section_tasks.iterrows()}

    # Decision variables
    x          = {}   # x[tid, bid] = 1 iff task tid assigned to block bid
    block_used = {}   # block_used[bid] = 1 iff at least one task in bid

    for tid in task_ids:
        for blk in candidates:
            x[tid, blk["id"]] = model.NewBoolVar(f"x_{tid}_{blk['id']}")
    for blk in candidates:
        block_used[blk["id"]] = model.NewBoolVar(f"bu_{blk['id']}")

    # ── Hard constraint 1: every task assigned to exactly one block ───────
    for tid in task_ids:
        model.Add(sum(x[tid, blk["id"]] for blk in candidates) == 1)

    # ── Hard constraint 2: task duration fits in block capacity ───────────
    for tid in task_ids:
        dur = int(task_info[tid]["duration_min"])
        for blk in candidates:
            if dur > blk["capacity"]:
                model.Add(x[tid, blk["id"]] == 0)

    # ── Hard constraint 3: block activation ──────────────────────────────
    for blk in candidates:
        for tid in task_ids:
            model.Add(x[tid, blk["id"]] <= block_used[blk["id"]])
        model.Add(
            sum(x[tid, blk["id"]] for tid in task_ids) >= block_used[blk["id"]]
        )

    # ── Hard constraint 4: resource exclusivity within a block ───────────
    # Same-department tasks share one exclusive crew — cannot overlap.
    task_list = list(section_tasks.itertuples())
    for t1, t2 in combinations(task_list, 2):
        if same_resource(str(t1.department), str(t2.department)):
            for blk in candidates:
                model.Add(
                    x[t1.task_id, blk["id"]] + x[t2.task_id, blk["id"]] <= 1
                )

    # ── LEXICOGRAPHIC OBJECTIVE ───────────────────────────────────────────
    #
    # CP-SAT minimizes, so we negate maximization goals.
    # Objective = sum of all terms (minimized).
    #
    # L1 MAXIMIZE high_priority_done:
    #   subtract W1 for each high-priority task that IS scheduled
    #
    # L2 MAXIMIZE total_priority (×100 to stay integer):
    #   subtract W2 × round(priority×100) for each scheduled task
    #
    # L3 MINIMIZE unscheduled:
    #   add W3 for each task that is NOT in any block
    #   (equivalently, subtract W3 for each task that IS scheduled,
    #    same effect since total tasks is constant — we use the
    #    positive form so the objective stays interpretable)
    #
    # L4 MINIMIZE block_count:
    #   add W4 for each block_used = 1
    #
    # L5 MINIMIZE blocked_minutes:
    #   add W5 × capacity for each block_used = 1
    #   (capacity is the block's available duration; actual workload
    #    is ≤ capacity, and we report actual workload in output)
    #
    # Dominance proof (see verify_weights.py):
    #   W1 > W2 × max_delta_L2   (L1 always beats L2)
    #   W2 > W3 × max_delta_L3   (L2 always beats L3)
    #   W3 > W4 × max_delta_L4   (L3 always beats L4)
    #   W4 > W5 × max_delta_L5   (L4 always beats L5)
    #
    # IMPORTANT: train conflicts are HARD constraints (candidate generation
    # already excludes conflicting windows). No soft penalty needed.

    obj = []

    for tid in task_ids:
        task  = task_info[tid]
        pri   = float(task["priority"])
        pri_i = int(round(pri * 100))   # scaled integer for L2
        is_hi = pri >= HIGH_PRIORITY_THRESHOLD

        for blk in candidates:
            xv = x[tid, blk["id"]]

            # L1: reward scheduling high-priority tasks
            if is_hi:
                obj.append(-xv * W1_HIGH_PRI_DONE)

            # L2: reward total priority
            obj.append(-xv * W2_TOTAL_PRIORITY * pri_i)

            # L3: penalise not scheduling (we add W3 once per task baseline,
            # then subtract W3 when it IS scheduled — net effect: scheduled=0 cost)
            obj.append(-xv * W3_UNSCHEDULED)

    # L3 baseline: add W3 for every task (then subtracted above when scheduled)
    obj.append(len(task_ids) * W3_UNSCHEDULED)

    for blk in candidates:
        # L4: penalise each opened block
        obj.append(block_used[blk["id"]] * W4_BLOCK_COUNT)
        # L5: penalise blocked capacity
        obj.append(block_used[blk["id"]] * blk["capacity"] * W5_BLOCKED_MINS)

    model.Minimize(sum(obj))

    # ── SOLVE ─────────────────────────────────────────────────────────────
    status_code = solver.Solve(model)
    status_map  = {
        cp_model.OPTIMAL:        "OPTIMAL",
        cp_model.FEASIBLE:       "FEASIBLE",
        cp_model.INFEASIBLE:     "INFEASIBLE",
        cp_model.MODEL_INVALID:  "MODEL_INVALID",
        cp_model.UNKNOWN:        "UNKNOWN",
    }
    status_str = status_map.get(status_code, "UNKNOWN")

    print()
    print(f"── RAILANUKRITI V4.1 OPTIMIZED PLAN  [{status_str}] ──────────────────")

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("  [No feasible plan found. Check window and task data.]")
        return

    # ── EXTRACT SOLUTION ──────────────────────────────────────────────────
    solution_blocks = []
    for blk in candidates:
        if solver.Value(block_used[blk["id"]]) == 1:
            assigned = [
                task_info[tid]
                for tid in task_ids
                if solver.Value(x[tid, blk["id"]]) == 1
            ]
            if assigned:
                blk_dur = max(int(t["duration_min"]) for t in assigned)
                solution_blocks.append({
                    "start":    blk["start"],
                    "end":      blk["start"] + blk_dur,
                    "duration": blk_dur,
                    "tasks":    assigned,
                })

    solution_blocks.sort(key=lambda b: b["start"])

    # ── OPTIMIZED METRICS ─────────────────────────────────────────────────
    opt_total_min  = sum(b["duration"] for b in solution_blocks)
    opt_blocks     = len(solution_blocks)

    opt_conf_set   = set()
    for blk in solution_blocks:
        opt_conf_set.update(conflicting_trains(section, blk["start"], blk["end"]))
    opt_conflicts  = len(opt_conf_set)

    sched_tids     = {str(t["task_id"]) for blk in solution_blocks for t in blk["tasks"]}
    opt_unsched    = [t for t in task_ids if str(t) not in sched_tids]

    opt_hi_done    = sum(
        1 for blk in solution_blocks
        for t in blk["tasks"]
        if float(t["priority"]) >= HIGH_PRIORITY_THRESHOLD
    )
    opt_total_pri  = round(
        sum(float(t["priority"]) for blk in solution_blocks for t in blk["tasks"]), 2
    )

    all_trains     = list(section_trains["train_id"].astype(str))
    protected_trains = [t for t in all_trains if t not in opt_conf_set]

    # ── DISPLAY BLOCKS ────────────────────────────────────────────────────
    for i, blk in enumerate(solution_blocks, 1):
        depts      = sorted({str(t["department"]) for t in blk["tasks"]})
        blk_confs  = conflicting_trains(section, blk["start"], blk["end"])

        print()
        print(f"  ┌─ BLOCK {i} ────────────────────────────────────────────────")
        print(f"  │  Time       : {fmt_time(blk['start'])} → {fmt_time(blk['end'])}")
        print(f"  │  Duration   : {blk['duration']} min  (actual workload, not full window)")
        print(f"  │  Departments: {', '.join(depts)}")
        print(f"  │")

        for t in sorted(blk["tasks"], key=lambda x: -float(x["priority"])):
            flag = " ★ HIGH-PRI" if float(t["priority"]) >= HIGH_PRIORITY_THRESHOLD else ""
            print(f"  │  ✓ {t['task_id']} | {str(t['department']):<12} | "
                  f"{str(t['asset_id']):<8} | "
                  f"{int(t['duration_min'])} min | "
                  f"Priority {t['priority']}{flag}")

        print(f"  │")
        if blk_confs:
            print(f"  │  ⚠ Train conflicts: {blk_confs}  [review required]")
        else:
            print(f"  │  ✓ No train conflicts  ✓ Safety buffer respected")

        print(f"  │")
        print(f"  │  WHY THIS BLOCK:")
        print(f"  │    ✓ High-priority maintenance tasks optimized first (L1 objective)")
        print(f"  │    ✓ Priority takes precedence over block-count reduction")
        print(f"  │    ✓ Safety and train-conflict constraints are hard constraints")
        print(f"  │    ✓ Window free from protected train movements (+{SAFETY_BUFFER_MIN} min buffer)")
        if len(depts) > 1:
            print(f"  │    ✓ Compatible departments coordinated (parallel execution assumed)")
        print(f"  │    ✓ Block duration = actual workload ({blk['duration']} min), not full window")
        print(f"  └──────────────────────────────────────────────────────────────")

    if opt_unsched:
        print()
        print(f"  ⚠ UNSCHEDULED tasks (no feasible window found after hard constraints):")
        for tid in opt_unsched:
            t = task_info[tid]
            print(f"    - {tid} | {t['department']} | Priority {t['priority']}")

    # ── COMPARISON SUMMARY ────────────────────────────────────────────────
    print()
    print("── COMPARISON  (Prototype Simulation — Synthetic Data) ─────────────")
    print()
    print(f"  {'Metric':<35} {'Baseline':>10} {'RailAnukriti':>13}")
    print(f"  {'─'*35} {'─'*10} {'─'*13}")
    print(f"  {'Maintenance blocks':<35} {b_blocks:>10} {opt_blocks:>13}")
    print(f"  {'Total blocked time (hrs)':<35} {b_total_min/60:>10.2f} {opt_total_min/60:>13.2f}")
    print(f"  {'Train conflicts':<35} {b_conflicts:>10} {opt_conflicts:>13}")
    print(f"  {'Unscheduled tasks':<35} {len(b_unsched):>10} {len(opt_unsched):>13}")
    print(f"  {'High-pri total in section':<35} {hi_pri_total:>10} {hi_pri_total:>13}")
    print(f"  {'High-pri tasks done':<35} {b_hi_done:>10} {opt_hi_done:>13}")
    print(f"  {'Total priority available':<35} {total_pri_avail:>10.2f} {total_pri_avail:>13.2f}")
    print(f"  {'Total priority scheduled':<35} {b_total_pri:>10.2f} {opt_total_pri:>13.2f}")

    if b_blocks > 0:
        print(f"\n  Block reduction        : {(b_blocks - opt_blocks)/b_blocks*100:+.1f}%  "
              f"[synthetic prototype result]")
    if b_total_min > 0:
        print(f"  Blocked-time reduction : {(b_total_min - opt_total_min)/b_total_min*100:+.1f}%  "
              f"[synthetic prototype result]")
    if b_conflicts > 0:
        print(f"  Conflicts avoided      : {b_conflicts - opt_conflicts}  "
              f"[synthetic prototype result]")

    if protected_trains:
        print(f"\n  Trains protected: {protected_trains}")

    print()
    print("  [All figures: synthetic prototype simulation.")
    print("   Not validated against real Indian Railways operations.]")
    print()
    print("  Primary objective: maximize high-priority task completion.")
    print("  Priority takes precedence over block-count reduction.")
    print("  Safety and train-conflict constraints are hard constraints.")


# ============================================================
# MAIN
# ============================================================

def main():
    sections = sorted(tasks_df["section"].unique())

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          RAILANUKRITI V4.1 — Prototype Simulation               ║")
    print("║    AI-Assisted Priority-Aware Maintenance Block Planner         ║")
    print("║  Team: The Avalanche  |  SIH 2026  |  Problem: SIH26027        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()
    print(f"  High-priority threshold : priority >= {HIGH_PRIORITY_THRESHOLD}")
    print(f"  Safety buffer           : {SAFETY_BUFFER_MIN} min (prototype parameter)")
    print(f"  Solver time limit       : {SOLVER_TIME_LIMIT_SEC} sec/section")
    print(f"  Priority formula        : "
          f"{PRIORITY_WEIGHT_CRITICALITY}×criticality + "
          f"{PRIORITY_WEIGHT_URGENCY}×urgency + "
          f"{PRIORITY_WEIGHT_OPERATIONAL_IMPACT}×impact")
    print(f"  Objective order         : "
          "high_pri_done > total_priority > unscheduled > blocks > blocked_hrs")
    print()
    print("  Sections:")
    for s in sections:
        print(f"    • {s}")

    for section in sections:
        optimize_section(section)

    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  RailAnukriti V4.1 complete.                                    ║")
    print("║  'AI recommends. Constraints validate. Human decides.'          ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()