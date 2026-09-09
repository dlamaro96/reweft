import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Pulse as Activity, ArrowRight, ArrowsClockwise, CheckCircle, Database, DownloadSimple, FileMagnifyingGlass as FileSearch,
  Gear, Info, List, LockKey, MagnifyingGlass, Pause, Play, Plus, SignOut, Sparkle, Warning, X,
} from '@phosphor-icons/react';
import { ApiError } from '../api/liveTypes';
import type {
  AssessmentRecord, EvidenceRecord, InferenceProfileRecord, LiveFinding, LiveSession,
  ProjectRecord, RunStateRecord, RuntimeDescriptor, SourceRecord, WorkspaceRecord,
} from '../api/liveTypes';
import { bootstrapWorkspace, clearSession, getRuntime, liveApi, loadSession, saveSession } from '../api/liveClient';
import { Badge, Button, Card, EmptyState, Notice, PanelHeader, Progress, SkeletonPage, StatusBadge } from '../components/Ui';
import { DemoApp, Sidebar, usePath } from './App';

type RuntimeStatus =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; descriptor: RuntimeDescriptor };

type WorkspaceData = {
  workspace: WorkspaceRecord | null;
  projects: ProjectRecord[];
  profiles: InferenceProfileRecord[];
  runs: AssessmentRecord[];
};

const liveMeta: Record<string, { title: string; eyebrow: string; description: string }> = {
  '/overview': { title: 'Workspace overview', eyebrow: 'Live runtime', description: 'Configured projects and actual records returned by this workspace.' },
  '/connections': { title: 'Connections', eyebrow: 'Live configuration', description: 'Create read-only sources and run explicit connectivity checks.' },
  '/assessments': { title: 'Assessments', eyebrow: 'Live runtime', description: 'Start and control evidence-driven investigations with recorded configuration.' },
  '/estate': { title: 'Estate & lineage', eyebrow: 'Collected evidence', description: 'Actual evidence collected for the selected assessment. Missing evidence remains visible.' },
  '/reports': { title: 'Reports & semantics', eyebrow: 'Run output', description: 'Semantic outputs produced by the selected live assessment.' },
  '/modernization': { title: 'Modernization studio', eyebrow: 'Run output', description: 'Target proposal data returned by the selected assessment.' },
  '/migration': { title: 'Migration & validation', eyebrow: 'Run output', description: 'Generated work packages and validation state without invented dates or results.' },
  '/findings': { title: 'Findings & evidence', eyebrow: 'Live evidence', description: 'Findings and evidence references returned by the current run.' },
  '/settings': { title: 'Workspace settings', eyebrow: 'Live configuration', description: 'Inference profiles and the active browser session.' },
};

export function App() {
  const [forcedMode, setForcedMode] = useState<'demo' | null>(() => new URLSearchParams(window.location.search).get('mode') === 'demo' ? 'demo' : null);
  const [runtime, setRuntime] = useState<RuntimeStatus>({ phase: 'loading' });
  const [session, setSession] = useState<LiveSession | null>(() => loadSession());
  const loadRuntime = useCallback(() => {
    const controller = new AbortController();
    setRuntime({ phase: 'loading' });
    getRuntime(controller.signal)
      .then(descriptor => setRuntime({ phase: 'ready', descriptor }))
      .catch(error => setRuntime({ phase: 'error', message: error instanceof Error ? error.message : 'Runtime discovery failed' }));
    return () => controller.abort();
  }, []);

  useEffect(() => loadRuntime(), [loadRuntime]);

  if (forcedMode === 'demo') return <DemoApp />;
  if (runtime.phase === 'loading') return <RuntimeLoading />;
  if (runtime.phase === 'error') return <RuntimeUnavailable message={runtime.message} retry={loadRuntime} openDemo={() => setForcedMode('demo')} />;
  if (runtime.descriptor.mode === 'demo') return <DemoApp />;
  if (!session && runtime.descriptor.mode === 'bootstrap') return <BootstrapOnboarding onComplete={setSession} openDemo={() => setForcedMode('demo')} />;
  if (!session) return <SessionConnect onComplete={setSession} openDemo={() => setForcedMode('demo')} />;
  return <LiveConsole session={session} descriptor={runtime.descriptor} onSignOut={() => { clearSession(); setSession(null); }} />;
}

function RuntimeLoading() {
  return <div className="runtime-gate"><div className="runtime-gate__brand"><div className="brand-mark" aria-hidden="true"><i/><i/><i/></div><strong>Reweft</strong></div><div className="runtime-gate__content"><SkeletonPage/><p className="runtime-loading-label">Detecting local runtime…</p></div></div>;
}

