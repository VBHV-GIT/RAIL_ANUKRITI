"""
RailAnukriti V4.1
AI-Assisted Coordinated Maintenance Block Planner

Team: The Avalanche
SIH 2026
Problem: SIH26027
Domain: Transportation & Logistics

IMPORTANT:
This is a synthetic prototype simulation.
Safety buffers, resource constraints and priority weights are
prototype assumptions and are NOT official Indian Railways rules.

AI recommends. Constraints validate. Human decides.
"""

import sys
from pathlib import Path
from itertools import combinations
from collections import defaultdict

import pandas as pd
from ortools.sat.python import cp_model


# ============================================================
# PATHS
# ============================================================

# optimizer_service.py
# -> services
# -> app
# -> backend
# -> rail-anukriti
BASE_DIR = Path(__file__).resolve().parents[3]

DATA_DIR = BASE_DIR / "data"

TASKS_FILE = DATA_DIR / "maintenance_tasks.csv"
TRAINS_FILE = DATA_DIR / "trains.csv"
WINDOWS_FILE = DATA_DIR / "block_windows.csv"


# ============================================================
# PROTOTYPE CONFIGURATION
# ============================================================

SAFETY_BUFFER_MIN = 15

HIGH_PRIORITY_THRESHOLD = 4.0

SOLVER_TIME_LIMIT_SEC = 30

CANDIDATE_STEP_MIN = 30


# ============================================================
# PRIORITY WEIGHTS
# ============================================================

PRIORITY_WEIGHT_CRITICALITY = 0.40
PRIORITY_WEIGHT_URGENCY = 0.35
PRIORITY_WEIGHT_OPERATIONAL_IMPACT = 0.25


# ============================================================
# LEXICOGRAPHIC OBJECTIVE WEIGHTS
# ============================================================

# Objective order:
#
# L1 = maximize high-priority tasks completed
# L2 = maximize total priority
# L3 = minimize unscheduled tasks
# L4 = minimize maintenance blocks
# L5 = minimize blocked minutes
#
# Higher objective always dominates lower objective.

W5_BLOCKED_MINS = 1
W4_BLOCK_COUNT = 300_000
W3_UNSCHEDULED = 60_300_000
W2_TOTAL_PRIORITY = 3_075_300_000
W1_HIGH_PRI_DONE = 153_768_075_300_000


# ============================================================
# RESOURCE MODEL
# ============================================================

RESOURCE_GROUP = {
    "Engineering": "TRACK",
    "Signalling": "SIGNAL",
    "Traction": "OHE",
}


def same_resource(dept_a: str, dept_b: str) -> bool:
    return (
        RESOURCE_GROUP.get(dept_a, dept_a)
        == RESOURCE_GROUP.get(dept_b, dept_b)
    )


# ============================================================
# DATAFRAME STORAGE
# ============================================================

tasks_df = pd.DataFrame()
trains_df = pd.DataFrame()
windows_df = pd.DataFrame()


# ============================================================
# TIME UTILITIES
# ============================================================

def fmt_time(minutes):
    if minutes is None:
        return "N/A"

    minutes = int(minutes)

    if minutes >= 1440:
        return "24:00"

    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def overlaps(s1, e1, s2, e2):
    return s1 < e2 and e1 > s2


# ============================================================
# DATA VALIDATION
# ============================================================

REQUIRED_TASK_COLS = [
    "task_id",
    "department",
    "asset_id",
    "section",
    "duration_min",
    "criticality",
    "urgency",
    "operational_impact",
    "status",
]

REQUIRED_TRAIN_COLS = [
    "train_id",
    "train_type",
    "section",
    "arrival_min",
    "departure_min",
    "priority",
]

REQUIRED_WINDOW_COLS = [
    "section",
    "available_start",
    "available_end",
    "max_block_hours",
]


def _validate_cols(df, required, name):
    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(
            f"{name} is missing columns: {missing}"
        )


def validate_tasks(df):
    _validate_cols(
        df,
        REQUIRED_TASK_COLS,
        "maintenance_tasks.csv",
    )

    df = df.copy()

    df["duration_min"] = pd.to_numeric(
        df["duration_min"],
        errors="coerce",
    )

    df["criticality"] = pd.to_numeric(
        df["criticality"],
        errors="coerce",
    )

    df["urgency"] = pd.to_numeric(
        df["urgency"],
        errors="coerce",
    )

    df["operational_impact"] = pd.to_numeric(
        df["operational_impact"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "task_id",
            "department",
            "section",
            "duration_min",
            "criticality",
            "urgency",
            "operational_impact",
        ]
    )

    df = df[df["duration_min"] > 0].copy()

    return df


