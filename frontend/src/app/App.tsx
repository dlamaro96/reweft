import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Pulse as Activity, Archive, ArrowDown, ArrowRight, ArrowsClockwise, BracketsCurly, Buildings,
  CaretDown, ChartDonut, CheckCircle, CirclesThreePlus, Code,
  Database, DownloadSimple, FileMagnifyingGlass as FileSearch, Gear, GitBranch,
  House, Kanban, List, MagnifyingGlass, Pause, Play, Plus, Robot, ShieldCheck,
  SlidersHorizontal, Sparkle, Table as TableIcon, UserCircle, Warning, X,
} from '@phosphor-icons/react';
import { getDemoSnapshot } from '../api/client';
import type { Asset, DemoSnapshot, Finding, Report, SourceSystem } from '../api/types';
import { Badge, Button, Card, EmptyState, Notice, PanelHeader, Progress, Segmented, SkeletonPage, StatusBadge } from '../components/Ui';

type IconType = typeof House;
type NavItem = { label: string; path: string; icon: IconType };

const primaryNav: NavItem[] = [
  { label: 'Overview', path: '/overview', icon: House },
  { label: 'Connections', path: '/connections', icon: Database },
  { label: 'Assessments', path: '/assessments', icon: Activity },
  { label: 'Estate & Lineage', path: '/estate', icon: GitBranch },
  { label: 'Reports & Semantics', path: '/reports', icon: ChartDonut },
  { label: 'Modernization', path: '/modernization', icon: Buildings },
  { label: 'Migration & Validation', path: '/migration', icon: Kanban },
  { label: 'Findings & Evidence', path: '/findings', icon: FileSearch },
];

const settingsNav: NavItem = { label: 'Settings', path: '/settings', icon: Gear };
const allNav = [...primaryNav, settingsNav];

const pageMeta: Record<string, { title: string; eyebrow: string; description: string }> = {
  '/overview': { title: 'Estate overview', eyebrow: 'BW retirement assessment', description: 'Coverage, risk and retirement readiness across the current synthetic estate.' },
  '/connections': { title: 'Connections', eyebrow: 'Configured sources', description: 'Scope, capabilities and source-safety posture for every evidence path.' },
  '/assessments': { title: 'Assessments', eyebrow: 'Autonomous investigation', description: 'Set an objective, inspect the effective policy, and follow evidence collection.' },
  '/estate': { title: 'Estate & lineage', eyebrow: '148 catalogued assets', description: 'Explore implemented logic and bounded cross-system dependency paths.' },
  '/reports': { title: 'Reports & semantics', eyebrow: '24 downstream outputs', description: 'Compare business meaning, usage evidence and target dispositions.' },
  '/modernization': { title: 'Modernization studio', eyebrow: 'Scenario v3', description: 'A versioned, target-neutral proposal grounded in collected evidence.' },
  '/migration': { title: 'Migration & validation', eyebrow: 'Proposed sequence', description: 'Work packages, coexistence gates and independent verification results.' },
  '/findings': { title: 'Findings & evidence', eyebrow: '11 open findings', description: 'Prioritized conclusions, assumptions and resolvable evidence locators.' },
  '/settings': { title: 'Workspace settings', eyebrow: 'Synthetic Manufacturing', description: 'Inference, access, policies, retention and local system diagnostics.' },
  '/welcome': { title: 'Welcome to Reweft', eyebrow: 'Understand your estate', description: 'Connect a real estate or inspect an isolated synthetic demonstration.' },
};