function RuntimeUnavailable({ message, retry, openDemo }: { message: string; retry: () => void; openDemo: () => void }) {
  return <RuntimeFrame title="The Reweft API is unavailable" description="Live mode cannot start until runtime discovery succeeds.">
    <Notice tone="danger" title="Runtime discovery failed">{message}. No synthetic records were substituted.</Notice>
    <div className="runtime-actions"><Button variant="primary" icon={<ArrowsClockwise size={17}/>} onClick={retry}>Retry API</Button><Button onClick={openDemo}>Open synthetic demo</Button></div>
  </RuntimeFrame>;
}

function RuntimeFrame({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <div className="onboarding-shell"><div className="onboarding-brand"><div className="brand-mark" aria-hidden="true"><i/><i/><i/></div><span><strong>Reweft</strong><small>Estate modernization</small></span></div><main className="onboarding-card"><Badge tone="accent">Local runtime</Badge><h1>{title}</h1><p className="onboarding-lede">{description}</p>{children}</main><p className="onboarding-footnote"><LockKey size={14}/> Credentials remain in this browser session and are never included in exports.</p></div>;
}

function BootstrapOnboarding({ onComplete, openDemo }: { onComplete: (session: LiveSession) => void; openDemo: () => void }) {
  const [form, setForm] = useState({ token: '', email: '', display_name: '', workspace_name: '' });
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => setForm(value => ({ ...value, [key]: event.target.value }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(undefined);
    try { onComplete(await bootstrapWorkspace(form)); }
    catch (reason) { setError(apiMessage(reason)); }
    finally { setBusy(false); }
  };
  return <RuntimeFrame title="Create the first workspace" description="Use the one-time bootstrap token printed by your local launcher. It is exchanged for a scoped bearer token.">
    <form className="onboarding-form" onSubmit={submit}>
      <Field label="Bootstrap token"><input type="password" required minLength={32} autoComplete="off" value={form.token} onChange={update('token')}/><small>Single-use and at least 32 characters.</small></Field>
      <div className="form-grid"><Field label="Email"><input type="email" required autoComplete="email" value={form.email} onChange={update('email')}/></Field><Field label="Display name"><input required maxLength={100} autoComplete="name" value={form.display_name} onChange={update('display_name')}/></Field></div>
      <Field label="Workspace name"><input required maxLength={100} value={form.workspace_name} onChange={update('workspace_name')}/></Field>
      {error && <Notice tone="danger" title="Bootstrap failed">{error}. The token was not saved.</Notice>}
      <div className="runtime-actions"><Button variant="primary" disabled={busy} icon={busy ? <ArrowsClockwise className="spin" size={17}/> : <ArrowRight size={17}/>}>{busy ? 'Creating…' : 'Create workspace'}</Button><Button type="button" onClick={openDemo}>Explore synthetic demo</Button></div>
    </form>
  </RuntimeFrame>;
}

function SessionConnect({ onComplete, openDemo }: { onComplete: (session: LiveSession) => void; openDemo: () => void }) {
  const [workspaceId, setWorkspaceId] = useState(''); const [token, setToken] = useState(''); const [error, setError] = useState<string>(); const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(undefined);
    const candidate = { workspaceId: workspaceId.trim(), token: token.trim() };
    try { await liveApi.workspace(candidate); saveSession(candidate); onComplete(candidate); }
    catch (reason) { setError(apiMessage(reason)); }
    finally { setBusy(false); }
  };
  return <RuntimeFrame title="Connect to a workspace" description="Enter an existing workspace ID and bearer token. Reweft verifies both before saving this browser session.">
    <form className="onboarding-form" onSubmit={submit}><Field label="Workspace ID"><input required value={workspaceId} onChange={event => setWorkspaceId(event.target.value)} autoComplete="off"/></Field><Field label="Bearer token"><input required type="password" value={token} onChange={event => setToken(event.target.value)} autoComplete="off"/></Field>{error && <Notice tone="danger" title="Authentication failed">{error}. Synthetic data was not loaded.</Notice>}<div className="runtime-actions"><Button variant="primary" disabled={busy} icon={busy ? <ArrowsClockwise className="spin" size={17}/> : <ArrowRight size={17}/>}>{busy ? 'Verifying…' : 'Open workspace'}</Button><Button type="button" onClick={openDemo}>Open synthetic demo</Button></div></form>
  </RuntimeFrame>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="field"><span>{label}</span>{children}</label>; }

function LiveConsole({ session, descriptor, onSignOut }: { session: LiveSession; descriptor: RuntimeDescriptor; onSignOut: () => void }) {
  const [path, navigate] = usePath(); const [menuOpen, setMenuOpen] = useState(false); const [toast, setToast] = useState<string>();
  const [data, setData] = useState<WorkspaceData>({ workspace: null, projects: [], profiles: [], runs: [] });
  const [loading, setLoading] = useState(true); const [loadErrors, setLoadErrors] = useState<string[]>([]); const [sources, setSources] = useState<SourceRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>(); const [runState, setRunState] = useState<RunStateRecord | null>(null); const [runLoading, setRunLoading] = useState(false); const [runError, setRunError] = useState<string>();
  const [evidenceRecords, setEvidenceRecords] = useState<EvidenceRecord[]>([]); const [evidenceLoading, setEvidenceLoading] = useState(false); const [evidenceError, setEvidenceError] = useState<string>();
  const meta = liveMeta[path] ?? liveMeta['/overview'];

  const refresh = useCallback(async () => {
    setLoading(true); setLoadErrors([]);
    const results = await Promise.allSettled([liveApi.workspace(session), liveApi.projects(session), liveApi.profiles(session), liveApi.assessments(session), liveApi.sources(session)]);
    const errors: string[] = [];
    setData(previous => ({
      workspace: takeResult(results[0], previous.workspace, 'Workspace', errors),
      projects: takeResult(results[1], previous.projects, 'Projects', errors),
      profiles: takeResult(results[2], previous.profiles, 'Inference profiles', errors),
      runs: takeResult(results[3], previous.runs, 'Assessments', errors),
    }));
    setSources(previous => takeResult(results[4], previous, 'Sources', errors));
    setLoadErrors(errors); setLoading(false);
  }, [session]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!selectedRunId && data.runs[0]) setSelectedRunId(data.runs[0].id); }, [data.runs, selectedRunId]);
  useEffect(() => {
    if (!selectedRunId) { setRunState(null); setRunError(undefined); setEvidenceRecords([]); setEvidenceError(undefined); return; }
    const controller = new AbortController(); setRunLoading(true); setEvidenceLoading(true); setRunError(undefined); setEvidenceError(undefined);
    void Promise.allSettled([liveApi.runState(session, selectedRunId, controller.signal), liveApi.evidence(session, selectedRunId)]).then(([stateResult,evidenceResult]) => {
      if (stateResult.status === 'fulfilled') setRunState(stateResult.value); else if (!(stateResult.reason instanceof DOMException && stateResult.reason.name === 'AbortError')) { setRunState(null); setRunError(apiMessage(stateResult.reason)); }
      if (evidenceResult.status === 'fulfilled') setEvidenceRecords(evidenceResult.value); else if (!(evidenceResult.reason instanceof DOMException && evidenceResult.reason.name === 'AbortError')) { setEvidenceRecords([]); setEvidenceError(apiMessage(evidenceResult.reason)); }
      setRunLoading(false); setEvidenceLoading(false);
    });
    return () => controller.abort();
  }, [selectedRunId, session, data.runs]);

  const go = (next: string) => { navigate(next); setMenuOpen(false); };
  const notify = (message: string) => { setToast(message); window.setTimeout(() => setToast(undefined), 3000); };
  const context: LivePageContext = { session, data, refresh, sources, setSources, selectedRunId, setSelectedRunId, runState, runLoading, runError, evidenceRecords, evidenceLoading, evidenceError, notify };
  return <div className="app-shell live-runtime">
    <a className="skip-link" href="#main-content">Skip to content</a><Sidebar path={path} open={menuOpen} onClose={() => setMenuOpen(false)} navigate={go}/>
    <div className="app-main"><header className="topbar"><button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><List size={21}/></button><div className="workspace-switcher workspace-switcher--static"><span className="workspace-avatar">{initials(data.workspace?.name ?? 'Live')}</span><span><strong>{data.workspace?.name ?? 'Authorized workspace'}</strong><small>{descriptor.persistence ?? 'Live API'}</small></span></div><div className="global-search global-search--status"><Activity size={17}/><span>Live runtime · authorized workspace</span></div><div className="topbar__actions"><Badge tone="success">Live</Badge><button className="icon-button" onClick={onSignOut} aria-label="Clear session and sign out"><SignOut size={19}/></button></div></header>
      <main id="main-content" className="content" tabIndex={-1}><div className="page-heading"><div><p className="eyebrow">{meta.eyebrow}</p><h1>{meta.title}</h1><p>{meta.description}</p></div><LivePageActions path={path} context={context}/></div>
        {loadErrors.length > 0 && <Notice tone="warning" title="Partial workspace data">{loadErrors.join(' · ')}. Successful sections remain visible; no demo records were substituted.</Notice>}
        {loading ? <SkeletonPage/> : <LivePage path={path} context={context}/>}</main></div>
    {toast && <div className="toast" role="status"><CheckCircle size={18} weight="fill"/>{toast}</div>}
  </div>;
}