def validate_trains(df):
    _validate_cols(
        df,
        REQUIRED_TRAIN_COLS,
        "trains.csv",
    )

    df = df.copy()

    df["arrival_min"] = pd.to_numeric(
        df["arrival_min"],
        errors="coerce",
    )

    df["departure_min"] = pd.to_numeric(
        df["departure_min"],
        errors="coerce",
    )

    df["priority"] = pd.to_numeric(
        df["priority"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "train_id",
            "section",
            "arrival_min",
            "departure_min",
        ]
    )

    df = df[
        df["arrival_min"] < df["departure_min"]
    ].copy()

    return df


def validate_windows(df):
    _validate_cols(
        df,
        REQUIRED_WINDOW_COLS,
        "block_windows.csv",
    )

    df = df.copy()

    df["available_start"] = pd.to_numeric(
        df["available_start"],
        errors="coerce",
    )

    df["available_end"] = pd.to_numeric(
        df["available_end"],
        errors="coerce",
    )

    df["max_block_hours"] = pd.to_numeric(
        df["max_block_hours"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "section",
            "available_start",
            "available_end",
            "max_block_hours",
        ]
    )

    df = df[
        df["available_start"] < df["available_end"]
    ].copy()

    return df


# ============================================================
# PRIORITY CALCULATION
# ============================================================

def calculate_priority(row):
    """
    Composite priority:

        criticality       × 0.40
        urgency           × 0.35
        operational_impact × 0.25

    Higher score = higher maintenance priority.
    """

    priority = (
        float(row["criticality"])
        * PRIORITY_WEIGHT_CRITICALITY
        + float(row["urgency"])
        * PRIORITY_WEIGHT_URGENCY
        + float(row["operational_impact"])
        * PRIORITY_WEIGHT_OPERATIONAL_IMPACT
    )

    return round(priority, 2)


# ============================================================
# LOAD DATA
# ============================================================

def reload_data():
    global tasks_df
    global trains_df
    global windows_df

    print("\nLoading data...")

    tasks_df = pd.read_csv(TASKS_FILE)
    trains_df = pd.read_csv(TRAINS_FILE)
    windows_df = pd.read_csv(WINDOWS_FILE)

    tasks_df = validate_tasks(tasks_df)
    trains_df = validate_trains(trains_df)
    windows_df = validate_windows(windows_df)

    tasks_df["priority"] = tasks_df.apply(
        calculate_priority,
        axis=1,
    )

    print(f"  Tasks   : {len(tasks_df)}")
    print(f"  Trains  : {len(trains_df)}")
    print(f"  Windows : {len(windows_df)}")

# ============================================================
# TRAIN PROTECTION
# ============================================================

def get_protected_windows(section):
    """
    Return protected train intervals:

        (protected_start, protected_end, train_id)

    A prototype safety buffer is applied around each train.
    """

    result = []

    section = section.upper()

    section_trains = trains_df[
        trains_df["section"]
        .astype(str)
        .str.upper()
        == section
    ]

    for _, train in section_trains.iterrows():

        arrival = int(train["arrival_min"])
        departure = int(train["departure_min"])

        protected_start = max(
            0,
            arrival - SAFETY_BUFFER_MIN,
        )

        protected_end = min(
            1440,
            departure + SAFETY_BUFFER_MIN,
        )

        result.append(
            (
                protected_start,
                protected_end,
                str(train["train_id"]),
            )
        )

    return result


def conflicting_trains(
    section,
    block_start,
    block_end,
):
    """
    Return train IDs conflicting with a proposed block.
    """

    conflicts = []

    for protected_start, protected_end, train_id in (
        get_protected_windows(section)
    ):

        if overlaps(
            block_start,
            block_end,
            protected_start,
            protected_end,
        ):
            conflicts.append(train_id)

    return conflicts


# ============================================================
# CANDIDATE BLOCK GENERATION
# ============================================================