function usePath() {
  const [path, setPath] = useState(() => pageMeta[window.location.pathname] ? window.location.pathname : '/overview');
  useEffect(() => {
    const onPop = () => setPath(pageMeta[window.location.pathname] ? window.location.pathname : '/overview');
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const navigate = (next: string) => {
    window.history.pushState({}, '', next);
    setPath(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return [path, navigate] as const;
}

export function App() {
  const [path, navigate] = usePath();
  const [snapshot, setSnapshot] = useState<DemoSnapshot | null>(null);
  const [dataNotice, setDataNotice] = useState<string>();
  const [menuOpen, setMenuOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [toast, setToast] = useState<string>();
  const meta = pageMeta[path] ?? pageMeta['/overview'];

  useEffect(() => {
    const controller = new AbortController();
    getDemoSnapshot(controller.signal).then(result => {
      setSnapshot(result.snapshot);
      setDataNotice(result.notice);
    }).catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen(open => !open);
      }
      if (event.key === 'Escape') {
        setCommandOpen(false); setChatOpen(false); setMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const go = (next: string) => { navigate(next); setMenuOpen(false); setCommandOpen(false); };
  const notify = (message: string) => { setToast(message); window.setTimeout(() => setToast(undefined), 3000); };

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Sidebar path={path} open={menuOpen} onClose={() => setMenuOpen(false)} navigate={go} />
    <div className="app-main">
      <header className="topbar">
        <button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><List size={21} /></button>
        <button className="workspace-switcher" onClick={() => notify('Workspace switcher is limited to the isolated demo workspace.')}><span className="workspace-avatar">SM</span><span><strong>Synthetic Manufacturing</strong><small>BW retirement assessment</small></span><CaretDown size={14}/></button>
        <button className="global-search" onClick={() => setCommandOpen(true)}><MagnifyingGlass size={17}/><span>Search assets, evidence, commands…</span><kbd>⌘ K</kbd></button>
        <div className="topbar__actions"><Badge tone="warning">Demo · synthetic</Badge><button className="icon-button" aria-label="Open contextual assistant" onClick={() => setChatOpen(true)}><Sparkle size={19}/></button><button className="avatar-button" aria-label="Open profile">DA</button></div>
      </header>
      <main id="main-content" className="content" tabIndex={-1}>
        <div className="page-heading">
          <div><p className="eyebrow">{meta.eyebrow}</p><h1>{meta.title}</h1><p>{meta.description}</p></div>
          <PageActions path={path} navigate={go} notify={notify} />
        </div>
        {dataNotice && <Notice tone="warning" title="Local demo data">{dataNotice} All records below are synthetic and isolated from real workspaces.</Notice>}
        {!snapshot ? <SkeletonPage /> : <Page path={path} data={snapshot} navigate={go} notify={notify} />}
      </main>
    </div>
    {commandOpen && <CommandPalette onClose={() => setCommandOpen(false)} navigate={go} data={snapshot}/>} 
    {chatOpen && <ContextPanel onClose={() => setChatOpen(false)} path={path} />}
    {toast && <div className="toast" role="status"><CheckCircle size={18} weight="fill" />{toast}</div>}
  </div>;
}

function Sidebar({ path, open, onClose, navigate }: { path: string; open: boolean; onClose: () => void; navigate: (path: string) => void }) {
  return <><div className={`mobile-scrim ${open ? 'is-open' : ''}`} onClick={onClose}/><aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Primary navigation">
    <div className="brand"><div className="brand-mark" aria-hidden="true"><i/><i/><i/></div><div><strong>Reweft</strong><small>Estate modernization</small></div><button className="icon-button mobile-close" aria-label="Close navigation" onClick={onClose}><X size={18}/></button></div>
    <nav className="nav-list">{primaryNav.map(item => <NavButton key={item.path} item={item} active={path === item.path} onClick={() => navigate(item.path)}/>)}</nav>
    <div className="sidebar__footer"><NavButton item={settingsNav} active={path === settingsNav.path} onClick={() => navigate(settingsNav.path)}/><div className="source-policy"><ShieldCheck size={17} weight="fill"/><span><strong>Read-only policy</strong><small>Source mutations disabled</small></span></div></div>
  </aside></>;
}

function NavButton({ item, active, onClick }: { item: NavItem; active: boolean; onClick: () => void }) {
  const Icon = item.icon;
  return <button onClick={onClick} className={`nav-item ${active ? 'is-active' : ''}`} aria-current={active ? 'page' : undefined}><Icon size={18} weight={active ? 'fill' : 'regular'}/><span>{item.label}</span></button>;
}

function PageActions({ path, navigate, notify }: { path: string; navigate: (path: string) => void; notify: (message: string) => void }) {
  if (path === '/connections') return <Button variant="primary" icon={<Plus size={17}/>} onClick={() => notify('Connector setup opened in safe configuration mode.')}>Add connection</Button>;
  if (path === '/assessments') return <Button variant="primary" icon={<Play size={17} weight="fill"/>} onClick={() => notify('A new draft assessment configuration was created.')}>New assessment</Button>;
  if (path === '/findings') return <Button icon={<DownloadSimple size={17}/>} onClick={() => notify('Synthetic evidence index prepared for export.')}>Export index</Button>;
  if (path === '/welcome') return null;
  return <div className="page-actions"><Button icon={<DownloadSimple size={17}/>} onClick={() => notify('Synthetic workspace report prepared.')}>Export</Button><Button variant="primary" icon={<Activity size={17}/>} onClick={() => navigate('/assessments')}>View active run</Button></div>;
}

function Page({ path, data, navigate, notify }: { path: string; data: DemoSnapshot; navigate: (path: string) => void; notify: (message: string) => void }) {
  switch (path) {
    case '/welcome': return <WelcomePage navigate={navigate}/>;
    case '/connections': return <ConnectionsPage data={data} notify={notify}/>;
    case '/assessments': return <AssessmentsPage data={data} notify={notify}/>;
    case '/estate': return <EstatePage data={data} notify={notify}/>;
    case '/reports': return <ReportsPage data={data} notify={notify}/>;
    case '/modernization': return <ModernizationPage notify={notify}/>;
    case '/migration': return <MigrationPage notify={notify}/>;
    case '/findings': return <FindingsPage data={data} notify={notify}/>;
    case '/settings': return <SettingsPage notify={notify}/>;
    default: return <OverviewPage data={data} navigate={navigate}/>;
  }
}

function WelcomePage({ navigate }: { navigate: (path: string) => void }) {
  return <div className="welcome-grid">
    <button className="choice-card" onClick={() => navigate('/connections')}><span className="choice-card__icon"><Database size={25}/></span><Badge tone="accent">Real workspace</Badge><h2>Configure your estate</h2><p>Add a read-only source, choose an inference route, preview the permitted scope, then begin an assessment.</p><span className="text-link">Configure connections <ArrowRight size={16}/></span></button>
    <button className="choice-card choice-card--demo" onClick={() => navigate('/overview')}><span className="choice-card__icon"><CirclesThreePlus size={25}/></span><Badge tone="warning">No credentials required</Badge><h2>Explore the synthetic demo</h2><p>Trace an original manufacturing estate from evidence through a versioned modernization proposal.</p><span className="text-link">Open demo workspace <ArrowRight size={16}/></span></button>
    <Notice title="Inference data-egress policy">A workspace controls which evidence may leave Reweft and which configured model endpoint may receive it. There is no silent public-provider fallback.</Notice>
  </div>;
}

function OverviewPage({ data, navigate }: { data: DemoSnapshot; navigate: (path: string) => void }) {
  return <div className="page-stack">
    <div className="metric-grid">{data.inventory.map(metric => <button className="metric-card" key={metric.label} onClick={() => navigate(metric.href)}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.qualifier}</small><ArrowRight size={16}/></button>)}</div>
    <div className="overview-grid">
      <Card className="run-card"><PanelHeader title="Active assessment" description={`${data.run.id} · started ${data.run.started}`} action={<StatusBadge status={data.run.state}/>}/><Progress value={data.run.progress} label={data.run.current}/><div className="run-task-list">{data.run.tasks.map(task => <div key={task.label}><span className={`task-dot task-dot--${task.status.toLowerCase()}`}/><div><strong>{task.label}</strong><small>{task.detail}</small></div><StatusBadge status={task.status}/></div>)}</div><button className="inline-action" onClick={() => navigate('/assessments')}>Inspect run timeline <ArrowRight size={15}/></button></Card>
      <Card><PanelHeader title="Retirement readiness" description="Known conditions, not an automatic go/no-go decision."/><div className="readiness-ring"><svg viewBox="0 0 120 120" role="img" aria-label="4 of 6 retirement condition groups are evidenced"><circle cx="60" cy="60" r="49"/><circle className="ring-progress" cx="60" cy="60" r="49" strokeDasharray="205 308"/><text x="60" y="57">4 / 6</text><text className="ring-label" x="60" y="75">evidenced</text></svg><ul><li><CheckCircle weight="fill"/>Inventory and lineage</li><li><CheckCircle weight="fill"/>Semantic reconciliation</li><li><Warning weight="fill"/>Outbound dependency unresolved</li><li><Warning weight="fill"/>Cutover evidence not started</li></ul></div><button className="inline-action" onClick={() => navigate('/migration')}>View retirement conditions <ArrowRight size={15}/></button></Card>
    </div>
    <Card><PanelHeader title="Priority signals" description="Every conclusion below resolves to synthetic evidence." action={<button className="inline-action" onClick={() => navigate('/findings')}>All findings <ArrowRight size={15}/></button>}/><div className="finding-list">{data.findings.slice(0,3).map(finding => <FindingRow key={finding.id} finding={finding}/>)}</div></Card>
  </div>;
}

function ConnectionsPage({ data, notify }: { data: DemoSnapshot; notify: (message: string) => void }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<SourceSystem | null>(null);
  const [testing, setTesting] = useState<string>();
  const filtered = data.sources.filter(source => `${source.name} ${source.type}`.toLowerCase().includes(query.toLowerCase()));
  const test = (id: string) => { setTesting(id); window.setTimeout(() => { setTesting(undefined); notify('Fixture capability checks completed. No live source was contacted.'); }, 900); };
  return <div className="page-stack">
    <Notice title="Four distinct capability states">Reachability, authentication, metadata access and objective coverage are evaluated separately. Demo checks never contact a vendor system.</Notice>
    <Card><div className="toolbar"><label className="search-field"><span className="sr-only">Search connections</span><MagnifyingGlass size={17}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search configured connections"/></label><Button icon={<SlidersHorizontal size={17}/>}>Filters</Button></div>
      <div className="connection-list">{filtered.map(source => <article key={source.id} className="connection-row"><div className="source-icon"><Database size={20}/></div><div className="connection-row__main"><div><h3>{source.name}</h3><Badge>{source.type}</Badge></div><p>{source.scope}</p><small>Resource group: {source.resourceGroup}</small></div><div className="connection-row__status"><StatusBadge status={source.status}/><StatusBadge status={source.validation}/></div><div className="row-actions"><Button onClick={() => test(source.id)} disabled={testing === source.id} icon={testing === source.id ? <ArrowsClockwise className="spin" size={16}/> : <Activity size={16}/>}>{testing === source.id ? 'Testing…' : 'Test'}</Button><Button variant="ghost" onClick={() => setSelected(source)}>Inspect</Button></div></article>)}</div>
    </Card>
    <Card><PanelHeader title="Connector catalog" description="Support and validation claims are kept separate."/><div className="catalog-grid">{[['PostgreSQL','Synthetic fixture','Native metadata and bounded profiling'],['SAP BW / BW/4HANA','Synthetic fixture','Query and transformation artifact parsing'],['dbt artifacts','Synthetic fixture','Manifest, catalog and run results'],['OpenLineage','Synthetic fixture','Events with explicit namespace mapping'],['Power BI','Not live verified','Metadata scan adapter requires tenant entitlement'],['File & SQL artifacts','Synthetic fixture','Read-only local evidence import']].map(item => <div className="catalog-item" key={item[0]}><div><Database size={19}/><strong>{item[0]}</strong></div><p>{item[2]}</p><StatusBadge status={item[1]}/></div>)}</div></Card>
    {selected && <Drawer title={selected.name} onClose={() => setSelected(null)}><p className="drawer-lede">Capability evidence for this configured synthetic source.</p><dl className="fact-list">{selected.facts.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><Notice tone="warning" title={selected.validation}>{selected.validation === 'Not live verified' ? 'Adapter code exists, but no proprietary tenant was available for live conformance.' : 'These results come from isolated public synthetic fixtures.'}</Notice><Button variant="primary" onClick={() => notify('Scope preview opened for the selected source.')}>Preview permitted scope</Button></Drawer>}
  </div>;
}

function AssessmentsPage({ data, notify }: { data: DemoSnapshot; notify: (message: string) => void }) {
  const [runState, setRunState] = useState<'Running'|'Paused'|'Cancelled'>('Running');
  const [tab, setTab] = useState<'progress'|'activity'|'config'>('progress');
  return <div className="page-stack">
    <div className="run-banner"><div><Badge tone={runState === 'Running' ? 'accent' : 'warning'}>{runState}</Badge><h2>{data.run.current}</h2><p>{data.run.id} · Conservative operating profile · 5 scoped sources</p></div><div className="run-banner__actions">{runState === 'Paused' ? <Button variant="primary" icon={<Play size={16}/>} onClick={() => {setRunState('Running');notify('Assessment resumed. New source operations may be admitted.')}}>Resume</Button> : <Button icon={<Pause size={16}/>} onClick={() => {setRunState('Paused');notify('Assessment paused. In-flight source work may still be completing.')}}>Pause</Button>}<Button variant="danger" icon={<X size={16}/>} onClick={() => {setRunState('Cancelled');notify('Cancellation requested; source termination state will be tracked separately.')}}>Cancel</Button></div></div>
    <div className="tabbar" role="tablist">{([['progress','Investigation'],['activity','Source activity'],['config','Effective configuration']] as const).map(item => <button role="tab" aria-selected={tab===item[0]} key={item[0]} onClick={()=>setTab(item[0])}>{item[1]}</button>)}</div>
    {tab === 'progress' && <div className="two-column"><Card><PanelHeader title="Investigation areas" description="Concise actions and outcomes; no hidden chain-of-thought."/><div className="run-task-list roomy">{data.run.tasks.map(task => <div key={task.label}><span className={`task-dot task-dot--${task.status.toLowerCase()}`}/><div><strong>{task.label}</strong><small>{task.detail}</small></div><StatusBadge status={task.status}/></div>)}</div></Card><Card><PanelHeader title="Evidence discovered"/><div className="timeline">{[['08:31','Dependency','Outbound DTP schedule linked to distributor extract'],['08:26','Code span','Period-end adjustment transformation parsed'],['08:19','Coverage','Archived reporting workspace remains outside scope'],['08:14','Inventory','PostgreSQL catalog snapshot validated']].map(item => <div key={item[0]}><time>{item[0]}</time><span/><div><strong>{item[1]}</strong><p>{item[2]}</p></div></div>)}</div></Card></div>}
    {tab === 'activity' && <Card><PanelHeader title="Source workload activity" description="Client timeout and source-side termination remain distinct states."/><div className="table-wrap"><table><thead><tr><th>Operation</th><th>Resource group</th><th>Cost</th><th>State</th><th>Actual termination</th></tr></thead><tbody><tr><td>Discover transformations</td><td>erp-core</td><td>Metadata</td><td><StatusBadge status="Complete"/></td><td>Confirmed</td></tr><tr><td>Trace DTP dependency</td><td>erp-core</td><td>Metadata</td><td><StatusBadge status="Active"/></td><td>Still running</td></tr><tr><td>Profile customer keys</td><td>analytics-postgres</td><td>Bounded profile</td><td><StatusBadge status="Deferred"/></td><td>Not admitted</td></tr></tbody></table></div></Card>}
    {tab === 'config' && <Card><PanelHeader title="Effective run configuration" description="Recorded when the run started; secret values are never included."/><dl className="config-grid"><div><dt>Objective</dt><dd>Legacy retirement readiness</dd></div><div><dt>Operating profile</dt><dd>Conservative</dd></div><div><dt>Source concurrency</dt><dd>2 per resource group</dd></div><div><dt>Inference route</dt><dd>Local structured profile</dd></div><div><dt>Evidence egress</dt><dd>Classified fields redacted</dd></div><div><dt>Policy revision</dt><dd>policy-07</dd></div></dl></Card>}
  </div>;
}

function EstatePage({ data, notify }: { data: DemoSnapshot; notify: (message: string) => void }) {
  const [view, setView] = useState<'lineage'|'assets'>('lineage');
  const [selected, setSelected] = useState<Asset | null>(null);
  const [query, setQuery] = useState('');
  const filtered = data.assets.filter(asset => `${asset.name} ${asset.type} ${asset.domain}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-stack">
    <div className="view-toolbar"><Segmented label="Estate view" value={view} options={[{value:'lineage',label:'Lineage graph'},{value:'assets',label:'Asset table'}]} onChange={setView}/><div className="page-actions"><Button icon={<Archive size={16}/>} onClick={() => notify('Current bounded layout saved to this demo workspace.')}>Save view</Button><Button icon={<DownloadSimple size={16}/>} onClick={() => notify('Accessible synthetic lineage SVG prepared.')}>Export SVG</Button></div></div>
    {view === 'lineage' ? <Card className="lineage-card"><PanelHeader title="Net sales to downstream consumers" description="Bounded path slice · 8 nodes · column-level where evidence allows"/><LineageGraph/><div className="graph-footer"><div className="legend"><span><i className="legend-line solid"/>Observed</span><span><i className="legend-line dashed"/>Inferred</span><span><i className="legend-node external"/>External boundary</span></div><p>Select a node for evidence, fields and impacted reports.</p></div></Card> : <Card><AssetTable assets={filtered} query={query} setQuery={setQuery} onSelect={setSelected}/></Card>}
    <Card><PanelHeader title="Accessible lineage table" description="Keyboard-readable alternative for the selected graph slice."/><div className="table-wrap"><table><thead><tr><th>From asset</th><th>Relationship</th><th>To asset</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody><tr><td>invoice_line</td><td>aggregated into</td><td>ZSD_NET_SALES</td><td><StatusBadge status="Observed"/></td><td>SQL AST · 4 spans</td></tr><tr><td>monthly_adjustment</td><td>adjusts</td><td>ZSD_NET_ADJ</td><td><StatusBadge status="Observed"/></td><td>ABAP span · lines 18–31</td></tr><tr><td>ZSD_NET_ADJ</td><td>feeds</td><td>Management net sales</td><td><StatusBadge status="Observed"/></td><td>Query element mapping</td></tr><tr><td>Distributor extract</td><td>consumed by</td><td>External portal</td><td><StatusBadge status="Inferred"/></td><td>Schedule + filename convention</td></tr></tbody></table></div></Card>
    {selected && <AssetDrawer asset={selected} onClose={()=>setSelected(null)}/>}
  </div>;
}

function AssetTable({ assets, query, setQuery, onSelect }: { assets: Asset[]; query: string; setQuery:(v:string)=>void; onSelect:(a:Asset)=>void }) {
  return <><div className="toolbar"><label className="search-field"><span className="sr-only">Search assets</span><MagnifyingGlass size={17}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search assets and definitions"/></label><Button icon={<SlidersHorizontal size={17}/>}>Filter</Button></div><div className="table-wrap"><table><thead><tr><th>Asset</th><th>Type</th><th>System</th><th>Domain</th><th>Usage evidence</th><th>Knowledge state</th></tr></thead><tbody>{assets.map(asset=><tr key={asset.id} className="clickable-row" onClick={()=>onSelect(asset)}><td><button>{asset.name}</button><small>{asset.id}</small></td><td>{asset.type}</td><td>{asset.system}</td><td>{asset.domain}</td><td>{asset.usage}</td><td><StatusBadge status={asset.status}/></td></tr>)}</tbody></table></div></>;
}

function LineageGraph() {
  const nodes = [
    {x:24,y:92,w:150,title:'invoice_line',sub:'PostgreSQL · table',tone:'source'},
    {x:24,y:222,w:150,title:'monthly_adjustment',sub:'BW · ADSO',tone:'source'},
    {x:252,y:92,w:150,title:'ZSD_NET_SALES',sub:'BW · query',tone:'derived'},
    {x:252,y:222,w:150,title:'ZSD_NET_ADJ',sub:'BW · transformation',tone:'derived'},
    {x:490,y:52,w:170,title:'Management net sales',sub:'Power BI · report',tone:'report'},
    {x:490,y:162,w:170,title:'Operations net sales',sub:'Power BI · report',tone:'report'},
    {x:490,y:272,w:170,title:'Distributor extract',sub:'Scheduled file',tone:'report'},
    {x:742,y:272,w:150,title:'External portal',sub:'Boundary · uncertain',tone:'external'},
  ];
  return <div className="graph-scroll" tabIndex={0} aria-label="Interactive lineage graph, use the accessible table below for keyboard navigation"><svg className="lineage-graph" viewBox="0 0 920 390" role="img" aria-labelledby="graph-title graph-desc"><title id="graph-title">Net sales lineage</title><desc id="graph-desc">Invoice and adjustment sources flow through BW logic to two reports and one external extract.</desc><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z"/></marker></defs><g className="edges"><path d="M174 118 C208 118 212 118 252 118"/><path d="M174 248 C208 248 212 248 252 248"/><path d="M402 118 C446 118 448 78 490 78"/><path d="M402 118 C446 118 448 188 490 188"/><path d="M402 248 C446 248 448 78 490 78"/><path className="dashed" d="M402 248 C446 248 448 298 490 298"/><path className="dashed" d="M660 298 C700 298 706 298 742 298"/></g>{nodes.map(node=><g key={node.title} className={`graph-node graph-node--${node.tone}`} tabIndex={0} role="button" aria-label={`${node.title}, ${node.sub}`}><rect x={node.x} y={node.y} width={node.w} height="54" rx="8"/><circle cx={node.x+18} cy={node.y+18} r="4"/><text className="node-title" x={node.x+16} y={node.y+28}>{node.title}</text><text className="node-sub" x={node.x+16} y={node.y+44}>{node.sub}</text></g>)}</svg></div>;
}

function AssetDrawer({ asset, onClose }: { asset: Asset; onClose:()=>void }) { return <Drawer title={asset.name} onClose={onClose}><div className="drawer-badges"><StatusBadge status={asset.status}/><Badge>{asset.type}</Badge></div><p className="drawer-lede">{asset.description}</p><dl className="fact-list"><div><dt>Native identity</dt><dd>{asset.system}/{asset.id}</dd></div><div><dt>Domain</dt><dd>{asset.domain}</dd></div><div><dt>Usage</dt><dd>{asset.usage}</dd></div><div><dt>Snapshot</dt><dd>demo-snapshot-07</dd></div></dl><h3>Derived definition</h3><pre className="code-block"><code>{`SELECT\n  customer_key,\n  fiscal_period,\n  SUM(net_amount) AS net_sales\nFROM invoice_line\nGROUP BY 1, 2`}</code></pre><p className="code-caption">Synthetic fixture · SQL lines 11–16 · collected fact</p></Drawer> }

function ReportsPage({ data, notify }: { data: DemoSnapshot; notify:(m:string)=>void }) {
  const [selected, setSelected] = useState<Report>(data.reports[0]);
  return <div className="reports-layout"><Card className="reports-list"><PanelHeader title="Report dispositions" description="Based on dependency, semantics and observed-use evidence."/><div className="report-items">{data.reports.map(report=><button key={report.id} onClick={()=>setSelected(report)} className={selected.id===report.id?'is-active':''}><span><strong>{report.name}</strong><small>{report.platform} · {report.usage}</small></span><StatusBadge status={report.disposition}/></button>)}</div></Card><Card className="report-detail"><PanelHeader title={selected.name} description={`${selected.id} · ${selected.platform}`} action={<Button onClick={()=>notify('Disposition editor opened; saving would create a new version.')}>Edit disposition</Button>}/><div className="semantic-callout"><span>Semantic distinction</span><p>{selected.distinction}</p></div><h3>{selected.metric}</h3><pre className="formula-block"><code>{selected.formula}</code></pre><dl className="fact-list"><div><dt>Proposed disposition</dt><dd><StatusBadge status={selected.disposition}/></dd></div><div><dt>Usage evidence</dt><dd>{selected.usage}</dd></div><div><dt>Evidence state</dt><dd>Observed + interpreted</dd></div></dl><h3>Side-by-side comparison</h3><div className="diff-view"><div><span>Invoice-only</span><code>SUM(invoice.net_amount)</code></div><ArrowRight size={17}/><div className="diff-added"><span>Management definition</span><code>SUM(invoice.net_amount) + monthly_adjustment</code></div></div><Notice tone="warning" title="Not equivalent by name">A matching title and one coincident sample total are insufficient evidence of semantic equivalence.</Notice></Card></div>;
}

function ModernizationPage({ notify }: { notify:(m:string)=>void }) {
  const [tab,setTab]=useState('architecture'); const [scenario,setScenario]=useState('v3');
  const tabs=[['architecture','Architecture'],['models','Models'],['pipelines','Pipelines'],['mappings','Mappings'],['operations','Security & operations']];
  return <div className="page-stack"><div className="scenario-bar"><div><span>Target scenario</span><select value={scenario} onChange={e=>setScenario(e.target.value)} aria-label="Target scenario"><option value="v3">Open lakehouse · v3</option><option value="v2">Warehouse-first · v2</option></select></div><div className="scenario-bar__meta"><span>Updated 42 min ago</span><Button onClick={()=>notify('Scenario comparison opened with changed assumptions highlighted.')}>Compare scenarios</Button><Button variant="primary" onClick={()=>notify('New version created. Dependent validations marked stale.')}>Create version</Button></div></div><div className="tabbar tabbar--scroll" role="tablist">{tabs.map(([id,label])=><button key={id} role="tab" aria-selected={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
    {tab==='architecture'&&<ArchitectureView/>}{tab==='models'&&<ModelsView/>}{tab==='pipelines'&&<PipelinesView/>}{tab==='mappings'&&<MappingsView/>}{tab==='operations'&&<OperationsView/>}</div>;
}

function ArchitectureView(){return <div className="two-column wide-left"><Card><PanelHeader title="Target architecture" description="Target-neutral logical design; platform bindings remain adapters."/><div className="architecture-diagram"><div className="arch-band"><span>Bounded ingestion</span><div><i>PostgreSQL CDC</i><i>BW extract transition</i><i>Artifact import</i></div></div><ArrowDown size={19}/><div className="arch-band"><span>Shared data foundation</span><div><i>Commercial</i><i>Product</i><i>Customer</i><i>Plant</i></div></div><ArrowDown size={19}/><div className="arch-band accent"><span>Analytical models</span><div><i>Invoice facts</i><i>Adjustments</i><i>Inventory snapshots</i></div></div><ArrowDown size={19}/><div className="arch-band"><span>Semantic & delivery</span><div><i>Certified metrics</i><i>BI models</i><i>Distributor contract</i></div></div></div></Card><Card><PanelHeader title="Decision basis"/><div className="evidence-stack"><div><Badge tone="accent">Fact</Badge><p>Invoice and adjustment logic have different grain and update cadence.</p><a href="/findings">3 evidence references</a></div><div><Badge tone="warning">Assumption</Badge><p>Target supports transactional merge semantics and snapshot isolation.</p><a href="/findings">Review assumption A-07</a></div><div><Badge tone="info">Decision</Badge><p>Preserve adjustment provenance as a separate fact.</p><a href="/findings">Decision D-12 · v3</a></div></div></Card></div>}

function ModelsView(){const [mode,setMode]=useState<'graph'|'schema'>('graph');return <Card><PanelHeader title="Commercial domain model" description="Readable grains, keys, histories and uncertain identity links." action={<Segmented label="Model view" value={mode} options={[{value:'graph',label:'Entity graph'},{value:'schema',label:'Schema'}]} onChange={setMode}/>}/>{mode==='graph'?<div className="model-graph"><Entity name="fact_invoice_line" kind="Fact" fields={['invoice_line_key PK','customer_key FK','net_amount','fiscal_period']}/><div className="model-links"><span/><span/><span/></div><div className="dimension-stack"><Entity name="dim_customer" kind="Dimension · SCD2" fields={['customer_key PK','source_customer_id','valid_from / valid_to']}/><Entity name="fact_adjustment" kind="Fact · monthly" fields={['adjustment_key PK','fiscal_period','signed_amount']}/><Entity name="dim_product" kind="Dimension · SCD2" fields={['product_key PK','material_id','product_group']}/></div></div>:<div className="table-wrap"><table><thead><tr><th>Model</th><th>Grain</th><th>Primary key</th><th>History</th><th>Source mapping</th></tr></thead><tbody><tr><td>fact_invoice_line</td><td>Invoice line</td><td>invoice_line_key</td><td>Append + correction</td><td>96% observed</td></tr><tr><td>fact_adjustment</td><td>Fiscal period × customer</td><td>adjustment_key</td><td>Versioned close</td><td>Observed</td></tr><tr><td>dim_customer</td><td>Canonical customer</td><td>customer_key</td><td>Type 2</td><td><StatusBadge status="Partial"/></td></tr></tbody></table></div>}<Notice tone="warning" title="Uncertain identity match">12 synthetic customer records map to multiple canonical candidates. The proposed crosswalk includes an explicit review queue.</Notice></Card>}
function Entity({name,kind,fields}:{name:string;kind:string;fields:string[]}){return <div className="entity"><header><strong>{name}</strong><span>{kind}</span></header>{fields.map(f=><div key={f}>{f}</div>)}</div>}
function PipelinesView(){return <Card><PanelHeader title="Invoice and adjustment pipelines" description="Initial and incremental behavior are specified separately."/><div className="pipeline-grid"><div><Badge tone="info">Initial load</Badge><h3>Historical commercial facts</h3><p>Partitioned extraction by fiscal year with record-count, amount and key reconciliation at each checkpoint.</p><dl><div><dt>Source limit</dt><dd>2 concurrent metadata / 1 extract</dd></div><div><dt>Restart</dt><dd>Completed partition checkpoint</dd></div><div><dt>Validation</dt><dd>Schema generated · execution not run</dd></div></dl></div><div><Badge tone="accent">Incremental</Badge><h3>Invoice change capture</h3><p>Watermark plus overlap window; late corrections are merged while original source timestamps remain preserved.</p><dl><div><dt>Cadence</dt><dd>15 minutes proposed</dd></div><div><dt>Late data</dt><dd>72-hour overlap assumption</dd></div><div><dt>Validation</dt><dd>Checks specified · not target tested</dd></div></dl></div><div><Badge tone="warning">Period close</Badge><h3>Monthly adjustments</h3><p>Separate idempotent ingestion after close status is observed. Never folded into invoice CDC.</p><dl><div><dt>Cadence</dt><dd>On published close</dd></div><div><dt>Checkpoint</dt><dd>Fiscal period + version</dd></div><div><dt>Validation</dt><dd>Contract specified · not run</dd></div></dl></div></div></Card>}
function MappingsView(){return <Card><PanelHeader title="Current-to-target mapping"/><div className="table-wrap"><table><thead><tr><th>Current asset</th><th>Target asset</th><th>Mapping state</th><th>Evidence</th><th>Affected validations</th></tr></thead><tbody><tr><td>ZSD_NET_SALES</td><td>fact_invoice_line.net_amount</td><td><StatusBadge status="Evidence-linked"/></td><td>7 fixture spans</td><td>4 checks defined</td></tr><tr><td>ZSD_NET_ADJ</td><td>fact_adjustment.signed_amount</td><td><StatusBadge status="Evidence-linked"/></td><td>3 fixture spans</td><td>3 checks defined</td></tr><tr><td>0CUSTOMER</td><td>dim_customer.customer_key</td><td><StatusBadge status="Partial"/></td><td>Identity fixture</td><td>1 expected-failure check</td></tr><tr><td>ZDIST_MONTHLY</td><td>delivery_export_v1</td><td><StatusBadge status="Assumption"/></td><td>Schedule only</td><td>Not run</td></tr></tbody></table></div></Card>}
function OperationsView(){return <div className="two-column"><Card><PanelHeader title="Security boundaries"/><ul className="check-list"><li><CheckCircle/>Credential custody remains in connector runtime</li><li><CheckCircle/>Workspace-scoped evidence and model cache</li><li><CheckCircle/>No public-provider fallback</li><li><CheckCircle/>Generated code isolated from source credentials</li><li><Warning/>Target IAM mapping is an assumption</li></ul></Card><Card><PanelHeader title="Operational requirements"/><dl className="fact-list"><div><dt>Recovery objective</dt><dd>Customer-configured; not yet agreed</dd></div><div><dt>Freshness</dt><dd>15 minutes proposed for invoices</dd></div><div><dt>Observability</dt><dd>OpenTelemetry-compatible</dd></div><div><dt>Deployment</dt><dd>Single-node demo; not HA</dd></div></dl></Card></div>}

function MigrationPage({notify}:{notify:(m:string)=>void}){const packages=[['01','Shared foundations','Specified','Models, policies and reconciliation harness'],['02','Invoice & customer','Checks defined','Invoice fact, customer crosswalk, semantic metric'],['03','Inventory snapshot','Proposed','Non-additive stock model and report'],['04','Outbound delivery','Blocked','External consumer contract not confirmed'],['05','Coexistence & cutover','Proposed','Dual-run, reconciliation and rollback conditions']];return <div className="page-stack"><div className="migration-summary"><div><strong>5</strong><span>work packages</span></div><div><strong>2</strong><span>blocking conditions</span></div><div><strong>7 / 9</strong><span>fixture checks specified</span></div><div><strong>0</strong><span>production validations</span></div></div><Card><PanelHeader title="Proposed work sequence" description="Dependencies determine order. Durations are intentionally not fabricated."/><div className="work-packages">{packages.map((item,index)=><div key={item[0]}><span className="package-number">{item[0]}</span><div><h3>{item[1]}</h3><p>{item[3]}</p></div><StatusBadge status={item[2]}/>{index<packages.length-1&&<span className="package-link"/>}</div>)}</div></Card><div className="two-column"><Card><PanelHeader title="Verification matrix" action={<Button onClick={()=>notify('Fixture checks are specifications in this demo; execution is not wired here.')}>Review checks</Button>}/><div className="validation-list"><div><FileSearch weight="fill"/><span><strong>Invoice amount parity</strong><small>Planned across 12 synthetic periods · not run</small></span></div><div><FileSearch weight="fill"/><span><strong>Adjustment provenance</strong><small>Expected separate grain · not run</small></span></div><div><Warning weight="fill"/><span><strong>Customer identity boundary</strong><small>Expected ambiguous fixture records · not run</small></span></div><div><XCircleIcon/><span><strong>Outbound contract</strong><small>Cannot run · consumer unknown</small></span></div></div></Card><Card><PanelHeader title="Retirement conditions"/><ul className="condition-list"><li>In-scope asset dispositions are specified, not accepted</li><li>Critical semantic checks are defined, not executed</li><li>Outbound consumers have confirmed replacement paths</li><li>Dual-run acceptance thresholds are agreed</li><li>Rollback path is tested on the target</li></ul><Notice tone="warning" title="Not ready to retire">Reweft does not decommission systems. Required verification and acceptance remain unresolved.</Notice></Card></div></div>}
function XCircleIcon(){return <X size={17} weight="bold"/>}

function FindingsPage({data,notify}:{data:DemoSnapshot;notify:(m:string)=>void}){const [severity,setSeverity]=useState('All');const [selected,setSelected]=useState<Finding|null>(null);const rows=data.findings.filter(f=>severity==='All'||f.severity===severity);return <div className="page-stack"><div className="filter-strip"><div className="filter-pills" aria-label="Filter by severity">{['All','High','Medium','Low'].map(value=><button key={value} aria-pressed={severity===value} className={severity===value?'is-active':''} onClick={()=>setSeverity(value)}>{value}{value==='All'&&<span>{data.findings.length}</span>}</button>)}</div><Button icon={<SlidersHorizontal size={16}/>}>More filters</Button></div><Card><div className="finding-list detailed">{rows.map(f=><button key={f.id} className="finding-button" onClick={()=>setSelected(f)}><FindingRow finding={f}/><ArrowRight size={17}/></button>)}</div></Card><Card><PanelHeader title="Changes since previous run" description="Snapshot comparison distinguishes absence from confirmed deletion."/><div className="change-list"><div><Badge tone="success">Added</Badge><span><strong>12 assets discovered</strong><small>New scope in the distribution artifact import</small></span></div><div><Badge tone="warning">Changed</Badge><span><strong>Monthly adjustment definition</strong><small>Hash differs; source version was not available</small></span></div><div><Badge>Not observed</Badge><span><strong>Legacy workbook delivery</strong><small>Absent from incomplete scan — not a confirmed deletion</small></span></div></div></Card>{selected&&<Drawer title={`${selected.id} · ${selected.title}`} onClose={()=>setSelected(null)}><div className="drawer-badges"><StatusBadge status={selected.severity}/><StatusBadge status={selected.state}/><Badge>{selected.area}</Badge></div><p className="drawer-lede">{selected.summary}</p><h3>Evidence locator</h3><div className="locator"><Code size={17}/><code>{selected.locator}</code><button onClick={()=>notify('Evidence locator copied.')}>Copy</button></div><pre className="code-block"><code>{`// Synthetic evidence excerpt\nresult = invoice_net_amount\n       + monthly_adjustment_amount\n// Grain: customer × fiscal period`}</code></pre><h3>Collaboration</h3><dl className="fact-list"><div><dt>Assigned to</dt><dd>{selected.assignee??'Unassigned'}</dd></div><div><dt>Comments</dt><dd>2 workspace comments</dd></div><div><dt>Decision</dt><dd>Pending</dd></div></dl><Button variant="primary" onClick={()=>notify('Comment composer opened for workspace collaborators.')}>Add comment</Button></Drawer>}</div>}

function FindingRow({finding}:{finding:Finding}){return <div className="finding-row"><span className={`severity-mark severity-mark--${finding.severity.toLowerCase()}`}/><div className="finding-row__body"><div><strong>{finding.title}</strong><span>{finding.id}</span></div><p>{finding.summary}</p><div><StatusBadge status={finding.severity}/><StatusBadge status={finding.state}/><Badge>{finding.area}</Badge><span className="evidence-count"><FileSearch size={14}/>{finding.evidence}</span></div></div></div>}

function SettingsPage({notify}:{notify:(m:string)=>void}) {
  const [tab,setTab]=useState('models');
  const [advanced,setAdvanced]=useState(false);
  const tabs=[['models','Models & inference'],['team','Team & access'],['policy','Policies & retention'],['diagnostics','Diagnostics']];
  return <div className="page-stack">
    <div className="tabbar tabbar--scroll" role="tablist">{tabs.map(([id,label])=><button role="tab" key={id} aria-selected={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
    {tab==='models'&&<div className="two-column wide-left">
      <Card><PanelHeader title="Default inference profile" description="Simple mode configures one explicit endpoint. There is no silent fallback." action={<label className="toggle-label"><input type="checkbox" checked={advanced} onChange={e=>setAdvanced(e.target.checked)}/><span/>Advanced</label>}/>
        <div className="form-grid"><label><span>Endpoint type</span><select defaultValue="openai-compatible"><option value="openai-compatible">OpenAI-compatible</option><option value="native">Native provider</option><option value="local">Local endpoint</option></select></label><label><span>Base URL</span><input defaultValue="http://model-gateway.internal/v1"/></label><label><span>Model identifier</span><input defaultValue="workspace-default"/><small>No model name is hard-coded by Reweft.</small></label><label><span>Credential</span><input value="Secret reference configured in demo" readOnly/><small>Secret values are not returned to the UI.</small></label>{advanced&&<><label><span>Input budget per run</span><input defaultValue="250000"/></label><label><span>Fallback policy</span><select defaultValue="none"><option value="none">No fallback</option><option value="private">Private routes only</option></select></label><label><span>Evidence classification</span><select defaultValue="internal"><option>Internal and below</option><option>Public only</option></select></label><label><span>Cache policy</span><select><option>Workspace and policy revision</option></select></label></>}</div>
        <div className="form-actions"><Button disabled icon={<Activity size={16}/>}>Provider not connected</Button><Button variant="primary" onClick={()=>notify('Demo profile preview updated locally; no provider configuration changed.')}>Preview changes</Button></div>
        <Notice title="Preflight disclosure">This demo cannot contact an inference provider. A connected provider test may consume tokens; estate evidence must not be included.</Notice>
      </Card>
      <Card><PanelHeader title="Route health"/><div className="health-block"><div><span className="pulse-dot pulse-dot--idle"/><div><strong>Configured demo endpoint</strong><small>Provider has not been tested</small></div></div><dl className="fact-list"><div><dt>Structured output</dt><dd>Required · not tested</dd></div><div><dt>Streaming</dt><dd>Not required</dd></div><div><dt>Tool format</dt><dd>Required · not tested</dd></div><div><dt>Public fallback</dt><dd>Disabled by configuration</dd></div></dl></div><PanelHeader title="Run consumption"/><div className="usage-meter"><span style={{width:'0%'}}/></div><p className="muted">Unknown — no provider invocation has been recorded.</p></Card>
    </div>}
    {tab==='team'&&<TeamSettings/>}{tab==='policy'&&<PolicySettings/>}{tab==='diagnostics'&&<Diagnostics/>}
  </div>
}
function TeamSettings(){return <Card><PanelHeader title="Workspace members" action={<Button icon={<Plus size={16}/>}>Invite member</Button>}/><div className="table-wrap"><table><thead><tr><th>Member</th><th>Role</th><th>Scope</th><th>Last active</th></tr></thead><tbody><tr><td><span className="member"><UserCircle size={22}/>Demo owner</span></td><td>Owner</td><td>Workspace</td><td>Now</td></tr><tr><td><span className="member"><UserCircle size={22}/>Demo architect</span></td><td>Architect</td><td>Project</td><td>42 min ago</td></tr><tr><td><span className="member"><Robot size={22}/>Validation service</span></td><td>Service account</td><td>Tests: write</td><td>3 hours ago</td></tr></tbody></table></div></Card>}
function PolicySettings(){return <div className="two-column"><Card><PanelHeader title="Evidence egress"/><ul className="settings-list"><li><span><strong>Classified-field redaction</strong><small>Required by deployment policy</small></span><input type="checkbox" checked readOnly/></li><li><span><strong>External inference</strong><small>Permitted for internal-and-below evidence</small></span><input type="checkbox" defaultChecked/></li><li><span><strong>Silent provider fallback</strong><small>Prohibited for all workspaces</small></span><input type="checkbox" disabled/></li></ul></Card><Card><PanelHeader title="Retention"/><dl className="fact-list"><div><dt>Evidence snapshots</dt><dd>90 days</dd></div><div><dt>Audit metadata</dt><dd>365 days</dd></div><div><dt>Model prompts</dt><dd>30 days · redacted</dd></div><div><dt>Generated exports</dt><dd>14 days</dd></div></dl><Button variant="danger">Delete workspace data…</Button></Card></div>}
function Diagnostics(){return <div className="two-column"><Card><PanelHeader title="Local installation"/><div className="diagnostic-list">{[['Frontend','Loaded'],['API service','Not checked'],['Orchestration worker','Not implemented'],['Collector worker','Not implemented'],['Data store','SQLite development'],['Temporal persistence','Not running in demo'],['Artifact sandbox','Not configured']].map(item=><div key={item[0]}><span>{item[0]}</span><StatusBadge status={item[1]}/></div>)}</div></Card><Card><PanelHeader title="Version information"/><dl className="fact-list"><div><dt>Reweft</dt><dd>0.1.0-development</dd></div><div><dt>Deployment</dt><dd>Synthetic frontend demonstration</dd></div><div><dt>Evidence storage</dt><dd>Bundled fixture</dd></div><div><dt>High availability</dt><dd>Not configured</dd></div></dl><Notice tone="warning" title="Development build">This local installation is not a published release or production-validated deployment.</Notice></Card></div>}

function Drawer({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}) {
  const ref=useRef<HTMLElement>(null);
  const returnFocus=useRef<HTMLElement|null>(null);
  useEffect(()=>{
    returnFocus.current=document.activeElement instanceof HTMLElement ? document.activeElement : null;
    ref.current?.focus();
    const handleKey=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.stopPropagation();onClose()}};
    window.addEventListener('keydown',handleKey);
    return ()=>{window.removeEventListener('keydown',handleKey);returnFocus.current?.focus()};
  },[onClose]);
  return <div className="drawer-scrim" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabIndex={-1} ref={ref}><header><h2 id="drawer-title">{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close panel"><X size={19}/></button></header><div className="drawer__content">{children}</div></aside></div>
}

function CommandPalette({onClose,navigate,data}:{onClose:()=>void;navigate:(p:string)=>void;data:DemoSnapshot|null}){const [query,setQuery]=useState('');const inputRef=useRef<HTMLInputElement>(null);useEffect(()=>inputRef.current?.focus(),[]);const results=useMemo(()=>{const nav=allNav.map(i=>({label:i.label,meta:'Navigate',path:i.path,icon:i.icon}));const assets=(data?.assets??[]).map(a=>({label:a.name,meta:`Asset · ${a.type}`,path:'/estate',icon:TableIcon}));return [...nav,...assets].filter(i=>`${i.label} ${i.meta}`.toLowerCase().includes(query.toLowerCase())).slice(0,8)},[query,data]);return <div className="modal-scrim" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><div className="command-palette" role="dialog" aria-modal="true" aria-label="Search and command palette"><div className="command-input"><MagnifyingGlass size={19}/><input ref={inputRef} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search assets, evidence, commands…"/><kbd>Esc</kbd></div><div className="command-results">{results.length?results.map((result,index)=>{const Icon=result.icon;return <button key={`${result.label}-${index}`} onClick={()=>navigate(result.path)}><Icon size={18}/><span><strong>{result.label}</strong><small>{result.meta}</small></span><ArrowRight size={15}/></button>}):<EmptyState title="No results">Try a system, asset, finding or destination name.</EmptyState>}</div><footer><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><kbd>↵</kbd> to open</span></footer></div></div>}

function ContextPanel({onClose,path}:{onClose:()=>void;path:string}){return <div className="drawer-scrim" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><aside className="context-panel" role="dialog" aria-modal="true" aria-labelledby="context-title"><header><div><span><Sparkle size={16}/> Context assistant</span><h2 id="context-title">Ask about this view</h2></div><button className="icon-button" onClick={onClose} aria-label="Close assistant"><X size={19}/></button></header><div className="context-scope"><span>Current context</span><strong>{pageMeta[path]?.title}</strong><small>Synthetic Manufacturing · RUN-042</small></div><div className="chat-empty"><div><BracketsCurly size={23}/></div><h3>Evidence-aware, source-isolated</h3><p>Answers may use the selected synthetic workspace and visible evidence. This panel cannot contact source systems or access credentials.</p><button>Explain the highest-risk finding</button><button>Compare the two net sales metrics</button><button>Show evidence behind this proposal</button></div><form onSubmit={e=>e.preventDefault()}><label className="sr-only" htmlFor="chat-message">Ask a contextual question</label><textarea id="chat-message" placeholder="Ask about the current evidence…"/><button className="icon-button" aria-label="Send question"><ArrowRight size={18}/></button></form></aside></div>}