type LivePageContext = {
  session: LiveSession; data: WorkspaceData; refresh: () => Promise<void>; sources: SourceRecord[]; setSources: React.Dispatch<React.SetStateAction<SourceRecord[]>>;
  selectedRunId?: string; setSelectedRunId: (id: string) => void; runState: RunStateRecord | null; runLoading: boolean; runError?: string; notify: (message: string) => void;
  evidenceRecords: EvidenceRecord[]; evidenceLoading: boolean; evidenceError?: string;
};

function LivePageActions({ path, context }: { path: string; context: LivePageContext }) {
  if (path === '/overview') return <Button icon={<ArrowsClockwise size={16}/>} onClick={() => void context.refresh()}>Refresh</Button>;
  if (path === '/assessments') return null;
  if (context.selectedRunId && ['/modernization','/migration','/findings','/reports','/estate'].includes(path)) return <Button icon={<DownloadSimple size={16}/>} onClick={() => void downloadExport(context)}>Export run</Button>;
  return null;
}

function LivePage({ path, context }: { path: string; context: LivePageContext }) {
  if (path === '/connections') return <LiveConnections context={context}/>;
  if (path === '/assessments') return <LiveAssessments context={context}/>;
  if (path === '/estate') return <LiveEvidence context={context}/>;
  if (path === '/reports') return <LiveReports context={context}/>;
  if (path === '/modernization') return <LiveModernizationView context={context}/>;
  if (path === '/migration') return <LiveMigration context={context}/>;
  if (path === '/findings') return <LiveFindings context={context}/>;
  if (path === '/settings') return <LiveSettings context={context}/>;
  return <LiveOverview context={context}/>;
}

