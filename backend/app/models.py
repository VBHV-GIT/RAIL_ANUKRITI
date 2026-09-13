"""
RailAnukriti V4.1 — Pydantic Response Models
backend/app/models.py

V4.1 additions vs V4:
- BaselineResult: added high_priority_total field
- OptimizedResult: added high_priority_total, total_priority_available,
  total_priority_scheduled fields
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    description: str


class SectionsResponse(BaseModel):
    sections: List[str]
    count: int


class TaskRecord(BaseModel):
    task_id: str
    department: str
    asset_id: str
    section: str
    duration_min: int
    criticality: float
    urgency: float
    operational_impact: float
    status: str
    priority: float


class TasksResponse(BaseModel):
    section: str
    tasks: List[TaskRecord]
    count: int


class TrainRecord(BaseModel):
    train_id: str
    train_type: str
    section: str
    arrival_min: int
    departure_min: int
    priority: str


class TrainsResponse(BaseModel):
    section: str
    trains: List[TrainRecord]
    count: int


class WindowRecord(BaseModel):
    section: str
    available_start: int
    available_end: int
    max_block_hours: float
    available_start_fmt: str
    available_end_fmt: str


class WindowsResponse(BaseModel):
    section: str
    windows: List[WindowRecord]
    count: int


class OptimizeRequest(BaseModel):
    """Optional request body — all fields have defaults."""
    safety_buffer_min: int = 15
    solver_time_limit_sec: int = 30


class TaskSummary(BaseModel):
    task_id: str
    department: str
    asset_id: str
    duration_min: int
    priority: float


class BlockResult(BaseModel):
    block_number: int
    start: str
    end: str
    duration_min: int
    departments: List[str]
    tasks: List[TaskSummary]
    train_conflicts: List[str]
    explanation: List[str]


class BaselineResult(BaseModel):
    blocks: int
    blocked_hours: float
    train_conflicts: int
    unscheduled_tasks: int
    high_priority_done: int
    high_priority_total: int          # NEW in V4.1


class OptimizedResult(BaseModel):
    blocks: int
    blocked_hours: float
    train_conflicts: int
    tasks_coordinated: int
    unscheduled_tasks: int
    high_priority_done: int
    high_priority_total: int          # NEW in V4.1
    total_priority_available: float   # NEW in V4.1
    total_priority_scheduled: float   # NEW in V4.1


class ComparisonResult(BaseModel):
    block_reduction_pct: Optional[float]
    blocked_time_reduction_pct: Optional[float]
    conflicts_avoided: int
    note: str


class OptimizeResponse(BaseModel):
    section: str
    status: str
    safety_buffer_min: int
    disclaimer: str
    baseline: BaselineResult
    optimized: OptimizedResult
    comparison: ComparisonResult
    blocks: List[BlockResult]
    trains_protected: List[str]
    explanation: List[str]