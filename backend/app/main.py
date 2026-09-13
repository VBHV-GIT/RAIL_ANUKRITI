"""
RailAnukriti V4 — FastAPI Application Entry Point
backend/app/main.py

Run with:
    cd backend
    uvicorn app.main:app --reload

Swagger UI: http://127.0.0.1:8000/docs
ReDoc:       http://127.0.0.1:8000/redoc
"""
from app.services.ai_service import generate_plan_explanation
from fastapi import Body, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    HealthResponse,
    SectionsResponse,
    TasksResponse,
    TrainsResponse,
    WindowsResponse,
    OptimizeRequest,
    OptimizeResponse,
)
from app.services.optimizer_service import (
    get_sections,
    get_section_tasks,
    get_section_trains,
    get_section_windows,
    run_optimization,
    reload_data,
)
from app.services.ai_service import generate_plan_explanation

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(
    title="RailAnukriti API",
    description=(
        "AI-Assisted Coordinated Maintenance Block Planner — V4\n\n"
        "**Team:** The Avalanche | **SIH 2026** | **Problem:** SIH26027\n\n"
        "> All optimisation results are from a **synthetic prototype simulation**. "
        "Not validated against real Indian Railways operations."
    ),
    version="4.0.0",
    contact={
        "name": "The Avalanche — SIH 2026",
    },
)


# ============================================================
# CORS  (allow React dev server and any local origin)
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://railanukriti.netlify.app",
],


    # allow_origins=[
    #     "http://localhost:3000",   # Create React App default
    #     "http://localhost:5173",   # Vite default
    #     "http://127.0.0.1:3000",
    #     "http://127.0.0.1:5173",
    # ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# STARTUP — pre-load and validate data once
# ============================================================

@app.on_event("startup")
async def startup_event():
    """
    Pre-load all CSVs and validate them on server start.
    Fails fast if data files are missing or malformed.
    """
    try:
        reload_data()
        sections = get_sections()
        print(f"[RailAnukriti] Data loaded OK — {len(sections)} sections: {sections}")
    except Exception as e:
        # Log and re-raise so uvicorn reports the error clearly
        print(f"[RailAnukriti] STARTUP ERROR: {e}")
        raise


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["System"],
)
def health():
    """Returns API status and version."""
    return HealthResponse(
        status="ok",
        version="4.0.0",
        description="RailAnukriti V4 API is running. Synthetic prototype simulation.",
    )


# ============================================================
# SECTIONS
# ============================================================

@app.get(
    "/sections",
    response_model=SectionsResponse,
    summary="List all available sections",
    tags=["Sections"],
)
def list_sections():
    """Return all railway sections present in the maintenance task dataset."""
    sections = get_sections()
    return SectionsResponse(sections=sections, count=len(sections))


# ============================================================
# SECTION DATA
# ============================================================

@app.get(
    "/sections/{section}/tasks",
    response_model=TasksResponse,
    summary="Get maintenance tasks for a section",
    tags=["Sections"],
)
def section_tasks(
    section: str = Path(..., description="Section ID, e.g. S01"),
):
    """
    Return all maintenance tasks for the given section,
    including computed priority scores.
    """
    tasks = get_section_tasks(section)
    if not tasks:
        raise HTTPException(
            status_code=404,
            detail=f"No tasks found for section '{section}'. "
                   f"Available sections: {get_sections()}",
        )
    return TasksResponse(section=section, tasks=tasks, count=len(tasks))


@app.get(
    "/sections/{section}/trains",
    response_model=TrainsResponse,
    summary="Get train movements for a section",
    tags=["Sections"],
)
def section_trains(
    section: str = Path(..., description="Section ID, e.g. S01"),
):
    """Return all scheduled train movements for the given section."""
    trains = get_section_trains(section)
    if not trains:
        raise HTTPException(
            status_code=404,
            detail=f"No trains found for section '{section}'.",
        )
    return TrainsResponse(section=section, trains=trains, count=len(trains))


@app.get(
    "/sections/{section}/windows",
    response_model=WindowsResponse,
    summary="Get maintenance windows for a section",
    tags=["Sections"],
)
def section_windows(
    section: str = Path(..., description="Section ID, e.g. S01"),
):
    """Return all available maintenance block windows for the given section."""
    windows = get_section_windows(section)
    if not windows:
        raise HTTPException(
            status_code=404,
            detail=f"No maintenance windows found for section '{section}'.",
        )
    return WindowsResponse(section=section, windows=windows, count=len(windows))


# ============================================================
# OPTIMIZE
# ============================================================

@app.post(
    "/optimize/{section}",
    response_model=OptimizeResponse,
    summary="Run V4 optimization for a section",
    tags=["Optimization"],
)
def optimize_section(
    section: str = Path(..., description="Section ID, e.g. S01"),
    request: OptimizeRequest = OptimizeRequest(),
):
    """
    Execute the V4 CP-SAT maintenance block optimization for the given section.

    - **section**: Railway section ID (e.g. `S01`)
    - **safety_buffer_min**: Minutes of clearance before/after each train movement *(prototype parameter — not an official Indian Railways rule)*
    - **solver_time_limit_sec**: CP-SAT solver wall-clock time limit per section

    Returns a structured plan with:
    - Baseline (rule-based sequential) metrics
    - Optimized block schedule
    - Per-block explainability
    - Comparison summary

    > All results are from a **synthetic prototype simulation**.
    """
    try:
        result = run_optimization(
            section=section,
            safety_buffer_min=request.safety_buffer_min,
            solver_time_limit_sec=request.solver_time_limit_sec,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimization failed unexpectedly: {e}",
        )

    return result

# ============================================================
# AI DECISION SUPPORT
# ============================================================

@app.post(
    "/ai/explain-plan/{section}",
    summary="Generate AI explanation for an optimized plan",
    tags=["AI Decision Support"],
)
def explain_plan(
    section: str = Path(..., description="Section ID, e.g. S01"),
optimization_result: dict = Body(...),
):
    """
    Generate an AI explanation for the already optimized plan.

    IMPORTANT:
    - OR-Tools generates the schedule.
    - OR-Tools constraints remain authoritative.
    - Qwen3 only explains the supplied optimization result.
    - No second optimization is performed here.
    - No cloud AI API is used.
    """

    try:
        # Run optimization once and use that exact result for AI explanation.
        optimization_result = run_optimization(
            section=section,
            safety_buffer_min=15,
            solver_time_limit_sec=30,
        )

        ai_explanation = generate_plan_explanation(
            optimization_result
        )

        return {
            "section": section,
            "ai_model": "qwen3:1.7b",
            "source": "local_ollama",
            "optimization_status": optimization_result.get(
                "status",
                "UNKNOWN",
            ),
            "ai_explanation": ai_explanation,
            "disclaimer": (
                "AI-generated explanation based on a synthetic "
                "prototype optimization result. "
                "It is not an official railway operating recommendation."
            ),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI explanation failed: {e}",
        )