function LiveOverview({ context }: { context: LivePageContext }) {
  const { data } = context;
  return <div className="page-stack"><div className="metric-grid"><LiveMetric label="Projects" value={data.projects.length} detail="Configured in this workspace"/><LiveMetric label="Inference profiles" value={data.profiles.length} detail={data.profiles.length ? 'Configuration records' : 'No profile configured'}/><LiveMetric label="Assessments" value={data.runs.length} detail={data.runs[0] ? stateLabel(data.runs[0].state) : 'No assessments started'}/><LiveMetric label="Evidence artifacts" value={context.runState?.evidence?.length ?? 0} detail={context.runState ? 'Returned by selected run' : 'No run state selected'}/></div>
    {data.projects.length === 0 ? <CreateProjectCard context={context}/> : <Card><PanelHeader title="Projects" description="Actual project records returned by the workspace."/><div className="project-grid">{data.projects.map(project => <div className="project-record" key={project.id}><div><strong>{project.name}</strong><small>{project.id}</small></div><Badge tone="success">Configured</Badge></div>)}</div></Card>}
    <Card><PanelHeader title="Recent assessments" description="State is reported by the API; Reweft does not infer completion."/>{data.runs.length ? <RunTable runs={data.runs} selected={context.selectedRunId} onSelect={context.setSelectedRunId}/> : <EmptyState title="No assessments yet">Create a project and inference profile, then configure the first assessment.</EmptyState>}</Card>
  </div>;
}

function LiveMetric({ label, value, detail }: { label: string; value: number; detail: string }) { return <div className="metric-card metric-card--static"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }

function CreateProjectCard({ context }: { context: LivePageContext }) {
  const [name,setName]=useState(''); const [busy,setBusy]=useState(false); const [error,setError]=useState<string>();
  const submit=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError(undefined);try{await liveApi.createProject(context.session,name);setName('');await context.refresh();context.notify('Project created.')}catch(reason){setError(apiMessage(reason))}finally{setBusy(false)}};
  return <Card><PanelHeader title="Create the first project" description="Projects scope assessment configuration and evidence."/><form className="inline-form" onSubmit={submit}><Field label="Project name"><input required maxLength={100} value={name} onChange={event=>setName(event.target.value)} placeholder="e.g. Legacy estate assessment"/></Field><Button variant="primary" disabled={busy} icon={busy?<ArrowsClockwise className="spin" size={16}/>:<Plus size={16}/>}>{busy?'Creating…':'Create project'}</Button></form>{error&&<Notice tone="danger" title="Project not created">{error}</Notice>}</Card>;
}