def generate_candidates(
    section,
    section_windows,
):
    """
    Generate feasible maintenance blocks.

    Train-protected intervals are removed first.
    """

    protected = get_protected_windows(section)

    candidates = []

    block_id = 0

    for _, window in section_windows.iterrows():

        window_start = int(
            window["available_start"]
        )

        window_end = int(
            window["available_end"]
        )

        max_minutes = int(
            float(window["max_block_hours"]) * 60
        )

        free_intervals = [
            (window_start, window_end)
        ]

        # Remove protected train windows.
        for protected_start, protected_end, _ in protected:

            new_free = []

            for free_start, free_end in free_intervals:

                if (
                    protected_end <= free_start
                    or protected_start >= free_end
                ):
                    new_free.append(
                        (free_start, free_end)
                    )

                else:

                    if free_start < protected_start:
                        new_free.append(
                            (
                                free_start,
                                protected_start,
                            )
                        )

                    if protected_end < free_end:
                        new_free.append(
                            (
                                protected_end,
                                free_end,
                            )
                        )

            free_intervals = new_free

        # Create candidate blocks.
        for free_start, free_end in free_intervals:

            for start in range(
                free_start,
                free_end,
                CANDIDATE_STEP_MIN,
            ):

                capacity = min(
                    free_end - start,
                    max_minutes,
                )

                if capacity <= 0:
                    continue

                end = start + capacity

                if conflicting_trains(
                    section,
                    start,
                    end,
                ):
                    continue

                candidates.append(
                    {
                        "id": block_id,
                        "start": start,
                        "end": end,
                        "capacity": capacity,
                    }
                )

                block_id += 1

    return candidates


# ============================================================
# BASELINE PLANNER
# ============================================================

def create_baseline(
    section,
    section_tasks,
    section_windows,
):
    """
    Rule-based sequential baseline.

    Tasks are processed by priority.
    Each resource group is sequential.
    Train protection is respected.
    """

    scheduled = []
    unscheduled = []

    resource_cursor = {}

    sorted_tasks = section_tasks.sort_values(
        by=["priority", "duration_min"],
        ascending=[False, False],
    )

    sorted_windows = section_windows.sort_values(
        "available_start"
    )

    for _, task in sorted_tasks.iterrows():

        task_id = str(task["task_id"])
        department = str(task["department"])
        resource = RESOURCE_GROUP.get(
            department,
            department,
        )

        duration = int(task["duration_min"])

        current_time = resource_cursor.get(
            resource,
            0,
        )

        placed = False

        for _, window in sorted_windows.iterrows():

            window_start = int(
                window["available_start"]
            )

            window_end = int(
                window["available_end"]
            )

            start = max(
                current_time,
                window_start,
            )

            while True:

                end = start + duration

                if end > window_end:
                    break

                conflicts = conflicting_trains(
                    section,
                    start,
                    end,
                )

                if not conflicts:
                    break

                latest_protected_end = start

                for (
                    protected_start,
                    protected_end,
                    _,
                ) in get_protected_windows(section):

                    if overlaps(
                        start,
                        end,
                        protected_start,
                        protected_end,
                    ):
                        latest_protected_end = max(
                            latest_protected_end,
                            protected_end,
                        )

                if latest_protected_end <= start:
                    break

                start = latest_protected_end

            end = start + duration

            if (
                end <= window_end
                and not conflicting_trains(
                    section,
                    start,
                    end,
                )
            ):

                scheduled.append(
                    {
                        "task_id": task_id,
                        "department": department,
                        "asset_id": str(
                            task["asset_id"]
                        ),
                        "start": start,
                        "end": end,
                        "duration": duration,
                        "priority": float(
                            task["priority"]
                        ),
                        "resource": resource,
                    }
                )

                resource_cursor[resource] = end

                placed = True

                break

        if not placed:

            unscheduled.append(
                {
                    "task_id": task_id,
                    "department": department,
                    "priority": float(
                        task["priority"]
                    ),
                    "duration": duration,
                }
            )

    return scheduled, unscheduled


def count_baseline_blocks(scheduled):
    """
    Count sequential maintenance blocks.
    """

    if not scheduled:
        return 0

    by_resource = defaultdict(list)

    for task in scheduled:
        by_resource[
            task["resource"]
        ].append(task)

    count = 0

    for resource_tasks in by_resource.values():

        resource_tasks.sort(
            key=lambda x: x["start"]
        )

        count += 1

        for i in range(
            1,
            len(resource_tasks),
        ):

            if (
                resource_tasks[i]["start"]
                > resource_tasks[i - 1]["end"]
            ):
                count += 1

    return count


# ============================================================
# OPTIMIZATION
# ============================================================

