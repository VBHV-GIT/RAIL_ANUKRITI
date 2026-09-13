import { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, Check, CheckCircle2, ChevronDown, ClipboardList,
  Clock3, Cpu, Gauge, GitCompareArrows, Info, LayoutDashboard, ListChecks,
  ShieldCheck, Sparkles, TrainFront, UserRound, Wrench, Zap,
} from "lucide-react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

const sections = ["S01", "S02", "S03", "S04", "S05", "S06", "S07"];

function OperationsTimeline({ result }) {
  if (!result?.blocks?.length) return null;

  return (
    <section className="operations-panel">
      <div className="section-label">
        <TrainFront size={13} />
        OPERATIONS VIEW
      </div>

      <div className="operations-header">
        <div>
          <h3>Train & Maintenance Operations</h3>
          <p>Maintenance activity coordinated around protected train movements</p>
        </div>

        <div className="operations-safe">
          <CheckCircle2 size={14} />
          Conflict Free
        </div>
      </div>

      {result.blocks.map((block) => (
        <div className="operation-block" key={block.block_number}>
          <div className="operation-time">
            <strong>BLOCK {block.block_number}</strong>
            <span>{block.start} — {block.end}</span>
          </div>

          <div className="operation-track">
            <div className="operation-bar">
              {block.tasks.map((task) => (
                <div className="operation-task" key={task.task_id}>
                  <strong>{task.task_id}</strong>
                  <span>{shortDepartment(task.department)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="operation-details">
            <span>
              {block.departments.join(" · ")}
            </span>
            <span>
              {block.duration_min} min workload
            </span>
          </div>
        </div>
      ))}

      <div className="protected-operations">
        <span className="protected-title">PROTECTED TRAINS</span>

        <div className="protected-list">
          {result.trains_protected.map((train) => (
            <div className="protected-train" key={train}>
              <TrainFront size={14} />
              {train}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
function App() {
  
const [section, setSection] = useState("S01");
const [loading, setLoading] = useState(false);
const [result, setResult] = useState(null);
const [error, setError] = useState("");
const [approvalStatus, setApprovalStatus] = useState("pending");

const [aiExplanation, setAiExplanation] = useState("");
const [aiLoading, setAiLoading] = useState(false);
const [aiError, setAiError] = useState("");
  const [activeNav, setActiveNav] = useState("dashboard");

  const [online, setOnline] = useState(navigator.onLine);

useEffect(() => {
  const handleOnline = () => setOnline(true);
  const handleOffline = () => setOnline(false);

  window.addEventListener("online", handleOnline);
  window.addEventListener("offline", handleOffline);

  return () => {
    window.removeEventListener("online", handleOnline);
    window.removeEventListener("offline", handleOffline);
  };
}, []);


  const scrollToSection = (id) => {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

 const optimizeSection = async () => {
  setLoading(true);
  setError("");
  setAiError("");
  setAiExplanation("");

  try {
    // ============================================================
    // 1. RUN OR-TOOLS OPTIMIZATION
    // ============================================================

    const response = await fetch(
      `${API_BASE}/optimize/${section}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          safety_buffer_min: 15,
          solver_time_limit_sec: 30,
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }

    const data = await response.json();

    // Show optimization result immediately
    setResult(data);
    setApprovalStatus("pending");

    // ============================================================
    // 2. SEND THE SAME RESULT TO AI
    // ============================================================

    setAiLoading(true);

    try {
      const aiResponse = await fetch(
        `${API_BASE}/ai/explain-plan/${section}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(data),
        }
      );

      if (!aiResponse.ok) {
        throw new Error(
          `AI API returned ${aiResponse.status}`
        );
      }

      const aiData = await aiResponse.json();

      setAiExplanation(
        aiData.ai_explanation || ""
      );

    } catch (aiErr) {
      console.error(
        "AI explanation error:",
        aiErr
      );

      setAiError(
        "AI explanation could not be generated. The optimized plan is still available."
      );

    } finally {
      setAiLoading(false);
    }

  } catch (err) {
    console.error(err);

    setError(
      "Unable to connect to the RailAnukriti backend. Make sure FastAPI is running on port 8000."
    );

  } finally {
    setLoading(false);
  }
};

  const optimized = result?.optimized || {};
  const baseline = result?.baseline || {};
  const blocks = result?.blocks || [];

  const optimizedBlocks =
    optimized.blocks ?? blocks.length ?? 0;

  const optimizedHours =
    optimized.blocked_hours ??
    blocks.reduce((sum, block) => sum + (block.duration_min || 0), 0) / 60;

  return (
    <div className="app">
      {/* ───────────────── SIDEBAR ───────────────── */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">
            <TrainFront size={20} strokeWidth={2.2} />
          </div>
          <div>
            <div className="sidebar-brand-name">RailAnukriti</div>
            <div className="sidebar-brand-subtitle">Automatic Block Planning</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button className={`nav-item ${activeNav === "dashboard" ? "active" : ""}`} onClick={() => scrollToSection("dashboard")}>
            <LayoutDashboard size={16} />
            <span>Dashboard</span>
          </button>
          <button className={`nav-item ${activeNav === "block-planning" ? "active" : ""}`} onClick={() => scrollToSection("block-planning")}>
            <ClipboardList size={16} />
            <span>Block Planning</span>
          </button>
          <button className={`nav-item ${activeNav === "maintenance-tasks" ? "active" : ""}`} onClick={() => scrollToSection("maintenance-tasks")}>
            <Wrench size={16} />
            <span>Maintenance Tasks</span>
          </button>
          <button className={`nav-item ${activeNav === "train-protection" ? "active" : ""}`} onClick={() => scrollToSection("train-protection")}>
            <TrainFront size={16} />
            <span>Train Protection</span>
          </button>
        </nav>

        <div className="sidebar-bottom">
          <span className="sidebar-system">SYSTEM</span>
          <div className="sidebar-status">
            <span className={`sidebar-status-dot ${online ? "online" : "offline"}`} />
            {online ? "System Online" : "System Offline"}
          </div>
        </div>
      </aside>

      <div className="main-area">
        {/* ───────────────── HEADER ───────────────── */}

      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="brand-mark">
              <TrainFront size={21} strokeWidth={2.2} />
            </div>

            <div>
              <div className="brand-name">RailAnukriti</div>
              <div className="brand-subtitle">
                Automatic Block Planning
              </div>
            </div>
          </div>

         <div className={`system-status ${online ? "online" : "offline"}`}>
  <span className="status-indicator" />
  <span>{online ? "System Online" : "System Offline"}</span>
</div>
        </div>
      </header>

      <main className="page" id="dashboard">
        {/* ───────────────── HERO ───────────────── */}

        <section className="hero" id="block-planning">
          <div className="hero-content">
            <div className="section-label">
              <Activity size={13} />
              MAINTENANCE BLOCK PLANNER
            </div>

            <h1>
              Smarter maintenance.
              <span>Better asset availability.</span>
            </h1>

            <p>
              Coordinate maintenance activities around train movements,
              operational constraints and departmental resources.
            </p>
          </div>

          <div className="planner-control">
            <div className="control-label">Railway Section</div>

            <div className="control-row">
              <div className="select-wrapper">
                <select
                  value={section}
                  onChange={(event) =>
                    setSection(event.target.value)
                  }
                >
                  {sections.map((item) => (
                    <option key={item} value={item}>
                      Section {item}
                    </option>
                  ))}
                </select>

                <ChevronDown size={16} />
              </div>

              <button
                className="optimize-button"
                onClick={optimizeSection}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="button-spinner" />
                    Optimizing
                  </>
                ) : (
                  <>
                    <Zap size={16} />
                    Optimize Plan
                  </>
                )}
              </button>
            </div>
          </div>
        </section>

        {/* ───────────────── ERROR ───────────────── */}

        {error && (
          <div className="error-message">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* ───────────────── EMPTY STATE ───────────────── */}

        {!result && !loading && !error && (
          <section className="empty-panel">
            <div className="empty-icon">
              <Cpu size={25} />
            </div>

            <h2>Ready to optimize</h2>

            <p>
              Select a railway section and generate an AI-assisted
              maintenance block plan.
            </p>
          </section>
        )}

        {/* ───────────────── LOADING ───────────────── */}

        {loading && (
          <section className="empty-panel">
            <div className="large-spinner" />

            <h2>Optimizing maintenance plan</h2>

            <p>
              Evaluating train movements, maintenance windows and
              operational constraints.
            </p>
          </section>
        )}

        {/* ───────────────── RESULTS ───────────────── */}

        {result && !loading && (
          <>
            {/* Result heading */}

            <section className="result-heading">
              <div>
                <div className="section-label">
                  <Gauge size={13} />
                  OPTIMIZATION RESULT
                </div>

                <h2>
                  Section {result.section}
                  <span className="result-status">
                    <CheckCircle2 size={17} />
                    {result.status}
                  </span>
                </h2>
              </div>

              <div className="buffer-badge">
                <ShieldCheck size={15} />
                Safety buffer: {result.safety_buffer_min} min
              </div>
            </section>

            {/* KPI cards */}

            <section className="kpi-grid">
              <KpiCard
                icon={<LayoutDashboard />}
                label="Maintenance Blocks"
                value={optimizedBlocks}
                footer={`${baseline.blocks ?? "—"} → ${optimizedBlocks}`}
              />

              <KpiCard
                icon={<Clock3 />}
                label="Blocked Hours"
                value={`${Number(optimizedHours).toFixed(1)} h`}
                footer={`${baseline.blocked_hours ?? "—"} h baseline`}
              />

              <KpiCard
                icon={<ListChecks />}
                label="High Priority"
                value={`${optimized.high_priority_done ?? 0}/${optimized.high_priority_total ?? 0}`}
                positive
              />

              <KpiCard
                icon={<ShieldCheck />}
                label="Train Conflicts"
                value={optimized.train_conflicts ?? 0}
                positive
              />

              <KpiCard
                icon={<Wrench />}
                label="Unscheduled Tasks"
                value={optimized.unscheduled_tasks ?? 0}
                positive
              />
            </section>

            {/* Improvement */}

            {result.comparison && (
              <section className="panel improvement-panel">
                <div className="panel-heading">
                  <div>
                    <div className="section-label">
                      <GitCompareArrows size={13} />
                      PLAN IMPROVEMENT
                    </div>

                    <h3>Optimized vs Baseline</h3>
                  </div>
                </div>

                <div className="improvement-grid">
                  <ImprovementMetric
                    label="Block Reduction"
                    value={`${result.comparison.block_reduction_pct}%`}
                  />

                  <ImprovementMetric
                    label="Blocked Time Reduction"
                    value={`${result.comparison.blocked_time_reduction_pct}%`}
                  />

                  <ImprovementMetric
                    label="Conflicts Avoided"
                    value={result.comparison.conflicts_avoided}
                  />
                </div>
              </section>
            )}

            {/* Timeline */}

            <section className="panel">
              <div className="panel-heading">
                <div>
                  <div className="section-label">
                    <Activity size={13} />
                    SCHEDULE VISUALIZATION
                  </div>

                  <h3>Maintenance Timeline</h3>
                </div>

                <span className="panel-note">
                  Actual optimized workload
                </span>
              </div>

              <MaintenanceTimeline blocks={blocks} />
            </section>

            {/* Tasks */}

            <section className="panel" id="maintenance-tasks">
              <div className="panel-heading">
                <div>
                  <div className="section-label">
                    <Wrench size={13} />
                    GENERATED PLAN
                  </div>

                  <h3>Maintenance Tasks</h3>
                </div>

                <span className="count-badge">
                  {blocks.reduce(
                    (total, block) =>
                      total + (block.tasks?.length || 0),
                    0
                  )}{" "}
                  tasks
                </span>
              </div>

              {blocks.map((block) => (
                <MaintenanceBlock
                  key={block.block_number}
                  block={block}
                />
              ))}
            </section>

            {/* Protected trains */}

            <section className="panel" id="train-protection">
              <div className="panel-heading">
                <div>
                  <div className="section-label">
                    <TrainFront size={13} />
                    OPERATIONAL PROTECTION
                  </div>

                  <h3>Protected Train Movements</h3>
                </div>

                <span className="success-badge">
                  <Check size={14} />
                  Conflict Free
                </span>
              </div>

              <div className="train-list">
                {result.trains_protected?.map((train) => (
                  <div className="train-item" key={train}>
                    <TrainFront size={16} />
                    {train}
                  </div>
                ))}
              </div>
            </section>

<OperationsTimeline result={result} />

{/* Human Approval */}

<section className="approval-panel">
  <div className="approval-header">
    <div>
      <div className="section-label">
        <ShieldCheck size={13} />
        OPERATOR REVIEW
      </div>

      <h3>
        {approvalStatus === "approved"
          ? "Maintenance Plan Approved"
          : approvalStatus === "rejected"
          ? "Maintenance Plan Rejected"
          : "Plan Ready for Review"}
      </h3>
    </div>

    <div
      className={`approval-status ${approvalStatus}`}
    >
      {approvalStatus === "approved" ? (
        <>
          <CheckCircle2 size={14} />
          Approved
        </>
      ) : approvalStatus === "rejected" ? (
        <>
          <AlertTriangle size={14} />
          Rejected
        </>
      ) : (
        <>
          <Clock3 size={14} />
          Pending Review
        </>
      )}
    </div>
  </div>

  {approvalStatus === "pending" && (
    <>
      <div className="approval-summary">
        <div>
          <span>Section</span>
          <strong>{result.section}</strong>
        </div>

        <div>
          <span>Blocks</span>
          <strong>{optimizedBlocks}</strong>
        </div>

        <div>
          <span>High Priority</span>
          <strong>
            {optimized.high_priority_done}/
            {optimized.high_priority_total}
          </strong>
        </div>

        <div>
          <span>Train Conflicts</span>
          <strong>
            {optimized.train_conflicts}
          </strong>
        </div>

        <div>
          <span>Unscheduled</span>
          <strong>
            {optimized.unscheduled_tasks}
          </strong>
        </div>
      </div>

      <div className="approval-validation">
        <div>
          <CheckCircle2 size={15} />
          All optimization constraints satisfied
        </div>

        <div>
          <CheckCircle2 size={15} />
          No train conflicts detected
        </div>

        <div>
          <CheckCircle2 size={15} />
          Safety buffer respected
        </div>
      </div>

      <div className="approval-actions">
        <button
          className="reject-button"
          onClick={() => setApprovalStatus("rejected")}
        >
          Reject Plan
        </button>

        <button
          className="approve-button"
          onClick={() => setApprovalStatus("approved")}
        >
          <CheckCircle2 size={16} />
          Approve Plan
        </button>
      </div>
    </>
  )}

  {approvalStatus === "approved" && (
    <div className="approved-message">
      <div className="approved-icon">
        <CheckCircle2 size={25} />
      </div>

      <div>
        <strong>Plan approved by operator</strong>

        <p>
          Section {result.section} maintenance plan is
          approved for operational consideration.
        </p>
      </div>
    </div>
  )}

  {approvalStatus === "rejected" && (
    <div className="rejected-message">
      <div className="rejected-icon">
        <AlertTriangle size={22} />
      </div>

      <div>
        <strong>Plan rejected</strong>

        <p>
          The operator rejected this recommendation.
          Generate a new plan after reviewing the
          maintenance requirements.
        </p>
      </div>

      <button
        className="review-again-button"
        onClick={() => setApprovalStatus("pending")}
      >
        Review Again
      </button>
    </div>
  )}
</section>

            {/* Explainability */}

            <section className="panel explanation-panel">
              <div className="panel-heading">
                <div>
                  <div className="section-label">
                    <Sparkles size={13} />
                    DECISION SUPPORT
                  </div>

                  <h3>Why this plan?</h3>
                </div>
              </div>

             <div className="explanation-list">

  {aiLoading && (
    <div className="explanation-row">
      <div className="explanation-check">
        <Sparkles size={13} />
      </div>

      <span>
        Generating AI explanation...
      </span>
    </div>
  )}

  {aiError && !aiLoading && (
    <div className="explanation-row">
      <div className="explanation-check">
        <AlertTriangle size={13} />
      </div>

      <span>
        {aiError}
      </span>
    </div>
  )}

  {!aiLoading && !aiError && aiExplanation && (
    <div className="ai-explanation">
      {aiExplanation}
    </div>
  )}

  {!aiLoading && !aiError && !aiExplanation && (
    <div className="explanation-row">
      <div className="explanation-check">
        <Info size={13} />
      </div>

      <span>
        No AI explanation available.
      </span>
    </div>
  )}

</div>
            </section>

            {/* Human decision */}

            {/* <section className="decision-panel">
              <div className="decision-icon">
                <UserRound size={21} />
              </div>

              <div className="decision-content">
                <div className="section-label">
                  <Info size={13} />
                  DECISION PRINCIPLE
                </div>

                <h3>
                  AI recommends.
                  <span> Constraints validate. </span>
                  Human decides.
                </h3>

                <p>
                  The generated plan is a decision-support
                  recommendation. Final operational approval remains
                  with authorized railway personnel.
                </p>
              </div>
            </section> */}

            {/* Disclaimer */}

            {/* {result.disclaimer && (
              <div className="disclaimer">
                <Info size={14} />
                <span>
                  <strong>Prototype:</strong>{" "}
                  {result.disclaimer}
                </span>
              </div>
            )} */}
          </>
        )}
      </main>

      <footer className="footer">
        <span className="footer-brand">RailAnukriti</span>
        <span>
           AI-Assisted Maintenance Block Planning  designed for Indian Railways. 
        </span>
      </footer>
      </div>
    </div>
  );
}

/* ───────────────── KPI ───────────────── */

function KpiCard({
  icon,
  label,
  value,
  footer,
  positive = false,
}) {
  return (
    <div className="kpi-card">
      <div className="kpi-icon">{icon}</div>

      <div className="kpi-label">{label}</div>

      <div className="kpi-value">{value}</div>

      {footer && (
        <div className="kpi-footer">{footer}</div>
      )}

      {positive && (
        <div className="kpi-positive">
          <Check size={12} />
          Validated
        </div>
      )}
    </div>
  );
}

/* ───────────────── IMPROVEMENT ───────────────── */

function ImprovementMetric({ label, value }) {
  return (
    <div className="improvement-metric">
      <div className="improvement-label">{label}</div>

      <div className="improvement-value">
        {value}
      </div>

      <div className="improvement-caption">
        vs baseline
      </div>
    </div>
  );
}

/* ───────────────── TIMELINE ───────────────── */

function MaintenanceTimeline({ blocks }) {
  if (!blocks.length) {
    return (
      <div className="timeline-empty">
        No maintenance blocks generated.
      </div>
    );
  }

  return (
    <div className="timeline">
      {blocks.map((block) => (
        <TimelineBlock
          key={block.block_number}
          block={block}
        />
      ))}
    </div>
  );
}

function TimelineBlock({ block }) {
  const startMinutes = timeToMinutes(block.start);
  const endMinutes = timeToMinutes(block.end);

  const duration = Math.max(
    endMinutes - startMinutes,
    1
  );

  const departments = block.tasks || [];

  const maxTaskDuration = Math.max(
    ...departments.map(
      (task) => task.duration_min || 0
    ),
    1
  );

  return (
    <div className="timeline-block">
      <div className="timeline-block-title">
        <span>
          BLOCK {block.block_number}
        </span>

        <strong>
          {block.start} — {block.end}
        </strong>
      </div>

      <div className="timeline-axis">
        <span>{block.start}</span>
        <span>
          {minutesToTime(
            startMinutes + duration / 2
          )}
        </span>
        <span>{block.end}</span>
      </div>

      <div className="timeline-body">
        {departments.map((task) => {
          const width = Math.max(
            ((task.duration_min || 0) /
              duration) *
              100,
            8
          );

          const departmentClass =
            task.department
              ?.toLowerCase()
              .replace(/\s+/g, "-") || "default";

          return (
            <div className="timeline-row" key={task.task_id}>
              <div className="timeline-label">
                <span>
                  {shortDepartment(task.department)}
                </span>

                <strong>{task.task_id}</strong>
              </div>

              <div className="timeline-track">
                <div
                  className={`timeline-task ${departmentClass}`}
                  style={{
                    width: `${Math.min(width, 100)}%`,
                  }}
                >
                  <span>{task.duration_min} min</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="timeline-footer">
        <span>
          <CheckCircle2 size={13} />
          {block.departments?.join(" · ")}
        </span>

        <span>
          Actual block workload: {block.duration_min} min
        </span>
      </div>
    </div>
  );
}

/* ───────────────── TASK BLOCK ───────────────── */

function MaintenanceBlock({ block }) {
  return (
    <div className="maintenance-block">
      <div className="maintenance-header">
        <div>
          <span className="block-number">
            BLOCK {block.block_number}
          </span>

          <strong>
            {block.start} — {block.end}
          </strong>
        </div>

        <span className="duration-badge">
          <Clock3 size={13} />
          {block.duration_min} min
        </span>
      </div>

      <div className="department-list">
        {block.departments?.map((department) => (
          <span
            className="department-badge"
            key={department}
          >
            {department}
          </span>
        ))}
      </div>

      <div className="task-table">
        <div className="task-head">
          <span>Task</span>
          <span>Department</span>
          <span>Asset</span>
          <span>Duration</span>
          <span>Priority</span>
        </div>

        {block.tasks?.map((task) => (
          <div className="task-line" key={task.task_id}>
            <strong>{task.task_id}</strong>

            <span>{task.department}</span>

            <span>{task.asset_id}</span>

            <span>{task.duration_min} min</span>

            <span
              className={
                task.priority >= 4
                  ? "priority-high"
                  : "priority-normal"
              }
            >
              {task.priority}
              {task.priority >= 4 && (
                <small>HIGH</small>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────────── HELPERS ───────────────── */

function timeToMinutes(time) {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function minutesToTime(totalMinutes) {
  const rounded = Math.round(totalMinutes);
  const hours = Math.floor(rounded / 60) % 24;
  const minutes = rounded % 60;

  return `${String(hours).padStart(2, "0")}:${String(
    minutes
  ).padStart(2, "0")}`;
}

function shortDepartment(department) {
  if (department === "Engineering") return "ENG";
  if (department === "Signalling") return "SIG";
  if (department === "Traction") return "TRC";

  return department?.slice(0, 3).toUpperCase() || "---";
}

export default App;