function LiveConnections({ context }: { context: LivePageContext }) {
  const [form,setForm]=useState({name:'',host:'',port:'5432',database:'',username:'',credential_ref:'',schemas:'',sslmode:'verify-full'}); const [busy,setBusy]=useState(false); const [error,setError]=useState<string>(); const [testing,setTesting]=useState<string>();
  const update=(key:keyof typeof form)=>(event:React.ChangeEvent<HTMLInputElement|HTMLSelectElement>)=>setForm(value=>({...value,[key]:event.target.value}));
  const submit=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError(undefined);try{const created=await liveApi.createPostgresSource(context.session,{name:form.name,host:form.host,port:Number(form.port),database:form.database,username:form.username,credential_ref:form.credential_ref,sslmode:form.sslmode,scope:{schemas:form.schemas.split(',').map(value=>value.trim()).filter(Boolean)}});context.setSources(items=>[created,...items]);context.notify('Source configuration created. No connection test has run.')}catch(reason){setError(apiMessage(reason))}finally{setBusy(false)}};
  const test=async(source:SourceRecord)=>{setTesting(source.id);setError(undefined);try{const result=await liveApi.testSource(context.session,source.id);const resultStatus='test_status' in result?result.test_status:result.status;context.setSources(items=>items.map(item=>item.id===source.id?{...item,...result,test_status:resultStatus}:item));context.notify('Connection test response recorded.')}catch(reason){setError(apiMessage(reason))}finally{setTesting(undefined)}};
  return <div className="page-stack"><Notice title="Source safety">Creating a connection stores configuration only. Connectivity and metadata access remain “not tested” until the explicit API test returns.</Notice><Card><PanelHeader title="Add PostgreSQL source" description="Only a secret reference is sent; this form never accepts a raw password."/><form onSubmit={submit}><div className="form-grid"><Field label="Connection name"><input required value={form.name} onChange={update('name')}/></Field><Field label="Host"><input required value={form.host} onChange={update('host')}/></Field><Field label="Port"><input required inputMode="numeric" value={form.port} onChange={update('port')}/></Field><Field label="Database"><input required value={form.database} onChange={update('database')}/></Field><Field label="Username"><input required value={form.username} onChange={update('username')}/></Field><Field label="Credential reference"><input required pattern="secret://.*" placeholder="secret://source/runtime-default" value={form.credential_ref} onChange={update('credential_ref')}/></Field><Field label="Permitted schemas"><input required placeholder="analytics, reporting" value={form.schemas} onChange={update('schemas')}/></Field><Field label="TLS mode"><select value={form.sslmode} onChange={update('sslmode')}><option value="verify-full">Verify full</option><option value="verify-ca">Verify CA</option><option value="require">Require encryption</option><option value="disable">Disabled (trusted local fixture only)</option></select></Field></div>{error&&<Notice tone="danger" title="Source operation failed">{error}. No fixture result was shown.</Notice>}<div className="form-actions"><Button variant="primary" disabled={busy} icon={busy?<ArrowsClockwise className="spin" size={16}/>:<Plus size={16}/>}>{busy?'Saving…':'Save source'}</Button></div></form></Card><Card><PanelHeader title="Configured sources" description="Persisted source records returned by the authorized workspace API."/>{context.sources.length?<div className="connection-list">{context.sources.map(source=><div className="connection-row" key={source.id}><div className="source-icon"><Database size={20}/></div><div className="connection-row__main"><h3>{source.name}</h3><p>{source.connector??'postgresql'} · {source.id}</p></div><StatusBadge status={source.test_status??source.status??'Not tested'}/><Button disabled={testing===source.id} onClick={()=>void test(source)}>{testing===source.id?'Testing…':'Test connection'}</Button></div>)}</div>:<EmptyState title="No configured sources">Create a source above to begin a bounded connection test.</EmptyState>}</Card></div>;
}

function LiveAssessments({ context }: { context: LivePageContext }) {
  const [objective,setObjective]=useState(''); const [projectId,setProjectId]=useState(context.data.projects[0]?.id??''); const [profileId,setProfileId]=useState(context.data.profiles[0]?.id??''); const [busy,setBusy]=useState(false); const [error,setError]=useState<string>();
  const start=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError(undefined);try{const run=await liveApi.createAssessment(context.session,{project_id:projectId,objective,scope:{source_ids:context.sources.map(source=>source.id)},inference_profile_id:profileId||null});await liveApi.transition(context.session,run.id,'start',run.version);await context.refresh();context.setSelectedRunId(run.id);context.notify('Assessment started with the recorded configuration.')}catch(reason){setError(apiMessage(reason))}finally{setBusy(false)}};
  return <div className="page-stack"><Card><PanelHeader title="New assessment" description="Starting records the selected project, source scope and inference profile."/>{context.data.projects.length===0?<EmptyState title="A project is required">Create a project from Overview before starting an assessment.</EmptyState>:<form onSubmit={start}><div className="form-grid"><Field label="Project"><select required value={projectId} onChange={event=>setProjectId(event.target.value)}>{context.data.projects.map(project=><option value={project.id} key={project.id}>{project.name}</option>)}</select></Field><Field label="Inference profile"><select value={profileId} onChange={event=>setProfileId(event.target.value)}><option value="">No inference profile</option>{context.data.profiles.map(profile=><option value={profile.id} key={profile.id}>{profile.name}</option>)}</select></Field></div><Field label="Objective"><textarea required minLength={3} maxLength={1000} value={objective} onChange={event=>setObjective(event.target.value)} placeholder="Describe the assessment objective and decision to support."/></Field><p className="form-hint">Source scope: {context.sources.length ? `${context.sources.length} source(s) created in this browser session` : 'No source IDs selected'}</p>{error&&<Notice tone="danger" title="Assessment not started">{error}. No run state was simulated.</Notice>}<div className="form-actions"><Button variant="primary" disabled={busy} icon={busy?<ArrowsClockwise className="spin" size={16}/>:<Play size={16}/>}>{busy?'Starting…':'Start assessment'}</Button></div></form>}</Card><Card><PanelHeader title="Assessment runs" description="Select a run to inspect its current state."/>{context.data.runs.length?<><RunTable runs={context.data.runs} selected={context.selectedRunId} onSelect={context.setSelectedRunId}/><RunControl context={context}/></>:<EmptyState title="No run records">Start the first assessment above.</EmptyState>}</Card></div>;
}