def optimize_section(section):
    """
    Main V4.1 CP-SAT optimizer.

    Returns a dictionary suitable for the FastAPI layer.
    """

    section = section.upper()

    section_tasks = tasks_df[
        tasks_df["section"]
        .astype(str)
        .str.upper()
        == section
    ].copy()

    section_trains = trains_df[
        trains_df["section"]
        .astype(str)
        .str.upper()
        == section
    ].copy()

    section_windows = windows_df[
        windows_df["section"]
        .astype(str)
        .str.upper()
        == section
    ].copy()

    if section_tasks.empty:
        raise ValueError(
            f"No maintenance tasks found for section '{section}'."
        )

    if section_windows.empty:
        raise ValueError(
            f"No maintenance windows found for section '{section}'."
        )

    # ========================================================
    # SECTION STATISTICS
    # ========================================================

    total_priority_available = round(
        float(section_tasks["priority"].sum()),
        2,
    )

    high_priority_total = int(
        (
            section_tasks["priority"]
            >= HIGH_PRIORITY_THRESHOLD
        ).sum()
    )

    # ========================================================
    # BASELINE
    # ========================================================

    baseline_scheduled, baseline_unscheduled = (
        create_baseline(
            section,
            section_tasks,
            section_windows,
        )
    )

    baseline_total_min = sum(
        task["duration"]
        for task in baseline_scheduled
    )

    baseline_blocks = count_baseline_blocks(
        baseline_scheduled
    )

    baseline_conflicts = set()

    for task in baseline_scheduled:

        baseline_conflicts.update(
            conflicting_trains(
                section,
                task["start"],
                task["end"],
            )
        )

    baseline_high_priority_done = sum(
        1
        for task in baseline_scheduled
        if task["priority"]
        >= HIGH_PRIORITY_THRESHOLD
    )

    baseline_total_priority = round(
        sum(
            task["priority"]
            for task in baseline_scheduled
        ),
        2,
    )

    # ========================================================
    # CANDIDATES
    # ========================================================

    candidates = generate_candidates(
        section,
        section_windows,
    )

    if not candidates:

        return {
            "section": section,
            "status": "INFEASIBLE",
            "safety_buffer_min": SAFETY_BUFFER_MIN,
            "disclaimer": (
                "All figures are from a synthetic prototype "
                "simulation. Not validated against real "
                "Indian Railways operations."
            ),
            "baseline": {
                "blocks": baseline_blocks,
                "blocked_hours": round(
                    baseline_total_min / 60,
                    2,
                ),
                "train_conflicts": len(
                    baseline_conflicts
                ),
                "unscheduled_tasks": len(
                    baseline_unscheduled
                ),
                "high_priority_done": (
                    baseline_high_priority_done
                ),
                "high_priority_total": (
                    high_priority_total
                ),
            },
            "optimized": {
                "blocks": 0,
                "blocked_hours": 0,
                "tasks_coordinated": 0,
                "unscheduled_tasks": len(
                    section_tasks
                ),
                "high_priority_done": 0,
                "high_priority_total": (
                    high_priority_total
                ),
            },
            "comparison": {
                "block_reduction_pct": 0,
                "blocked_time_reduction_pct": 0,
                "conflicts_avoided": 0,
                "note": (
                    "No feasible maintenance candidate "
                    "blocks were generated."
                ),
            },
            "blocks": [],
            "trains_protected": [
                str(x)
                for x in section_trains[
                    "train_id"
                ].tolist()
            ],
            "explanation": [
                "No feasible maintenance slot exists.",
                "Train-conflict windows were rejected.",
                (
                    "Safety buffer was applied around "
                    "train movements."
                ),
            ],
        }

    # ========================================================
    # CP-SAT MODEL
    # ========================================================

    model = cp_model.CpModel()

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = (
        SOLVER_TIME_LIMIT_SEC
    )

    solver.parameters.num_search_workers = 8

    task_ids = [
        str(x)
        for x in section_tasks["task_id"]
    ]

    task_info = {
        str(row["task_id"]): row
        for _, row in section_tasks.iterrows()
    }

    x = {}

    block_used = {}

    # ========================================================
    # VARIABLES
    # ========================================================

    for task_id in task_ids:

        for block in candidates:

            x[
                task_id,
                block["id"],
            ] = model.NewBoolVar(
                f"x_{task_id}_{block['id']}"
            )

    for block in candidates:

        block_used[
            block["id"]
        ] = model.NewBoolVar(
            f"block_used_{block['id']}"
        )

    # ========================================================
    # CONSTRAINT 1
    # Every task is either scheduled OR unscheduled.
    #
    # IMPORTANT:
    # We use <= 1, not == 1, because infeasible tasks
    # must be allowed to remain unscheduled.
    # ========================================================

    for task_id in task_ids:

        model.Add(
            sum(
                x[
                    task_id,
                    block["id"],
                ]
                for block in candidates
            )
            <= 1
        )

    # ========================================================
    # CONSTRAINT 2
    # Task duration must fit block capacity.
    # ========================================================

    for task_id in task_ids:

        duration = int(
            task_info[task_id]["duration_min"]
        )

        for block in candidates:

            if duration > block["capacity"]:

                model.Add(
                    x[
                        task_id,
                        block["id"],
                    ]
                    == 0
                )

    # ========================================================
    # CONSTRAINT 3
    # Block activation.
    # ========================================================

    for block in candidates:

        block_id = block["id"]

        for task_id in task_ids:

            model.Add(
                x[
                    task_id,
                    block_id,
                ]
                <= block_used[block_id]
            )

        model.Add(
            sum(
                x[
                    task_id,
                    block_id,
                ]
                for task_id in task_ids
            )
            >= block_used[block_id]
        )

    # ========================================================
    # CONSTRAINT 4
    # Same resource cannot run two tasks in same block.
    # ========================================================

    task_rows = list(
        section_tasks.itertuples()
    )

    for task_a, task_b in combinations(
        task_rows,
        2,
    ):

        department_a = str(
            task_a.department
        )

        department_b = str(
            task_b.department
        )

        if same_resource(
            department_a,
            department_b,
        ):

            task_a_id = str(
                task_a.task_id
            )

            task_b_id = str(
                task_b.task_id
            )

            for block in candidates:

                block_id = block["id"]

                model.Add(
                    x[
                        task_a_id,
                        block_id,
                    ]
                    + x[
                        task_b_id,
                        block_id,
                    ]
                    <= 1
                )

    # ========================================================
    # OBJECTIVE
    #
    # L1: MAX high-priority tasks
    # L2: MAX total priority
    # L3: MIN unscheduled
    # L4: MIN blocks
    # L5: MIN blocked capacity
    # ========================================================

    objective_terms = []

    # --------------------------------------------------------
    # L1 + L2
    # --------------------------------------------------------

    for task_id in task_ids:

        task = task_info[task_id]

        priority = float(
            task["priority"]
        )

        priority_integer = int(
            round(priority * 100)
        )

        is_high_priority = (
            priority
            >= HIGH_PRIORITY_THRESHOLD
        )

        for block in candidates:

            decision = x[
                task_id,
                block["id"],
            ]

            # L1
            if is_high_priority:

                objective_terms.append(
                    -decision
                    * W1_HIGH_PRI_DONE
                )

            # L2
            objective_terms.append(
                -decision
                * W2_TOTAL_PRIORITY
                * priority_integer
            )

            # L3
            objective_terms.append(
                -decision
                * W3_UNSCHEDULED
            )

    # --------------------------------------------------------
    # L3 baseline penalty
    #
    # Every task starts with an unscheduled penalty.
    # Scheduling removes that penalty.
    # --------------------------------------------------------

    objective_terms.append(
        len(task_ids)
        * W3_UNSCHEDULED
    )

    # --------------------------------------------------------
    # L4 + L5
    # --------------------------------------------------------

    for block in candidates:

        block_id = block["id"]

        objective_terms.append(
            block_used[block_id]
            * W4_BLOCK_COUNT
        )

        objective_terms.append(
            block_used[block_id]
            * block["capacity"]
            * W5_BLOCKED_MINS
        )

    model.Minimize(
        sum(objective_terms)
    )

    # ========================================================
    # SOLVE
    # ========================================================

    status_code = solver.Solve(model)

    status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }

    status = status_map.get(
        status_code,
        "UNKNOWN",
    )

    if status_code not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):

        return {
            "section": section,
            "status": status,
            "safety_buffer_min": SAFETY_BUFFER_MIN,
            "disclaimer": (
                "All figures are from a synthetic prototype "
                "simulation. Not validated against real "
                "Indian Railways operations."
            ),
            "baseline": {
                "blocks": baseline_blocks,
                "blocked_hours": round(
                    baseline_total_min / 60,
                    2,
                ),
                "train_conflicts": len(
                    baseline_conflicts
                ),
                "unscheduled_tasks": len(
                    baseline_unscheduled
                ),
                "high_priority_done": (
                    baseline_high_priority_done
                ),
                "high_priority_total": (
                    high_priority_total
                ),
            },
            "optimized": {
                "blocks": 0,
                "blocked_hours": 0,
                "tasks_coordinated": 0,
                "unscheduled_tasks": len(
                    section_tasks
                ),
                "high_priority_done": 0,
                "high_priority_total": (
                    high_priority_total
                ),
            },
            "comparison": {
                "block_reduction_pct": 0,
                "blocked_time_reduction_pct": 0,
                "conflicts_avoided": 0,
                "note": (
                    "CP-SAT did not find a feasible solution."
                ),
            },
            "blocks": [],
            "trains_protected": [
                str(x)
                for x in section_trains[
                    "train_id"
                ].tolist()
            ],
            "explanation": [
                "No feasible optimized plan was found.",
                "Hard safety constraints were preserved.",
                "Train conflicts are not allowed.",
            ],
        }

    # ========================================================
    # EXTRACT SOLUTION
    # ========================================================

    solution_blocks = []

    for block in candidates:

        block_id = block["id"]

        if solver.Value(
            block_used[block_id]
        ) != 1:
            continue

        assigned_tasks = []

        for task_id in task_ids:

            if solver.Value(
                x[
                    task_id,
                    block_id,
                ]
            ) == 1:

                row = task_info[task_id]

                assigned_tasks.append(
                    {
                        "task_id": str(
                            row["task_id"]
                        ),
                        "department": str(
                            row["department"]
                        ),
                        "asset_id": str(
                            row["asset_id"]
                        ),
                        "duration_min": int(
                            row["duration_min"]
                        ),
                        "priority": float(
                            row["priority"]
                        ),
                    }
                )

        if not assigned_tasks:
            continue

        # Parallel departments mean the block duration is
        # determined by the longest task.
        workload_duration = max(
            task["duration_min"]
            for task in assigned_tasks
        )

        block_start = block["start"]

        block_end = (
            block_start
            + workload_duration
        )

        solution_blocks.append(
            {
                "start": block_start,
                "end": block_end,
                "duration": workload_duration,
                "tasks": assigned_tasks,
            }
        )

    solution_blocks.sort(
        key=lambda block: block["start"]
    )

    # ========================================================
    # OPTIMIZED METRICS
    # ========================================================

    optimized_total_min = sum(
        block["duration"]
        for block in solution_blocks
    )

    optimized_blocks = len(
        solution_blocks
    )

    optimized_conflicts = set()

    for block in solution_blocks:

        optimized_conflicts.update(
            conflicting_trains(
                section,
                block["start"],
                block["end"],
            )
        )

    scheduled_task_ids = {
        task["task_id"]
        for block in solution_blocks
        for task in block["tasks"]
    }

    optimized_unscheduled = [
        task_id
        for task_id in task_ids
        if task_id not in scheduled_task_ids
    ]

    optimized_high_priority_done = sum(
        1
        for block in solution_blocks
        for task in block["tasks"]
        if task["priority"]
        >= HIGH_PRIORITY_THRESHOLD
    )

    optimized_total_priority = round(
        sum(
            task["priority"]
            for block in solution_blocks
            for task in block["tasks"]
        ),
        2,
    )

    # ========================================================
    # TRAIN PROTECTION
    # ========================================================

    all_train_ids = [
        str(train_id)
        for train_id in section_trains[
            "train_id"
        ].tolist()
    ]

    protected_trains = [
        train_id
        for train_id in all_train_ids
        if train_id not in optimized_conflicts
    ]

    # ========================================================
    # BLOCK API FORMAT
    # ========================================================

    api_blocks = []

    for index, block in enumerate(
        solution_blocks,
        start=1,
    ):

        departments = sorted(
            {
                task["department"]
                for task in block["tasks"]
            }
        )

        conflicts = conflicting_trains(
            section,
            block["start"],
            block["end"],
        )

        api_tasks = []

        for task in sorted(
            block["tasks"],
            key=lambda x: -x["priority"],
        ):

            api_tasks.append(
                {
                    "task_id": task["task_id"],
                    "department": task[
                        "department"
                    ],
                    "asset_id": task[
                        "asset_id"
                    ],
                    "duration_min": task[
                        "duration_min"
                    ],
                    "priority": task[
                        "priority"
                    ],
                    "high_priority": (
                        task["priority"]
                        >= HIGH_PRIORITY_THRESHOLD
                    ),
                }
            )

        explanation = [
            "Window free from protected train movements.",
            (
                f"Safety buffer of "
                f"{SAFETY_BUFFER_MIN} minutes "
                "respected."
            ),
            (
                "High-priority maintenance tasks "
                "receive first preference."
            ),
            (
                "Compatible departments coordinated "
                "within one maintenance block."
            ),
            (
                "Block duration equals actual "
                "parallel workload."
            ),
        ]

        if conflicts:
            explanation.append(
                f"Train conflicts detected: {conflicts}"
            )
        else:
            explanation.append(
                "No train conflicts."
            )

        api_blocks.append(
            {
                "block_number": index,
                "start": fmt_time(
                    block["start"]
                ),
                "end": fmt_time(
                    block["end"]
                ),
                "duration_min": block[
                    "duration"
                ],
                "departments": departments,
                "tasks": api_tasks,
                "train_conflicts": conflicts,
                "explanation": explanation,
            }
        )

    # ========================================================
    # COMPARISON
    # ========================================================

    if baseline_blocks > 0:

        block_reduction = round(
            (
                (
                    baseline_blocks
                    - optimized_blocks
                )
                / baseline_blocks
            )
            * 100,
            1,
        )

    else:
        block_reduction = 0.0

    if baseline_total_min > 0:

        blocked_time_reduction = round(
            (
                (
                    baseline_total_min
                    - optimized_total_min
                )
                / baseline_total_min
            )
            * 100,
            1,
        )

    else:
        blocked_time_reduction = 0.0

    # ========================================================
    # FINAL API RESPONSE
    # ========================================================

    result = {
        "section": section,
        "status": status,

        "safety_buffer_min": SAFETY_BUFFER_MIN,

        "disclaimer": (
            "All figures are from a synthetic prototype "
            "simulation. Safety buffer values, resource "
            "constraints and priority weights are configurable "
            "prototype parameters and are NOT official Indian "
            "Railways rules. No real-world performance "
            "guarantees are implied."
        ),

        "baseline": {
            "blocks": baseline_blocks,
            "blocked_hours": round(
                baseline_total_min / 60,
                2,
            ),
            "train_conflicts": len(
                baseline_conflicts
            ),
            "unscheduled_tasks": len(
                baseline_unscheduled
            ),
            "high_priority_done": (
                baseline_high_priority_done
            ),
            "high_priority_total": (
                high_priority_total
            ),
            "total_priority_available": (
                total_priority_available
            ),
            "total_priority_scheduled": (
                baseline_total_priority
            ),
        },

        "optimized": {
            "blocks": optimized_blocks,
            "blocked_hours": round(
                optimized_total_min / 60,
                2,
            ),
            "train_conflicts": len(
                optimized_conflicts
            ),
            "tasks_coordinated": sum(
                len(block["tasks"])
                for block in solution_blocks
            ),
            "unscheduled_tasks": len(
                optimized_unscheduled
            ),
            "high_priority_done": (
                optimized_high_priority_done
            ),
            "high_priority_total": (
                high_priority_total
            ),
            "total_priority_available": (
                total_priority_available
            ),
            "total_priority_scheduled": (
                optimized_total_priority
            ),
        },

        "comparison": {
            "block_reduction_pct": (
                block_reduction
            ),
            "blocked_time_reduction_pct": (
                blocked_time_reduction
            ),
            "conflicts_avoided": max(
                0,
                len(baseline_conflicts)
                - len(optimized_conflicts),
            ),
            "note": (
                "Synthetic prototype result — "
                "not validated against real operations."
            ),
        },

        "blocks": api_blocks,

        "trains_protected": protected_trains,

        "explanation": [
            (
                "High-priority task completion is "
                "the primary optimization objective."
            ),
            (
                "Total priority is optimized after "
                "high-priority completion."
            ),
            (
                "Unscheduled tasks are minimized "
                "after priority objectives."
            ),
            (
                "Maintenance block count is minimized "
                "after priority objectives."
            ),
            (
                "Blocked time is minimized as the "
                "final objective."
            ),
            (
                "Train conflicts are hard constraints."
            ),
            (
                f"Safety buffer of {SAFETY_BUFFER_MIN} "
                "minutes is applied around trains."
            ),
            (
                "Compatible departments may execute "
                "in parallel."
            ),
            (
                "Same-resource tasks cannot execute "
                "simultaneously."
            ),
            (
                "All results are synthetic prototype "
                "simulation results."
            ),
        ],
    }

    return result


