import {
  Archive,
  Bell,
  Bookmark,
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ExternalLink,
  EyeOff,
  Filter,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  MapPin,
  Menu,
  Clock,
  Download,
  Play,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { cancelRun, createApplication, createSavedSearch, deleteSavedSearch, eventUrl, fetchAnalytics, fetchApplications, fetchJobs, fetchNotifications, fetchRun, fetchSavedSearches, fetchSourceHealth, launchSearch, markNotificationRead, runSavedSearch, updateApplication, updateJob, updateSavedSearch } from "./api";
import type { AnalyticsOverview, Application, Job, LocalJobMeta, Notification, SavedSearch, SearchCriteria, SearchRun, SourceHealth } from "./types";

const SOURCES = ["linkedin", "hellowork", "francetravail", "wttj", "adzuna"];
const SOURCE_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  hellowork: "HelloWork",
  francetravail: "France Travail",
  wttj: "Welcome to the Jungle",
  adzuna: "Adzuna",
};
const PAGE_SIZE = 12;

const emptyCriteria: SearchCriteria = {
  keywords: [],
  location: "France",
  contract_types: [],
  experience_levels: [],
  workplace_types: [],
  date_posted: "past_week",
  sort_by: "date",
  max_results: 50,
};

function loadMeta(): Record<string, LocalJobMeta> {
  try {
    return JSON.parse(localStorage.getItem("jobpilot-meta") ?? "{}");
  } catch {
    return {};
  }
}

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Job | null>(null);
  const [meta, setMeta] = useState<Record<string, LocalJobMeta>>(loadMeta);
  const [showSearch, setShowSearch] = useState(false);
  const [showApplications, setShowApplications] = useState(false);
  const [showOperations, setShowOperations] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [savedOnly, setSavedOnly] = useState(false);
  const [sort, setSort] = useState("newest");
  const [run, setRun] = useState<SearchRun | null>(null);

  const refreshJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
      sort,
    });
    if (query.trim()) params.set("q", query.trim());
    if (sourceFilter) params.set("source", sourceFilter);
    if (locationFilter.trim()) params.set("location", locationFilter.trim());
    if (remoteOnly) params.set("remote", "true");
    try {
      const result = await fetchJobs(params);
      setJobs(result.items);
      setTotal(result.total);
      setMeta((current) => {
        const next = { ...current };
        result.items.forEach((job) => {
          next[job.id] = { saved: job.saved, hidden: job.hidden, notes: job.user_notes ?? undefined, tags: job.user_tags };
        });
        return next;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load jobs");
    } finally {
      setLoading(false);
    }
  }, [locationFilter, page, query, remoteOnly, sort, sourceFilter]);

  useEffect(() => {
    const timer = window.setTimeout(refreshJobs, 200);
    return () => window.clearTimeout(timer);
  }, [refreshJobs]);

  useEffect(() => {
    localStorage.setItem("jobpilot-meta", JSON.stringify(meta));
  }, [meta]);

  const updateMeta = async (id: string, patch: Partial<LocalJobMeta>) => {
    setMeta((current) => ({ ...current, [id]: { ...current[id], ...patch } }));
    try { await updateJob(id, patch); } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save changes"); }
  };

  const visibleJobs = useMemo(
    () => jobs.filter((job) => !meta[job.id]?.hidden && (!savedOnly || meta[job.id]?.saved)),
    [jobs, meta, savedOnly],
  );

  const startSearch = async (criteria: SearchCriteria, sources: string[], details: boolean) => {
    setError(null);
    try {
      const created = await launchSearch(criteria, sources, details);
      setShowSearch(false);
      const initial = await fetchRun(created.id);
      setRun(initial);
      const stream = new EventSource(eventUrl(created.id));
      const update = async () => setRun(await fetchRun(created.id));
      ["source_started", "job_found", "source_completed", "source_failed"].forEach((name) =>
        stream.addEventListener(name, update),
      );
      const finish = async () => {
        stream.close();
        await update();
        await refreshJobs();
      };
      stream.addEventListener("search_completed", finish);
      stream.addEventListener("search_cancelled", finish);
      stream.addEventListener("search_failed", finish);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not launch search");
    }
  };

  return (
    <div className="app-shell">
      <Sidebar open={mobileNav} onClose={() => setMobileNav(false)} onApplications={() => { setShowApplications(true); setMobileNav(false); }} onOperations={() => { setShowOperations(true); setMobileNav(false); }} />
      <main className="main-content">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu /></button>
          <div className="global-search"><Search size={18} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} placeholder="Search jobs, companies, skills…" /></div>
          <div className="top-actions"><button className="icon-button" aria-label="Notifications" onClick={() => setShowOperations(true)}><Bell /></button><div className="avatar">AB</div></div>
        </header>

        <section className="page">
          <div className="page-heading">
            <div><p className="eyebrow">JOB DISCOVERY</p><h1>Find your next opportunity</h1><p>Search across five sources, all in one focused workspace.</p></div>
            <button className="primary-button" onClick={() => setShowSearch(true)}><Plus size={18} /> New search</button>
          </div>

          {run && !["completed", "completed_with_errors", "failed", "cancelled"].includes(run.status) && (
            <RunProgress run={run} onCancel={async () => { await cancelRun(run.id); }} />
          )}

          <div className="stats-grid">
            <Stat label="Jobs discovered" value={total.toLocaleString()} detail="Across all searches" icon={<BriefcaseBusiness />} />
            <Stat label="Saved roles" value={Object.values(meta).filter((item) => item.saved).length.toString()} detail="Your shortlist" icon={<Bookmark />} />
            <Stat label="Active sources" value="5" detail="All systems ready" icon={<CircleDot />} accent />
          </div>

          <div className="results-layout">
            <aside className="filters-panel">
              <div className="panel-title"><span><SlidersHorizontal size={17} /> Filters</span><button onClick={() => { setSourceFilter(""); setLocationFilter(""); setRemoteOnly(false); setSavedOnly(false); }}>Reset</button></div>
              <FilterField label="Location"><div className="input-with-icon"><MapPin size={16} /><input value={locationFilter} onChange={(e) => { setLocationFilter(e.target.value); setPage(0); }} placeholder="Paris, Lyon…" /></div></FilterField>
              <FilterField label="Source"><select value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setPage(0); }}><option value="">All sources</option>{SOURCES.map((source) => <option key={source} value={source}>{SOURCE_LABELS[source]}</option>)}</select></FilterField>
              <label className="toggle-row"><span>Remote only</span><input type="checkbox" checked={remoteOnly} onChange={(e) => { setRemoteOnly(e.target.checked); setPage(0); }} /><i /></label>
              <label className="toggle-row"><span>Saved jobs</span><input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} /><i /></label>
              <div className="filter-tip"><Sparkles size={18} /><div><strong>Compatibility scores</strong><p>Ready for your future typesafe.ai connection.</p></div></div>
            </aside>

            <div className="results-panel">
              <div className="results-toolbar"><div><h2>{savedOnly ? "Saved opportunities" : "Latest opportunities"}</h2><p>{total} matching jobs</p></div><div className="sort-control"><ListFilter size={16} /><select value={sort} onChange={(e) => setSort(e.target.value)}><option value="newest">Recently discovered</option><option value="posted">Recently posted</option><option value="title">Job title</option></select></div></div>
              {error && <div className="error-banner"><X size={18} /> {error}<button onClick={refreshJobs}>Retry</button></div>}
              {loading ? <LoadingCards /> : visibleJobs.length ? (
                <div className="job-list">{visibleJobs.map((job) => <JobCard key={job.id} job={job} meta={meta[job.id]} onOpen={() => setSelected(job)} onSave={() => updateMeta(job.id, { saved: !meta[job.id]?.saved })} onHide={() => updateMeta(job.id, { hidden: true })} />)}</div>
              ) : <EmptyState onSearch={() => setShowSearch(true)} />}
              <div className="pagination"><button disabled={page === 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft /></button><span>Page {page + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span><button disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((value) => value + 1)}><ChevronRight /></button></div>
            </div>
          </div>
        </section>
      </main>
      {showSearch && <SearchModal onClose={() => setShowSearch(false)} onSubmit={startSearch} />}
      {selected && <button className="track-fab" onClick={async () => { try { await createApplication(selected.id); setSelected(null); setShowApplications(true); } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not track application"); } }}><BriefcaseBusiness /> Track application</button>}
      {selected && <JobDrawer job={selected} meta={meta[selected.id]} onClose={() => setSelected(null)} onUpdate={(patch) => updateMeta(selected.id, patch)} onTrack={async () => { try { await createApplication(selected.id); setSelected(null); setShowApplications(true); } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not track application"); } }} />}
      {showApplications && <ApplicationsBoard onClose={() => setShowApplications(false)} />}
      {showOperations && <OperationsCenter onClose={() => setShowOperations(false)} />}
    </div>
  );
}

function Sidebar({ open, onClose, onApplications, onOperations }: { open: boolean; onClose: () => void; onApplications: () => void; onOperations: () => void }) {
  return <><div className={`mobile-overlay ${open ? "show" : ""}`} onClick={onClose} /><aside className={`sidebar ${open ? "open" : ""}`}><div className="brand"><div className="brand-mark">J</div><div><strong>JobPilot</strong><span>Career command center</span></div><button className="mobile-only" onClick={onClose}><X /></button></div><nav><p>WORKSPACE</p><a className="active"><Search /> Discover jobs</a><a><Bookmark /> Saved</a><a onClick={onApplications}><Archive /> Applications</a><p>INSIGHTS</p><a onClick={onApplications}><LayoutDashboard /> Overview</a><a onClick={onOperations}><Clock /> Automations</a><a><Sparkles /> Compatibility <small>Soon</small></a></nav><div className="sidebar-bottom"><a onClick={onOperations}><Settings /> Operations</a><div className="profile"><div className="avatar">AB</div><div><strong>Your workspace</strong><span>Private & local</span></div><ChevronDown /></div></div></aside></>;
}

function Stat({ label, value, detail, icon, accent = false }: { label: string; value: string; detail: string; icon: React.ReactNode; accent?: boolean }) { return <div className={`stat-card ${accent ? "accent" : ""}`}><div className="stat-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>; }
function FilterField({ label, children }: { label: string; children: React.ReactNode }) { return <label className="filter-field"><span>{label}</span>{children}</label>; }

function JobCard({ job, meta, onOpen, onSave, onHide }: { job: Job; meta?: LocalJobMeta; onOpen: () => void; onSave: () => void; onHide: () => void }) {
  const source = job.sources[0]?.source ?? "source";
  return <article className="job-card" onClick={onOpen}><div className="company-logo">{job.company.slice(0, 2).toUpperCase()}</div><div className="job-main"><div className="job-title-row"><div><h3>{job.title}</h3><p><Building2 size={14} /> {job.company}</p></div><div className="job-actions"><button className={meta?.saved ? "saved" : ""} onClick={(e) => { e.stopPropagation(); onSave(); }} aria-label="Save job"><Bookmark /></button><button onClick={(e) => { e.stopPropagation(); onHide(); }} aria-label="Hide job"><EyeOff /></button></div></div><div className="job-meta"><span><MapPin /> {job.location}</span>{job.contract_type && <span>{job.contract_type.toUpperCase()}</span>}{job.remote && <span className="remote-pill">Remote</span>}</div><div className="job-footer"><span className={`source-badge ${source}`}>{SOURCE_LABELS[source] ?? source}</span><span>{relativeDate(job.posted_at ?? job.first_seen_at)}</span>{meta?.tags?.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div></div><ChevronRight className="card-chevron" /></article>;
}

function RunProgress({ run, onCancel }: { run: SearchRun; onCancel: () => void }) { return <div className="run-progress"><div className="run-heading"><div><LoaderCircle className="spin" /><span><strong>Searching job boards</strong><small>{run.total_jobs} jobs found so far</small></span></div><button onClick={onCancel}>Cancel</button></div><div className="source-progress">{run.sources.map((source) => <div key={source.source}><span>{SOURCE_LABELS[source.source] ?? source.source}</span><strong>{source.job_count}</strong><i className={source.status} /></div>)}</div></div>; }

function SearchModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (criteria: SearchCriteria, sources: string[], details: boolean) => void }) {
  const [keywords, setKeywords] = useState(""); const [criteria, setCriteria] = useState(emptyCriteria); const [sources, setSources] = useState(SOURCES); const [details, setDetails] = useState(false);
  const toggle = (source: string) => setSources((current) => current.includes(source) ? current.filter((item) => item !== source) : [...current, source]);
  const submit = (event: FormEvent) => { event.preventDefault(); onSubmit({ ...criteria, keywords: keywords.split(",").map((item) => item.trim()).filter(Boolean) }, sources, details); };
  return <div className="modal-backdrop" onMouseDown={onClose}><form className="search-modal" onSubmit={submit} onMouseDown={(e) => e.stopPropagation()}><div className="modal-header"><div><p className="eyebrow">NEW SEARCH</p><h2>What are you looking for?</h2></div><button type="button" onClick={onClose}><X /></button></div><div className="form-grid"><FilterField label="Keywords"><input autoFocus value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Python, QA automation, React…" /></FilterField><FilterField label="Exact job title"><input value={criteria.title ?? ""} onChange={(e) => setCriteria({ ...criteria, title: e.target.value })} placeholder="Senior QA Engineer" /></FilterField><FilterField label="Location"><input value={criteria.location} onChange={(e) => setCriteria({ ...criteria, location: e.target.value })} /></FilterField><FilterField label="Radius"><select value={criteria.radius_km ?? ""} onChange={(e) => setCriteria({ ...criteria, radius_km: e.target.value ? Number(e.target.value) : undefined })}><option value="">Any distance</option>{[5, 10, 25, 50, 100].map((value) => <option key={value} value={value}>{value} km</option>)}</select></FilterField><FilterField label="Published"><select value={criteria.date_posted} onChange={(e) => setCriteria({ ...criteria, date_posted: e.target.value })}><option value="past_24h">Past 24 hours</option><option value="past_week">Past week</option><option value="past_month">Past month</option><option value="any_time">Any time</option></select></FilterField><FilterField label="Maximum results"><input type="number" min="1" max="500" value={criteria.max_results} onChange={(e) => setCriteria({ ...criteria, max_results: Number(e.target.value) })} /></FilterField></div><div className="source-selector"><span>Search sources</span><div>{SOURCES.map((source) => <button type="button" className={sources.includes(source) ? "selected" : ""} key={source} onClick={() => toggle(source)}>{sources.includes(source) && <Check />} {SOURCE_LABELS[source]}</button>)}</div></div><label className="details-check"><input type="checkbox" checked={details} onChange={(e) => setDetails(e.target.checked)} /> Fetch full LinkedIn descriptions <small>Slower, but provides richer results</small></label><div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={!sources.length}><Search /> Launch search</button></div></form></div>;
}

function JobDrawer({ job, meta, onClose, onUpdate, onTrack }: { job: Job; meta?: LocalJobMeta; onClose: () => void; onUpdate: (patch: Partial<LocalJobMeta>) => void; onTrack: () => void }) {
  const [tag, setTag] = useState("");
  const addTag = () => { if (tag.trim()) { onUpdate({ tags: [...new Set([...(meta?.tags ?? []), tag.trim()])] }); setTag(""); } };
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="job-drawer" onMouseDown={(e) => e.stopPropagation()}><div className="drawer-top"><button onClick={onClose}><X /></button></div><div className="drawer-content"><div className="drawer-company"><div className="company-logo large">{job.company.slice(0, 2).toUpperCase()}</div><div><span>{job.company}</span><h2>{job.title}</h2><p><MapPin /> {job.location}</p></div></div><div className="drawer-actions"><button className={meta?.saved ? "primary-button" : "secondary-button"} onClick={() => onUpdate({ saved: !meta?.saved })}><Bookmark /> {meta?.saved ? "Saved" : "Save job"}</button><a className="primary-button" href={job.sources[0]?.url ?? job.canonical_url ?? "#"} target="_blank" rel="noreferrer">View original <ExternalLink /></a></div><div className="detail-chips">{job.contract_type && <span>{job.contract_type.toUpperCase()}</span>}{job.experience_level && <span>{job.experience_level}</span>}{job.remote && <span>Remote friendly</span>}</div><section><h3>About the role</h3><p className="description">{job.description ?? "A full description was not provided by this source. Open the original listing for complete details."}</p></section><section><h3>Your notes</h3><textarea value={meta?.notes ?? ""} onChange={(e) => onUpdate({ notes: e.target.value })} placeholder="Interview questions, company research, reminders…" /></section><section><h3>Tags</h3><div className="tag-editor">{meta?.tags?.map((item) => <button key={item} onClick={() => onUpdate({ tags: meta.tags?.filter((value) => value !== item) })}>{item} <X /></button>)}<div><Tag /><input value={tag} onChange={(e) => setTag(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addTag(); }} placeholder="Add tag" /><button onClick={addTag}>Add</button></div></div></section></div></aside></div>;
}

const PIPELINE = ["saved", "preparing", "applied", "screening", "interview", "offer"];

function ApplicationsBoard({ onClose }: { onClose: () => void }) {
  const [applications, setApplications] = useState<Application[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [items, overview] = await Promise.all([fetchApplications(), fetchAnalytics()]);
      setApplications(items);
      setAnalytics(overview);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load applications");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const move = async (id: string, stage: string) => {
    setApplications((items) => items.map((item) => item.id === id ? { ...item, stage } : item));
    try { await updateApplication(id, { stage }); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not move application"); await refresh(); }
  };

  return <div className="applications-screen">
    <header><div><p className="eyebrow">APPLICATION TRACKER</p><h1>Your opportunity pipeline</h1><p>Drag applications between stages and keep every next step visible.</p></div><button className="icon-button" onClick={onClose}><X /></button></header>
    <div className="pipeline-stats"><Stat label="Total applications" value={String(analytics?.total_applications ?? 0)} detail="All tracked roles" icon={<BriefcaseBusiness />} /><Stat label="Active pipeline" value={String(analytics?.active_applications ?? 0)} detail="Open opportunities" icon={<CircleDot />} accent /><Stat label="Overdue follow-ups" value={String(analytics?.overdue_tasks ?? 0)} detail="Need attention" icon={<Bell />} /></div>
    {error && <div className="error-banner"><X /> {error}<button onClick={refresh}>Retry</button></div>}
    {loading ? <div className="board-loading"><LoaderCircle className="spin" /> Loading pipeline…</div> : <div className="kanban-board">{PIPELINE.map((stage) => {
      const items = applications.filter((item) => item.stage === stage);
      return <section className="kanban-column" key={stage} onDragOver={(event) => event.preventDefault()} onDrop={(event) => move(event.dataTransfer.getData("application/id"), stage)}><div className="kanban-heading"><span>{stage}</span><b>{items.length}</b></div><div>{items.map((application) => <article draggable onDragStart={(event) => event.dataTransfer.setData("application/id", application.id)} className="application-card" key={application.id}><div className="company-logo">{application.job.company.slice(0, 2).toUpperCase()}</div><h3>{application.job.title}</h3><p>{application.job.company}</p><span><MapPin /> {application.job.location}</span>{application.next_action_at && <small>Next: {new Date(application.next_action_at).toLocaleDateString()}</small>}<select value={application.stage} onChange={(event) => move(application.id, event.target.value)}>{PIPELINE.map((value) => <option key={value} value={value}>{value}</option>)}<option value="rejected">rejected</option><option value="withdrawn">withdrawn</option><option value="archived">archived</option></select></article>)}</div></section>;
    })}</div>}
  </div>;
}

function OperationsCenter({ onClose }: { onClose: () => void }) {
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("France");
  const [interval, setInterval] = useState(1440);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [searches, alerts, sources] = await Promise.all([fetchSavedSearches(), fetchNotifications(), fetchSourceHealth()]);
      setSavedSearches(searches); setNotifications(alerts); setHealth(sources.items); setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load operations"); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createSavedSearch({ name, criteria: { ...emptyCriteria, keywords: keywords.split(",").map((value) => value.trim()).filter(Boolean), location }, sources: SOURCES, include_details: false, schedule_enabled: true, schedule_interval_minutes: interval });
      setName(""); setKeywords(""); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save automation"); }
  };

  return <div className="operations-screen">
    <header><div><p className="eyebrow">AUTOMATION & OPERATIONS</p><h1>Keep your search working</h1><p>Schedule searches, review source health, notifications, and exports.</p></div><button className="icon-button" onClick={onClose}><X /></button></header>
    {error && <div className="error-banner"><X /> {error}<button onClick={refresh}>Retry</button></div>}
    <div className="operations-grid">
      <section className="operations-card automation-card"><h2>Saved searches</h2><form onSubmit={add}><input required value={name} onChange={(event) => setName(event.target.value)} placeholder="Automation name" /><input required value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="Keywords, comma separated" /><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Location" /><select value={interval} onChange={(event) => setInterval(Number(event.target.value))}><option value={60}>Every hour</option><option value={360}>Every 6 hours</option><option value={1440}>Every day</option><option value={10080}>Every week</option></select><button className="primary-button"><Plus /> Save schedule</button></form>
        <div className="automation-list">{savedSearches.map((item) => <article key={item.id}><div><strong>{item.name}</strong><span>{item.criteria.keywords?.join(", ") || "All jobs"} · {item.criteria.location}</span><small>{item.schedule_enabled ? `Next: ${item.next_run_at ? new Date(item.next_run_at).toLocaleString() : "pending"}` : "Paused"}</small></div><label className="mini-toggle"><input type="checkbox" checked={item.schedule_enabled} onChange={async (event) => { await updateSavedSearch(item.id, { schedule_enabled: event.target.checked }); await refresh(); }} /> enabled</label><button title="Run now" onClick={async () => { await runSavedSearch(item.id); await refresh(); }}><Play /></button><button title="Delete" onClick={async () => { await deleteSavedSearch(item.id); await refresh(); }}><Trash2 /></button></article>)}</div>
      </section>
      <section className="operations-card"><h2>Source health</h2><div className="health-list">{health.map((source) => <div key={source.name}><i className={source.last_status === "failed" ? "failed" : "healthy"} /><span><strong>{SOURCE_LABELS[source.name] ?? source.name}</strong><small>{source.last_error ?? source.last_status.replaceAll("_", " ")}</small></span></div>)}</div><h2 className="export-title">Data exports</h2><div className="export-actions"><a href="/api/export/jobs.csv"><Download /> Jobs CSV</a><a href="/api/export/applications.csv"><Download /> Applications CSV</a></div></section>
      <section className="operations-card notifications-card"><h2>Notifications</h2>{notifications.length ? notifications.map((item) => <button className={item.read ? "read" : ""} key={item.id} onClick={async () => { if (!item.read) await markNotificationRead(item.id); await refresh(); }}><Bell /><span><strong>{item.title}</strong><small>{item.message} · {new Date(item.created_at).toLocaleString()}</small></span></button>) : <p className="quiet-state">No notifications yet.</p>}</section>
    </div>
  </div>;
}

function LoadingCards() { return <div className="job-list">{[1, 2, 3, 4].map((item) => <div className="job-card skeleton" key={item}><i /><div><b /><span /><small /></div></div>)}</div>; }
function EmptyState({ onSearch }: { onSearch: () => void }) { return <div className="empty-state"><div><Filter /></div><h3>No opportunities found</h3><p>Try changing your filters or launch a fresh multi-source search.</p><button className="primary-button" onClick={onSearch}><Plus /> New search</button></div>; }
function relativeDate(value: string) { const days = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 86400000)); return days === 0 ? "Today" : days === 1 ? "Yesterday" : `${days} days ago`; }