function RunTable({runs,selected,onSelect}:{runs:AssessmentRecord[];selected?:string;onSelect:(id:string)=>void}){return <div className="table-wrap"><table><thead><tr><th>Objective</th><th>State</th><th>Version</th><th>Updated</th></tr></thead><tbody>{runs.map(run=><tr key={run.id} className={selected===run.id?'selected-row':''}><td><button onClick={()=>onSelect(run.id)}>{run.objective}</button><small>{run.id}</small></td><td><StatusBadge status={stateLabel(run.state)}/></td><td>v{run.version}</td><td>{formatDate(run.updated_at)}</td></tr>)}</tbody></table></div>}

function RunControl({context}:{context:LivePageContext}){const run=context.data.runs.find(item=>item.id===context.selectedRunId);const [busy,setBusy]=useState(false);const [error,setError]=useState<string>();if(!run)return null;const transition=async(action:string)=>{setBusy(true);setError(undefined);try{await liveApi.transition(context.session,run.id,action,run.version);await context.refresh();context.notify(`${actionLabel(action)} request completed.`)}catch(reason){setError(apiMessage(reason))}finally{setBusy(false)}};const canPause=['collecting','analyzing','designing','verifying'].includes(run.state);const canResume=run.state==='paused-by-user';const canStart=run.state==='queued';const canCancel=!['completed','completed-with-gaps','failed','cancelled'].includes(run.state);return <div className="run-control"><div><strong>Selected run</strong><small>{run.id} · current state: {stateLabel(run.state)}</small></div><div>{canStart&&<Button disabled={busy} icon={<Play size={16}/>} onClick={()=>void transition('start')}>Start</Button>}{canPause&&<Button disabled={busy} icon={<Pause size={16}/>} onClick={()=>void transition('pause')}>Pause</Button>}{canResume&&<Button disabled={busy} icon={<Play size={16}/>} onClick={()=>void transition('resume')}>Resume</Button>}{canCancel&&<Button variant="danger" disabled={busy} icon={<X size={16}/>} onClick={()=>void transition('cancel')}>Cancel</Button>}</div>{error&&<Notice tone="danger" title="Transition failed">{error}. The displayed run was not changed locally.</Notice>}</div>}

function LiveEvidence({ context }: { context: LivePageContext }) {
  if (!context.selectedRunId) return <Card><EmptyState title="Select an assessment">Create or select a live assessment before inspecting evidence.</EmptyState></Card>;
  if (context.evidenceLoading) return <SkeletonPage/>;
  if (context.evidenceError) return <Card><Notice tone="danger" title="Evidence unavailable">{context.evidenceError}. No synthetic evidence was substituted.</Notice></Card>;
  return <Card><PanelHeader title="Collected evidence" description="Authorized evidence records returned by the workspace endpoint."/><EvidenceContent evidence={context.evidenceRecords}/></Card>;
}
function EvidenceContent({evidence}:{evidence:EvidenceRecord[]}){if(!evidence.length)return <EmptyState title="No evidence returned">The selected run-state response contains no evidence. This is not treated as a confirmed absence in the source estate.</EmptyState>;return <div className="table-wrap"><table><thead><tr><th>Object</th><th>Platform</th><th>Status</th><th>Classification</th><th>Locator</th></tr></thead><tbody>{evidence.map(item=><tr key={item.id}><td>{item.native_object_id}<small>{item.environment}</small></td><td>{item.platform}</td><td><StatusBadge status={item.collection_status}/></td><td>{item.classification}</td><td><code>{item.locator.external_label}: {item.locator.value}</code></td></tr>)}</tbody></table></div>}

function LiveFindings({ context }: { context: LivePageContext }) { return <LiveRunSection context={context} title="Findings unavailable"><FindingsContent findings={context.runState?.findings??[]}/></LiveRunSection>; }
function FindingsContent({findings}:{findings:LiveFinding[]}){if(!findings.length)return <EmptyState title="No findings returned">The selected live run has not returned findings. No synthetic risks or conclusions are shown.</EmptyState>;return <div className="finding-list detailed">{findings.map(finding=><div className="finding-row" key={finding.id}><span className={`severity-mark severity-mark--${(finding.severity??'low').toLowerCase()}`}/><div className="finding-row__body"><div><strong>{finding.title}</strong><span>{finding.id}</span></div><p>{finding.interpretation??'No interpretation was returned.'}</p><div><StatusBadge status={finding.severity??'Unranked'}/><StatusBadge status={finding.knowledge_state??'Unspecified'}/><span className="evidence-count"><FileSearch size={14}/>{finding.evidence_ids?.length??0} evidence references</span></div></div></div>)}</div>}