# ============================================================
# FASTAPI DATA FUNCTIONS
# ============================================================

def get_sections():
    """
    Return all railway sections.
    """

    if tasks_df.empty:
        reload_data()

    return sorted(
        tasks_df["section"]
        .dropna()
        .astype(str)
        .str.upper()
        .unique()
        .tolist()
    )


def get_section_tasks(section: str):
    """
    Return maintenance tasks for a section.
    """

    if tasks_df.empty:
        reload_data()

    section = section.upper()

    df = tasks_df[
        tasks_df["section"]
        .astype(str)
        .str.upper()
        == section
    ]

    if df.empty:
        return []

    result = []

    for _, row in df.iterrows():

        result.append(
            {
                "task_id": str(
                    row["task_id"]
                ),
                "department": str(
                    row["department"]
                ),
                "asset_id": str(
                    row["asset_id"]
                ),
                "section": str(
                    row["section"]
                ),
                "duration_min": int(
                    row["duration_min"]
                ),
                "criticality": float(
                    row["criticality"]
                ),
                "urgency": float(
                    row["urgency"]
                ),
                "operational_impact": float(
                    row["operational_impact"]
                ),
                "status": str(
                    row["status"]
                ),
                "priority": float(
                    row["priority"]
                ),
            }
        )

    return result