function LiveModernizationView({context}:{context:LivePageContext}){const modernization=context.runState?.modernization;return <LiveRunSection context={context} title="Modernization unavailable">{modernization?<div className="two-column wide-left"><Card><PanelHeader title={modernization.scenario??'Target proposal'} description="Returned by the selected run."/><StatusBadge status={modernization.status??'Unspecified'}/><h3 className="section-label">Target models</h3>{modernization.target_models?.length?<div className="project-grid">{modernization.target_models.map(model=><div className="project-record" key={model.name}><div><strong>{model.name}</strong><small>{model.kind??'Model'}{model.grain?` · ${model.grain}`:''}</small></div></div>)}</div>:<EmptyState title="No target models">The run returned a proposal container without target model records.</EmptyState>}</Card><Card><PanelHeader title="Assumptions"/>{modernization.assumptions?.length?<ul className="plain-list">{modernization.assumptions.map(item=><li key={item}><Warning size={15}/>{item}</li>)}</ul>:<EmptyState title="No assumptions returned">No assumptions were included in this response.</EmptyState>}</Card></div>:<EmptyState title="No modernization proposal">The selected run has not returned a modernization specification.</EmptyState>}</LiveRunSection>}

function LiveMigration({context}:{context:LivePageContext}){const packages=context.runState?.modernization?.work_packages??[];return <LiveRunSection context={context} title="Migration output unavailable">{packages.length?<Card><PanelHeader title="Work packages" description="No duration or completion is inferred by the frontend."/><div className="work-packages">{packages.map((item,index)=><div key={item.id??item.name}><span className="package-number">{String(index+1).padStart(2,'0')}</span><div><h3>{item.name}</h3><p>{item.description??'No description returned.'}</p></div><StatusBadge status={item.status??'Unspecified'}/>{index<packages.length-1&&<span className="package-link"/>}</div>)}</div></Card>:<EmptyState title="No work packages returned">The selected run has not produced migration work packages.</EmptyState>}</LiveRunSection>}

function LiveReports({context}:{context:LivePageContext}){const metrics=context.runState?.modernization?.metrics??[];const reports=context.runState?.modernization?.report_dispositions??[];return <LiveRunSection context={context} title="Semantic output unavailable">{metrics.length||reports.length?<div className="page-stack"><Card><PanelHeader title="Metric definitions" description="Evidence-derived definitions remain separate where their semantics differ."/>{metrics.length?<div className="table-wrap"><table><thead><tr><th>Metric</th><th>Definition</th><th>Grain</th><th>Additivity</th></tr></thead><tbody>{metrics.map(metric=><tr key={metric.name}><td><strong>{metric.name}</strong></td><td><code>{metric.definition}</code></td><td>{metric.grain??'Unresolved'}</td><td>{metric.additive_behavior??'Unresolved'}</td></tr>)}</tbody></table></div>:<EmptyState title="No metrics returned">No metric specifications were produced.</EmptyState>}</Card><Card><PanelHeader title="Report dispositions"/>{reports.length?<div className="project-grid">{reports.map((report,index)=><div className="project-record" key={`${report.report}-${index}`}><div><strong>{report.report??'Unnamed report'}</strong><small>{report.reason??'No additional rationale returned.'}</small></div><StatusBadge status={report.disposition??'Unresolved'}/></div>)}</div>:<EmptyState title="No report dispositions">No report mappings were produced.</EmptyState>}</Card></div>:<EmptyState title="No report-semantic records returned">The selected run has not produced metric definitions or report dispositions.</EmptyState>}</LiveRunSection>}

function LiveRunSection({context,title,children}:{context:LivePageContext;title:string;children:React.ReactNode}){if(!context.selectedRunId)return <Card><EmptyState title="Select an assessment">Create or select a live assessment before inspecting run output.</EmptyState></Card>;if(context.runLoading)return <SkeletonPage/>;if(context.runError)return <Card><Notice tone="danger" title={title}>{context.runError}. No synthetic run output was substituted.</Notice></Card>;if(!context.runState)return <Card><EmptyState title={title}>The API returned no state for the selected run.</EmptyState></Card>;return <div className="page-stack">{context.runState.partial&&<Notice tone="warning" title="Partial run state">The API marked this response partial. Missing records are unknown, not absent.</Notice>}{context.runState.progress!=null&&<Card><Progress value={context.runState.progress} label={context.runState.message??context.runState.phase??stateLabel(context.runState.run.state)}/></Card>}{children}</div>}