def get_section_trains(section: str):
    """
    Return train movements for a section.
    """

    if trains_df.empty:
        reload_data()

    section = section.upper()

    df = trains_df[
        trains_df["section"]
        .astype(str)
        .str.upper()
        == section
    ]

    if df.empty:
        return []

    result = []

    for _, row in df.iterrows():

        result.append(
            {
                "train_id": str(
                    row["train_id"]
                ),
                "train_type": str(
                    row["train_type"]
                ),
                "section": str(
                    row["section"]
                ),
                "arrival_min": int(
                    row["arrival_min"]
                ),
                "departure_min": int(
                    row["departure_min"]
                ),
                "priority": float(
                    row["priority"]
                ),
            }
        )

    return result


def get_section_windows(section: str):
    """
    Return maintenance windows for a section.
    """

    if windows_df.empty:
        reload_data()

    section = section.upper()

    df = windows_df[
        windows_df["section"]
        .astype(str)
        .str.upper()
        == section
    ]

    if df.empty:
        return []

    result = []

    for _, row in df.iterrows():

        result.append(
            {
                "section": str(
                    row["section"]
                ),
                "available_start": int(
                    row["available_start"]
                ),
                "available_end": int(
                    row["available_end"]
                ),
                "max_block_hours": float(
                    row["max_block_hours"]
                ),
            }
        )

    return result


# ============================================================
# FASTAPI OPTIMIZATION ENTRY POINT
# ============================================================

def run_optimization(
    section: str,
    safety_buffer_min: int = 15,
    solver_time_limit_sec: int = 30,
):
    """
    FastAPI-compatible optimization function.

    Temporarily applies API parameters and runs V4.1.
    """

    global SAFETY_BUFFER_MIN
    global SOLVER_TIME_LIMIT_SEC

    section = section.upper()

    if section not in get_sections():

        raise ValueError(
            f"Unknown section '{section}'. "
            f"Available sections: {get_sections()}"
        )

    old_safety_buffer = SAFETY_BUFFER_MIN
    old_solver_limit = SOLVER_TIME_LIMIT_SEC

    try:

        SAFETY_BUFFER_MIN = max(
            0,
            int(safety_buffer_min),
        )

        SOLVER_TIME_LIMIT_SEC = max(
            1,
            int(solver_time_limit_sec),
        )

        return optimize_section(section)

    finally:

        SAFETY_BUFFER_MIN = (
            old_safety_buffer
        )

        SOLVER_TIME_LIMIT_SEC = (
            old_solver_limit
        )


# ============================================================
# CLI
# ============================================================

def main():

    reload_data()

    sections = get_sections()

    print()
    print(
        "╔══════════════════════════════════════════════════════════════════╗"
    )
    print(
        "║          RAILANUKRITI V4.1 — Prototype Simulation               ║"
    )
    print(
        "║    AI-Assisted Priority-Aware Maintenance Block Planner         ║"
    )
    print(
        "║  Team: The Avalanche  |  SIH 2026  |  Problem: SIH26027        ║"
    )
    print(
        "╚══════════════════════════════════════════════════════════════════╝"
    )
    print()

    print(
        f"  High-priority threshold : "
        f"priority >= {HIGH_PRIORITY_THRESHOLD}"
    )

    print(
        f"  Safety buffer           : "
        f"{SAFETY_BUFFER_MIN} min"
    )

    print(
        f"  Solver time limit       : "
        f"{SOLVER_TIME_LIMIT_SEC} sec/section"
    )

    print(
        "  Priority formula        : "
        "0.40×criticality + "
        "0.35×urgency + "
        "0.25×impact"
    )

    print(
        "  Objective order         : "
        "high_pri_done > total_priority "
        "> unscheduled > blocks > blocked_time"
    )

    print()

    print("  Sections:")

    for section in sections:
        print(f"    • {section}")

    for section in sections:

        result = optimize_section(section)

        print()
        print(
            f"Completed optimization for {section}: "
            f"{result['status']}"
        )

    print()
    print(
        "╔══════════════════════════════════════════════════════════════════╗"
    )
    print(
        "║  RailAnukriti V4.1 complete.                                    ║"
    )
    print(
        "║  AI recommends. Constraints validate. Human decides.            ║"
    )
    print(
        "╚══════════════════════════════════════════════════════════════════╝"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()