function LiveSettings({context}:{context:LivePageContext}){const [form,setForm]=useState({name:'',provider:'openai_compatible',endpoint_class:'local',model:'',base_url:'',credential_ref:''});const [busy,setBusy]=useState(false);const [error,setError]=useState<string>();const [testing,setTesting]=useState<string>();const update=(key:keyof typeof form)=>(event:React.ChangeEvent<HTMLInputElement|HTMLSelectElement>)=>setForm(value=>({...value,[key]:event.target.value}));const submit=async(event:React.FormEvent)=>{event.preventDefault();setBusy(true);setError(undefined);try{await liveApi.createProfile(context.session,{name:form.name,provider:form.provider,endpoint_class:form.endpoint_class,model:form.model,base_url:form.base_url||null,credential_ref:form.credential_ref||null,tls_verify:true,allowed_data_classes:['metadata'],fallback_profile_ids:[]});await context.refresh();context.notify('Inference profile created. Capabilities remain not tested.')}catch(reason){setError(apiMessage(reason))}finally{setBusy(false)}};const test=async(profile:InferenceProfileRecord)=>{setTesting(profile.id);setError(undefined);try{await liveApi.testProfile(context.session,profile.id);await context.refresh();context.notify('Provider test response recorded.')}catch(reason){setError(apiMessage(reason))}finally{setTesting(undefined)}};return <div className="page-stack"><Card><PanelHeader title="Add inference profile" description="Model routing is configured at runtime; TLS verification cannot be disabled."/><form onSubmit={submit}><div className="form-grid"><Field label="Profile name"><input required value={form.name} onChange={update('name')}/></Field><Field label="Provider"><select value={form.provider} onChange={update('provider')}><option value="openai_compatible">OpenAI-compatible</option><option value="openai">OpenAI</option><option value="azure_openai">Azure OpenAI</option></select></Field><Field label="Endpoint class"><select value={form.endpoint_class} onChange={update('endpoint_class')}><option value="local">Local</option><option value="private">Private</option><option value="public">Public</option></select></Field><Field label="Model identifier"><input required value={form.model} onChange={update('model')}/></Field><Field label="Base URL"><input type="url" placeholder="https://provider.example/v1" value={form.base_url} onChange={update('base_url')}/></Field><Field label="Credential reference"><input pattern="secret://.*" placeholder="secret://inference/default" value={form.credential_ref} onChange={update('credential_ref')}/></Field></div>{error&&<Notice tone="danger" title="Inference operation failed">{error}. No provider success was inferred.</Notice>}<div className="form-actions"><Button variant="primary" disabled={busy} icon={busy?<ArrowsClockwise className="spin" size={16}/>:<Plus size={16}/>}>{busy?'Saving…':'Create profile'}</Button></div></form></Card><Card><PanelHeader title="Inference profiles" description="Capability status comes only from provider test responses."/>{context.data.profiles.length?<div className="profile-list">{context.data.profiles.map(profile=><div key={profile.id}><div><strong>{profile.name}</strong><small>{profile.provider} · {profile.model} · {profile.endpoint_class}</small></div><StatusBadge status={profile.capabilities?.test_status??(profile.last_successful_test?'Test recorded':'Not tested')}/><Button disabled={testing===profile.id} onClick={()=>void test(profile)}>{testing===profile.id?'Testing…':'Test provider'}</Button></div>)}</div>:<EmptyState title="No inference profiles">Create a profile above. Assessment can also run without inference when supported by the objective.</EmptyState>}</Card><Card><PanelHeader title="Browser session"/><dl className="fact-list"><div><dt>Workspace ID</dt><dd><code>{context.session.workspaceId}</code></dd></div><div><dt>Token storage</dt><dd>Current tab session only</dd></div><div><dt>Export behavior</dt><dd>Token never included</dd></div></dl></Card></div>}

async function downloadExport(context:LivePageContext){if(!context.selectedRunId)return;try{const blob=await liveApi.exportRun(context.session,context.selectedRunId);const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=`reweft-${context.selectedRunId}.zip`;anchor.click();URL.revokeObjectURL(url);context.notify('Authorized run export downloaded.')}catch(reason){context.notify(`Export failed: ${apiMessage(reason)}`)}}

function takeResult<T>(result:PromiseSettledResult<T>,fallback:T,label:string,errors:string[]):T{if(result.status==='fulfilled')return result.value;errors.push(`${label}: ${apiMessage(result.reason)}`);return fallback}
function apiMessage(error:unknown){if(error instanceof ApiError)return error.status===0?`API unreachable: ${error.message}`:`${error.status}: ${error.message}`;return error instanceof Error?error.message:'Unknown error'}
function initials(name:string){return name.split(/\s+/).slice(0,2).map(part=>part[0]?.toUpperCase()).join('')||'RW'}
function stateLabel(state:string){return state.split('-').map(word=>word.charAt(0).toUpperCase()+word.slice(1)).join(' ')}
function actionLabel(action:string){return action.charAt(0).toUpperCase()+action.slice(1)}
function formatDate(value:string){const date=new Date(value);return Number.isNaN(date.getTime())?value:new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date)}
