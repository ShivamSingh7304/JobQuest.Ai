import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  ArrowRight, Bell, BriefcaseBusiness, CalendarDays, Check, ChevronRight,
  CircleHelp, FileText, LayoutDashboard, LogOut, Menu, MessageCircle,
  Plus, Search, Settings2, ShieldCheck, Sparkles, Target, X, Zap,
} from 'lucide-react'
import './styles.css'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

async function apiRequest(path, options = {}) {
  const token = localStorage.getItem('jobquest_token')
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail || 'Something went wrong')
  if (path.includes('/tailor') || /\/applications\/\d+\/prepare$/.test(path)) {
    window.dispatchEvent(new Event('jobquest:open-review'))
  }
  return data
}

const navItems = [
  ['Overview', LayoutDashboard], ['Resumes', FileText], ['Job discovery', BriefcaseBusiness],
  ['Interview prep', Target], ['Applications', CalendarDays],
  ['Career coach', MessageCircle], ['Calendar', CalendarDays],
]

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('jobquest_token'))
  const [user, setUser] = useState(null)
  const [active, setActive] = useState('Overview')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [toast, setToast] = useState('')

  const notify = (message) => {
    setToast(message)
    window.clearTimeout(window.__jobQuestToast)
    window.__jobQuestToast = window.setTimeout(() => setToast(''), 2500)
  }

  useEffect(() => {
    if (!token) return
    apiRequest('/auth/me').then(setUser).catch(() => {
      localStorage.removeItem('jobquest_token')
      setToken(null)
    })
  }, [token])

  useEffect(() => {
    const openReview = () => {
      setActive('Human review')
      setMobileOpen(false)
    }
    window.addEventListener('jobquest:open-review', openReview)
    return () => window.removeEventListener('jobquest:open-review', openReview)
  }, [])

  useEffect(() => {
    const previewResume = (event) => {
      const link = event.target.closest?.('a[href*="/api/resumes/preview/"]')
      if (!link) return
      event.preventDefault()
      const popup = window.open('about:blank', '_blank')
      fetch(link.href, {
        headers: { Authorization: `Bearer ${localStorage.getItem('jobquest_token') || ''}` },
      }).then((response) => {
        if (!response.ok) throw new Error('Resume preview could not be loaded')
        return response.blob()
      }).then((blob) => {
        if (popup) popup.location.href = URL.createObjectURL(blob)
      }).catch(() => {
        if (popup) popup.close()
        window.alert('Resume preview could not be loaded. Please sign in again.')
      })
    }
    document.addEventListener('click', previewResume)
    return () => document.removeEventListener('click', previewResume)
  }, [])

  if (!token) return <AuthScreen onAuth={(nextToken, nextUser) => {
    localStorage.setItem('jobquest_token', nextToken)
    setToken(nextToken)
    setUser(nextUser)
  }} />

  const logout = () => {
    localStorage.removeItem('jobquest_token')
    setToken(null)
    setUser(null)
  }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Sparkles size={17} /></div><span>JobQuest<em>.ai</em></span></div>
      <div className="profile-switch"><div className="avatar">{initials(user?.full_name || 'Alex Sharma')}</div><div><strong>{user?.full_name || 'Your workspace'}</strong><small>Personal workspace</small></div><ChevronRight size={15} /></div>
      <p className="section-label">WORKSPACE</p>
      <nav>{navItems.map(([label, Icon]) => <button key={label} className={active === label ? 'active' : ''} onClick={() => { setActive(label); setMobileOpen(false) }}><Icon size={17} /><span>{label}</span>{label === 'Human review' && <b className="alert">2</b>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="pro-card"><div className="pro-icon"><Zap size={16} /></div><strong>Keep your momentum</strong><p>One focused action today compounds.</p><button onClick={() => setActive('Career coach')}>Ask your coach <ArrowRight size={14} /></button></div><button className="settings"><Settings2 size={16} /> Settings</button><button className="settings" onClick={logout}><LogOut size={16} /> Sign out</button></div>
    </aside>
    <main className="main">
      <header className="topbar"><button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X /> : <Menu />}</button><div className="breadcrumbs"><span>Workspace</span><i>/</i><strong>{active}</strong></div><div className="top-actions"><button className="icon-button" onClick={() => notify('You are all caught up')}><Bell size={18} /><i /></button><button className="icon-button"><CircleHelp size={18} /></button><div className="avatar">{initials(user?.full_name || 'Alex Sharma')}</div></div></header>
      <div className="page">{renderView(active, { notify, setActive, user })}</div>
    </main>
    {toast && <div className="toast"><Check size={16} />{toast}</div>}
  </div>
}

function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault(); setLoading(true); setError('')
    try {
      if (mode === 'signup') {
        const user = await apiRequest('/auth/register', { method: 'POST', body: JSON.stringify(form) })
        const login = await loginRequest(form.email, form.password)
        onAuth(login.access_token, user)
      } else {
        const login = await loginRequest(form.email, form.password)
        const user = await apiRequest('/auth/me', { headers: { Authorization: `Bearer ${login.access_token}` } })
        onAuth(login.access_token, user)
      }
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  return <div className="auth-shell"><div className="auth-visual"><div className="auth-brand"><div className="brand-mark"><Sparkles size={18} /></div> JobQuest<em>.ai</em></div><div className="auth-copy"><span className="eyebrow">YOUR CAREER, IN FOCUS</span><h1>Make your next move with clarity.</h1><p>Find the right roles, sharpen your story, and move every opportunity forward — all in one calm workspace.</p><div className="auth-proof"><div><ShieldCheck size={17} /> Human approval built in</div><div><Sparkles size={17} /> AI grounded in your experience</div></div></div><div className="auth-orbit one" /><div className="auth-orbit two" /></div><div className="auth-panel"><div className="auth-panel-inner"><div className="auth-mobile-brand"><div className="brand-mark"><Sparkles size={16} /></div> JobQuest<em>.ai</em></div><span className="eyebrow">{mode === 'login' ? 'WELCOME BACK' : 'GET STARTED'}</span><h2>{mode === 'login' ? 'Sign in to your workspace' : 'Create your workspace'}</h2><p className="auth-subtitle">{mode === 'login' ? 'Pick up where your career momentum left off.' : 'Your career command center is a few details away.'}</p>{error && <div className="form-error">{error}</div>}<form onSubmit={submit}>{mode === 'signup' && <label>Full name<input required value={form.full_name} onChange={field(setForm, 'full_name')} placeholder="Alex Sharma" /></label>}<label>Email<input required type="email" value={form.email} onChange={field(setForm, 'email')} placeholder="you@example.com" /></label><label>Password<input required minLength={8} type="password" value={form.password} onChange={field(setForm, 'password')} placeholder="At least 8 characters" /></label><button className="button full" disabled={loading}>{loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <ArrowRight size={16} /></button></form><p className="auth-toggle">{mode === 'login' ? 'New to JobQuest?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p></div></div></div>
}

async function loginRequest(email, password) {
  const body = new URLSearchParams({ username: email, password })
  const response = await fetch(`${API_BASE}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail || 'Invalid email or password')
  return data
}

function renderView(active, props) {
  if (active === 'Overview') return <DynamicOverview {...props} />
  if (active === 'Resumes') return <Resumes {...props} />
  if (active === 'Job discovery') return <Jobs {...props} />
  if (active === 'Applications') return <Applications {...props} />
  if (active === 'Human review') return <Review {...props} />
  if (active === 'Career coach') return <Coach {...props} />
  if (active === 'Calendar') return <Calendar {...props} />
  return <Interview {...props} />
}

function Overview({ setActive, notify }) { return <><Header eyebrow="THURSDAY · 30 OCTOBER 2026" title={<>Good morning, Alex <span className="spark">✦</span></>} subtitle="Here’s what deserves your attention today." action={<button className="button" onClick={() => setActive('Career coach')}>Ask your career coach <ArrowRight size={16} /></button>} /><div className="metric-grid"><Metric label="Active applications" value="12" note="+3 this week" tone="lavender" icon={<BriefcaseBusiness size={16} />} /><Metric label="Resume match score" value="78%" note="+8% since last review" tone="green" visual={<span className="metric-ring">78</span>} /><Metric label="Interview readiness" value="64%" note="Focus: system design" visual={<div className="progress"><i style={{ width: '64%' }} /></div>} /><Metric label="Saved opportunities" value="28" note="6 new matches" visual={<div className="bars"><i /><i /><i /><i /><i /></div>} /></div><div className="overview-grid"><section className="card"><CardTitle title="Today’s focus" subtitle="Small steps, meaningful progress." link="View plan" onClick={() => notify('Your plan is up to date')} /><FocusRow done title="Update your professional summary" meta="Resume · 15 min" /><FocusRow title="Review 2 new job matches" meta="Job discovery · 10 min" onClick={() => setActive('Job discovery')} /><FocusRow title="Practice behavioral questions" meta="Interview prep · 20 min" onClick={() => setActive('Interview prep')} /></section><section className="coach-card"><span className="coach-label"><Sparkles size={14} /> CAREER COACH</span><h2>“You’re closer than you think.”</h2><p>Your resume is a strong match for 6 new roles. Let’s make sure your applications tell the same story.</p><button className="button light" onClick={() => setActive('Career coach')}>Start a conversation <ArrowRight size={16} /></button></section></div><div className="overview-grid lower"><section className="card"><CardTitle title="Application pulse" subtitle="Latest movement across your applications." link="See all" onClick={() => setActive('Applications')} /><div className="table"><div className="table-head"><span>ROLE</span><span>COMPANY</span><span>STAGE</span><span>UPDATED</span></div><ApplicationRow role="Product Engineer" company="Linear" stage="Interview" tone="purple" updated="Today" /><ApplicationRow role="Frontend Intern" company="Razorpay" stage="In review" tone="orange" updated="Yesterday" /><ApplicationRow role="Software Engineer" company="Swiggy" stage="Applied" tone="blue" updated="Oct 24" /></div></section><section className="card top-match"><CardTitle title="Top match" subtitle="Based on your profile and goals." extra={<b className="score">92%</b>} /><div className="job-line"><div className="company-logo">S</div><div><strong>Software Engineer, Growth</strong><small>Stripe · Bengaluru / Hybrid</small></div></div><div className="chips"><span>Python</span><span>APIs</span><span>Product sense</span></div><div className="match-footer"><small><b>Strong match</b> · 8 of 9 skills</small><button className="link" onClick={() => setActive('Job discovery')}>View role <ArrowRight size={14} /></button></div></section></div></> }

function DynamicOverview({ setActive, notify, user }) {
  const [data, setData] = useState(null)
  useEffect(() => { apiRequest('/overview').then(setData).catch((err) => notify(err.message)) }, [])
  const applications = data?.recent_applications || []
  const name = user?.full_name?.split(' ')[0] || 'there'
  return <><Header eyebrow="YOUR WORKSPACE" title={<>Good morning, {name} <span className="spark">✦</span></>} subtitle="Here’s what deserves your attention today." action={<button className="button" onClick={() => setActive('Career coach')}>Ask your career coach <ArrowRight size={16} /></button>} />
    <div className="metric-grid"><Metric label="Active applications" value={data ? data.active_applications : '—'} note="Across your saved and submitted roles" tone="lavender" icon={<BriefcaseBusiness size={16} />} /><Metric label="Resumes" value={data ? data.resume_count : '—'} note="Saved in your workspace" tone="green" visual={<span className="metric-ring">{data?.resume_count || 0}</span>} /><Metric label="Interview pipeline" value={data ? data.interviewing_applications : '—'} note="Applications at interview stage" visual={<div className="progress"><i style={{ width: `${data ? Math.min(data.interviewing_applications * 20, 100) : 0}%` }} /></div>} /><Metric label="Saved opportunities" value={data ? data.saved_opportunities : '—'} note="Applications waiting to move forward" visual={<div className="bars"><i /><i /><i /><i /><i /></div>} /></div>
    <div className="overview-grid"><section className="card"><CardTitle title="Today’s focus" subtitle="Small steps, meaningful progress." link="View plan" onClick={() => notify('Your plan is up to date')} /><FocusRow done={Boolean(data?.resume_count)} title="Keep your resume ready" meta="Resume workspace" onClick={() => setActive('Resumes')} /><FocusRow title="Review your applications" meta="Application tracker" onClick={() => setActive('Applications')} /><FocusRow title="Practice interview questions" meta="Interview prep" onClick={() => setActive('Interview prep')} /></section><section className="coach-card"><span className="coach-label"><Sparkles size={14} /> CAREER COACH</span><h2>Keep your momentum.</h2><p>{data ? `You have ${data.active_applications} active application${data.active_applications === 1 ? '' : 's'} to keep moving.` : 'Loading your application activity…'}</p><button className="button light" onClick={() => setActive('Career coach')}>Start a conversation <ArrowRight size={16} /></button></section></div>
    <div className="overview-grid lower"><section className="card"><CardTitle title="Application pulse" subtitle="Latest movement across your applications." link="See all" onClick={() => setActive('Applications')} /><div className="table"><div className="table-head"><span>ROLE</span><span>COMPANY</span><span>STAGE</span><span>UPDATED</span></div>{applications.length ? applications.map((item) => <ApplicationRow key={item.id} role={item.role} company={item.company} stage={item.stage} tone={item.status === 'interviewing' ? 'purple' : item.status === 'pending_approval' ? 'orange' : 'blue'} updated={new Date(item.updated_at).toLocaleDateString()} />) : <p className="empty-copy">No applications yet. Save a role from Job discovery to get started.</p>}</div></section><section className="card top-match"><CardTitle title="Your next move" subtitle="Based on your current application activity." /><div className="job-line"><div className="company-logo">{data?.active_applications || 0}</div><div><strong>{data?.active_applications ? 'Keep your applications moving' : 'Find your first opportunity'}</strong><small>{data?.active_applications ? 'Review pending applications and prepare for interviews.' : 'Search roles matched to your resume.'}</small></div></div><div className="match-footer"><button className="link" onClick={() => setActive(data?.active_applications ? 'Applications' : 'Job discovery')}>{data?.active_applications ? 'View applications' : 'Find roles'} <ArrowRight size={14} /></button></div></section></div></>
}

function Header({ eyebrow, title, subtitle, action }) { return <div className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{subtitle}</p></div>{action}</div> }
function CardTitle({ title, subtitle, link, onClick, extra }) { return <div className="card-title"><div><h2>{title}</h2><p>{subtitle}</p></div>{extra || (link && <button className="link" onClick={onClick}>{link} <ArrowRight size={14} /></button>)}</div> }
function Metric({ label, value, note, tone = '', visual, icon }) { return <div className={`metric ${tone}`}><div className="metric-top"><span>{label}</span>{icon}</div><strong>{value}</strong><small>{note}</small>{visual}</div> }
function FocusRow({ done, title, meta, onClick }) { return <button className="focus-row" onClick={onClick}><span className={`check ${done ? 'done' : ''}`}>{done && <Check size={13} />}</span><span><strong>{title}</strong><small>{meta}</small></span>{done ? <em>Done</em> : <ArrowRight size={16} />}</button> }
function ApplicationRow({ role, company, stage, tone, updated }) { return <div className="table-row"><strong>{role}</strong><span>{company}</span><em className={`pill ${tone}`}>{stage}</em><span>{updated}</span></div> }

function Resumes({ notify }) {
  const [items, setItems] = useState([])
  const [file, setFile] = useState(null)
  const [selectedResumeId, setSelectedResumeId] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [workflow, setWorkflow] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { apiRequest('/resumes').then((data) => { setItems(data); if (data[0]) setSelectedResumeId(String(data[0].id)) }).catch((err) => notify(err.message)) }, [])
  const upload = async () => { if (!file) return notify('Choose a PDF or DOCX resume first'); setBusy(true); try { const data = new FormData(); data.append('file', file); const item = await apiRequest('/resumes/upload', { method: 'POST', body: data }); setItems((current) => [item, ...current]); setSelectedResumeId(String(item.id)); notify('Resume uploaded and analyzed') } catch (err) { notify(err.message) } finally { setBusy(false) } }
  const remove = async (item) => { if (!window.confirm(`Remove ${item.original_filename}?`)) return; try { await apiRequest(`/resumes/${item.id}`, { method: 'DELETE' }); setItems((current) => current.filter((entry) => entry.id !== item.id)); if (String(item.id) === selectedResumeId) setSelectedResumeId(''); notify('Resume removed') } catch (err) { notify(err.message) } }
  const tailor = async () => { if (!selectedResumeId) return notify('Choose a resume first'); if (!jobDescription.trim()) return notify('Paste a target job description first'); setBusy(true); try { const result = await apiRequest(`/resumes/${selectedResumeId}/tailor`, { method: 'POST', body: JSON.stringify({ job_description: jobDescription }) }); setWorkflow(result); notify(`Draft ready for review · output #${result.workflow_output_id}`) } catch (err) { notify(err.message) } finally { setBusy(false) } }
  return <><Header eyebrow="RESUME WORKSPACE" title="Your resumes" subtitle="Build a sharper story for every opportunity." action={<label className="button file-button"><Plus size={16} /> Choose resume<input type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0])} /></label>} /><div className="resume-grid"><section className="card"><CardTitle title="Saved resumes" subtitle={`${items.length} resume${items.length === 1 ? '' : 's'} in your workspace`} />{items.length ? items.map((item) => <div className={`resume-item ${String(item.id) === selectedResumeId ? 'selected' : ''}`} key={item.id}><button className="resume-select" onClick={() => setSelectedResumeId(String(item.id))}><div className="file-icon">{item.original_filename.toLowerCase().endsWith('.docx') ? 'DOCX' : 'PDF'}</div><div><strong>{item.original_filename}</strong><small>Version {item.version} · analyzed</small><div className="chips"><span>{String(item.id) === selectedResumeId ? 'Selected' : 'Ready for matching'}</span></div></div></button><div className="resume-actions"><a className="link" href={`/api/resumes/preview/${item.id}`} target="_blank" rel="noreferrer">Preview <ArrowRight size={13} /></a><button className="link danger-link" onClick={() => remove(item)}>Remove <X size={13} /></button></div></div>) : <Empty title="No resumes yet" text="Upload a PDF or DOCX to start your workspace." />}<button className="button full" onClick={upload} disabled={busy || !file}>{busy ? 'Uploading…' : 'Upload selected resume'} <ArrowRight size={16} /></button></section><section className="card tailor"><span className="coach-label purple"><Sparkles size={14} /> AI RESUME TAILORING</span><h2>Make your resume fit the role.</h2><p>Choose a saved resume and paste the target job description. Your original stays unchanged.</p><label>Target job description<textarea value={jobDescription} onChange={(e) => setJobDescription(e.target.value)} placeholder="Paste the full job description here…" rows="8" /></label><button className="button" onClick={tailor} disabled={busy || !selectedResumeId}>{busy ? 'Tailoring…' : 'Analyze and tailor'} <ArrowRight size={16} /></button>{workflow && <div className="workflow-result"><span className="eyebrow">DRAFT #{workflow.workflow_output_id} · PENDING REVIEW</span><h3>{workflow.tailoring.professional_summary}</h3><p>{workflow.tailoring.changes_made?.join(' ')}</p><div className="chips">{(workflow.tailoring.relevant_skills || []).map((skill) => <span key={skill}>{skill}</span>)}</div><small>Human review is open for this draft.</small></div>}</section></div></>
}

function Jobs({ notify }) { const [query, setQuery] = useState(''); const [country, setCountry] = useState('India'); const [resumeId, setResumeId] = useState(''); const [resumes, setResumes] = useState([]); const [jobs, setJobs] = useState([]); const [savedJobs, setSavedJobs] = useState({}); const [busy, setBusy] = useState(false); const [actionId, setActionId] = useState(''); useEffect(() => { apiRequest('/resumes').then((data) => { setResumes(data); if (data[0]) setResumeId(data[0].id) }).catch(() => {}) }, []); const search = async () => { if (!resumeId || !query.trim()) return notify('Select a resume and enter a search query'); setBusy(true); try { const result = await apiRequest('/jobs/match', { method: 'POST', body: JSON.stringify({ resume_id: Number(resumeId), query, country, limit: 10, max_pages: 2 }) }); setJobs(result.jobs || []); notify(`${result.matched_job_count || 0} matched jobs found`) } catch (err) { notify(err.message) } finally { setBusy(false) } }; const saveJob = async (job, key) => { if (!job.application_url) return notify('This role has no application URL to save'); setActionId(key); try { const saved = await apiRequest('/jobs/save', { method: 'POST', body: JSON.stringify({ external_id: job.external_id || key, title: job.title || 'Untitled role', company_name: job.company_name || 'Unknown company', application_url: job.application_url, description: job.description || null, excerpt: job.excerpt || null, location_restrictions: job.location_restrictions || [], employment_type: job.employment_type || null, seniority: job.seniority || null, published_at: job.published_at || null }) }); setSavedJobs((current) => ({ ...current, [key]: saved })); notify('Job saved to your workspace'); return saved } catch (err) { notify(err.message) } finally { setActionId('') } }; const applyToJob = async (job, key) => { if (!resumeId) return notify('Select a resume before applying'); setActionId(`apply-${key}`); try { const saved = savedJobs[key] || await saveJob(job, key); if (!saved?.job_id) return; const application = await apiRequest('/applications', { method: 'POST', body: JSON.stringify({ job_id: saved.job_id, resume_id: Number(resumeId), status: 'saved' }) }); notify(`Application #${application.id} created`) } catch (err) { notify(err.message) } finally { setActionId('') } }; return <><Header eyebrow="JOB DISCOVERY" title="Find your next opportunity" subtitle="Search live roles and rank them against your resume." action={<button className="button" onClick={search}>{busy ? 'Searching…' : 'Search jobs'} <Search size={16} /></button>} /><section className="search-panel card"><label>Resume<select value={resumeId} onChange={(e) => setResumeId(e.target.value)}><option value="">Choose a resume</option>{resumes.map((r) => <option key={r.id} value={r.id}>{r.original_filename}</option>)}</select></label><label>Search query<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Python developer" /></label><label>Country<input value={country} onChange={(e) => setCountry(e.target.value)} /></label></section><div className="job-list">{jobs.length ? jobs.map((job, index) => { const key = job.external_id || String(index); const saved = savedJobs[key]; return <article className="card job-card" key={key}><div className="job-content"><div className="job-line"><div className="company-logo">{(job.company_name || 'J')[0]}</div><div><h2>{job.title || 'Untitled role'}</h2><small>{job.company_name || 'Unknown company'} · {job.employment_type || 'Role'}</small></div></div><p className="job-description">{job.description || job.excerpt || 'No description was provided for this listing.'}</p><div className="chips">{(job.matched_skills || []).map((skill) => <span key={skill}>{skill}</span>)}</div><div className="job-actions"><button className="save-button" disabled={actionId === key || Boolean(saved)} onClick={() => saveJob(job, key)}>{saved ? <><Check size={14} /> Saved</> : actionId === key ? 'Saving…' : 'Save job'}</button><button className="button apply-button" disabled={actionId === `apply-${key}`} onClick={() => applyToJob(job, key)}>{actionId === `apply-${key}` ? 'Applying…' : 'Save & apply'} <ArrowRight size={14} /></button>{job.application_url && <a className="external-link" href={job.application_url} target="_blank" rel="noreferrer">Open listing <ArrowRight size={13} /></a>}</div></div><div className="job-score">{Number(job.match_score || 0).toFixed(0)}%<small>match</small></div></article> }) : <Empty title="Ready when you are" text="Search for roles and JobQuest will rank them against your resume." />}</div></> }

function Applications({ notify }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState('')
  useEffect(() => { apiRequest('/applications').then(setItems).catch((err) => notify(err.message)).finally(() => setLoading(false)) }, [])
  const update = async (item, nextStatus) => { if (['approved', 'submitted'].includes(nextStatus) && !item.workflow_output_record_id) return notify('Prepare this application for human review before approving or submitting it'); try { const updated = await apiRequest(`/applications/${item.id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus, workflow_output_record_id: item.workflow_output_record_id || undefined }) }); setItems((current) => current.map((entry) => entry.id === item.id ? updated : entry)); notify('Application updated') } catch (err) { notify(err.message) } }
  const prepareForReview = async (item) => { setBusyId(String(item.id)); try { const result = await apiRequest(`/applications/${item.id}/prepare`, { method: 'POST' }); setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, status: result.status === 'approved_for_submission' ? 'approved' : 'pending_approval', workflow_output_record_id: result.workflow_output_id } : entry)); notify(`Application prepared for review · output #${result.workflow_output_id}`) } catch (err) { notify(err.message) } finally { setBusyId('') } }
  const columns = [
    { key: 'saved', name: 'Saved jobs', color: 'blue', matches: (item) => item.status === 'saved' },
    { key: 'in_process', name: 'Applied · in process', color: 'orange', matches: (item) => ['pending_approval', 'approved', 'submitted'].includes(item.status) },
    { key: 'interviewing', name: 'Interview', color: 'purple', matches: (item) => item.status === 'interviewing' },
  ]
  return <><Header eyebrow="APPLICATION TRACKER" title="Keep every opportunity moving" subtitle={`${items.length} applications · saved → applied → interview.`} action={<button className="button" onClick={() => notify('Create an application from a saved job in Job discovery')}><Plus size={16} /> Add application</button>} />{loading ? <div className="card loading-card">Loading your applications…</div> : <div className="kanban">{columns.map((column) => { const grouped = items.filter(column.matches); return <section className="kanban-col" key={column.key}><div className="kanban-title"><span className={`dot ${column.color}`} /><strong>{column.name}</strong><b>{grouped.length}</b></div>{grouped.length ? grouped.map((item) => <div className="application-card" key={item.id}><strong>Application #{item.id}</strong><span>Job #{item.job_id}</span><small>{item.notes || 'No notes yet'}</small>{!item.workflow_output_record_id && ['saved', 'pending_approval'].includes(item.status) && <button className="link" disabled={busyId === String(item.id)} onClick={() => prepareForReview(item)}>{busyId === String(item.id) ? 'Preparing…' : 'Prepare for human review'} <ShieldCheck size={13} /></button>}<select value={item.status} onChange={(e) => update(item, e.target.value)}><option value="saved">Saved job</option><option value="pending_approval">Applied · pending review</option><option value="approved">Applied · approved</option><option value="submitted">Applied · submitted</option><option value="interviewing">Interview</option></select>{item.workflow_output_record_id && <small>Review output #{item.workflow_output_record_id}</small>}</div>) : <Empty title="Nothing here yet" text="Applications will appear in this stage." />}</section>})}</div>}</>
}

function Review({ notify }) {
  const [output, setOutput] = useState(null)
  const [decision, setDecision] = useState('approve')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  useEffect(() => { apiRequest('/workflow-outputs?status=pending_review&limit=20').then((items) => setOutput(items[0] || null)).catch((err) => notify(err.message)).finally(() => setLoading(false)) }, [])
  const submit = async (nextDecision) => { if (!output) return notify('No pending workflow output found'); setDecision(nextDecision); setSubmitting(true); try { await apiRequest('/feedback', { method: 'POST', body: JSON.stringify({ decision: nextDecision, feedback: nextDecision === 'request_changes' ? 'Please review this draft.' : null, workflow_output_record_id: output.id }) }); setOutput({ ...output, status: nextDecision === 'approve' ? 'approved' : 'changes_requested' }); notify(nextDecision === 'approve' ? 'Content approved' : 'Changes requested') } catch (err) { notify(err.message) } finally { setSubmitting(false) } }
  const saveTailored = async () => { if (!output?.payload?.resume_id) return notify('The original resume could not be identified'); setSubmitting(true); try { const saved = await apiRequest(`/resumes/${output.payload.resume_id}/save-tailored`, { method: 'POST', body: JSON.stringify({ workflow_output_record_id: output.id }) }); setDownloadUrl(saved.download_url); notify('New tailored resume saved') } catch (err) { notify(err.message) } finally { setSubmitting(false) } }
  const payload = output?.payload
  const tailoring = payload?.tailoring
  const isApplication = output?.workflow_name === 'application_preparation'
  const title = isApplication ? `Application #${payload?.application_id || 'draft'}` : (tailoring?.target_role || payload?.target_role || 'Tailored resume draft')
  const summary = isApplication ? 'Review the application details and confirm they are ready to move forward.' : (tailoring?.professional_summary || 'Review the AI-generated suggestions against your original resume.')
  return <><Header eyebrow="HUMAN REVIEW" title="Your approval queue" subtitle="AI drafts are waiting for your final say." action={<span className="secure"><ShieldCheck size={14} /> Nothing sends without you</span>} />{loading ? <div className="card loading-card">Loading your review queue…</div> : !output ? <section className="card review-card"><Empty title="Nothing to review" text="Tailor a resume or prepare an application first." /></section> : <section className="card review-card"><div className="review-badge"><Sparkles size={14} /> {output.workflow_name.replaceAll('_', ' ').toUpperCase()} · {output.status.toUpperCase()}</div><h2>{title}</h2><p>{summary}</p>{isApplication && <div className="workflow-result"><span className="eyebrow">APPLICATION DETAILS</span><p>Job #{payload?.job_id || '—'} · Resume #{payload?.resume_id || '—'}</p><small>Approve only after checking the job and resume details.</small></div>}{tailoring?.changes_made?.length > 0 && <div className="workflow-result"><span className="eyebrow">CHANGES MADE</span><ul>{tailoring.changes_made.map((change) => <li key={change}>{change}</li>)}</ul></div>}<div className="review-actions"><button className="reject" disabled={submitting || output.status !== 'pending_review'} onClick={() => submit('request_changes')}>Request changes</button><button className="button" disabled={submitting || output.status !== 'pending_review'} onClick={() => submit('approve')}>{submitting ? 'Saving…' : 'Approve content'} <Check size={16} /></button></div>{!isApplication && output.status === 'approved' && <div className="review-actions"><button className="button" disabled={submitting} onClick={saveTailored}>{submitting ? 'Saving PDF…' : 'Save tailored resume as PDF'} <FileText size={16} /></button>{downloadUrl && <a className="button light" href={downloadUrl} target="_blank" rel="noreferrer">Download PDF <ArrowRight size={16} /></a>}</div>}<p className="review-note">Current decision: <b>{decision === 'approve' ? 'Approve' : 'Request changes'}</b> · Workflow output #{output.id}</p></section>}</>
}

function Coach({ notify }) { const [message, setMessage] = useState(''); const [messages, setMessages] = useState([{ role: 'assistant', content: 'Hey! I’m your career coach. Ask me about your resume, job search, or interview preparation.' }]); const send = async (e) => { e.preventDefault(); if (!message.trim()) return; const current = message; setMessage(''); setMessages([...messages, { role: 'user', content: current }]); try { const result = await apiRequest('/chat', { method: 'POST', body: JSON.stringify({ message: current }) }); setMessages((old) => [...old, { role: 'assistant', content: result.response }]) } catch (err) { notify(err.message) } }; return <><Header eyebrow="CAREER COACH" title="A thinking partner for your next move" subtitle="Ask questions, plan your next step, or get unstuck." /><section className="card chat"><div className="chat-messages">{messages.map((item, i) => <div className={`chat-message ${item.role}`} key={i}>{item.role === 'assistant' && <div className="coach-avatar"><Sparkles size={15} /></div>}<p>{item.content}</p></div>)}</div><form className="chat-input" onSubmit={send}><input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask your career coach anything..." /><button><ArrowRight size={16} /></button></form></section></> }

function Calendar({ notify }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const load = () => { setLoading(true); apiRequest('/calendar/events?days=14').then(setData).catch((err) => notify(err.message)).finally(() => setLoading(false)) }
  useEffect(load, [])
  const connect = async () => { setConnecting(true); try { const result = await apiRequest('/calendar/connect', { method: 'POST' }); if (result.authorization_url) window.location.href = result.authorization_url } catch (err) { notify(err.message) } finally { setConnecting(false) } }
  const events = data?.events || []
  return <><Header eyebrow="GOOGLE CALENDAR" title="Your interview rhythm" subtitle={data?.connected ? `Synced with ${data.calendar_name || 'your primary calendar'}` : 'Bring your interviews, preparation blocks, and follow-ups into one view.'} action={<div className="calendar-header-actions"><button className="button" onClick={data?.connected ? load : connect} disabled={connecting}>{connecting ? 'Opening Google…' : data?.connected ? 'Refresh schedule' : 'Connect Google Calendar'} <CalendarDays size={16} /></button>{data?.connected && <button className="link" onClick={connect} disabled={connecting}>Reconnect for event creation</button>}</div>} />
    {!data?.connected && !loading && <section className="card calendar-hero calendar-connect"><div className="calendar-icon"><CalendarDays size={22} /></div><span className="eyebrow">GOOGLE CALENDAR MCP</span><h2>Keep your preparation and interviews in sync.</h2><p>Connect Google Calendar to securely read your upcoming schedule through Google’s Calendar MCP server.</p><button className="button" onClick={connect} disabled={connecting}>{connecting ? 'Opening Google…' : 'Connect calendar'} <ArrowRight size={16} /></button></section>}
    {loading ? <div className="card loading-card">Loading your calendar…</div> : data?.connected && <div className="calendar-dashboard"><section className="card calendar-summary"><div className="calendar-summary-top"><div><span className="eyebrow">NEXT 14 DAYS</span><h2>{events.length} scheduled moment{events.length === 1 ? '' : 's'}</h2><p>Use the time between events to prepare with your career coach.</p></div><div className="calendar-icon"><CalendarDays size={22} /></div></div><div className="calendar-stats"><span><b>{events.filter((event) => event.all_day).length}</b> all-day</span><span><b>{events.filter((event) => !event.all_day).length}</b> timed events</span><span><b>{data.time_zone}</b> timezone</span></div></section><section className="card upcoming"><CardTitle title="Upcoming" subtitle="Your next career moments" extra={<button className="link" onClick={load}>Refresh</button>} />{events.length ? <div className="event-list">{events.map((event) => <a className="calendar-event" key={event.id} href={event.link || undefined} target={event.link ? '_blank' : undefined} rel="noreferrer"><div className="event-date"><strong>{event.date_label.split(',')[0]}</strong><span>{event.date_label.split(',').slice(1).join(',')}</span></div><div className="event-dot" /><div className="event-details"><strong>{event.title}</strong><small>{event.time_label}{event.location ? ` · ${event.location}` : ''}</small>{event.conference_url && <span className="event-link">Join meeting <ArrowRight size={12} /></span>}</div><ChevronRight size={16} /></a>)}</div> : <Empty title="Your schedule is clear" text="No events are scheduled in the next 14 days." />}</section></div>}
  </>
}

function Interview({ notify }) {
  const [resumes, setResumes] = useState([])
  const [resumeId, setResumeId] = useState('')
  const [jobDescription, setJobDescription] = useState('Software Engineer role requiring clear problem solving, backend fundamentals, APIs, and collaboration.')
  const [mode, setMode] = useState(null)
  const [session, setSession] = useState(null)
  const [answer, setAnswer] = useState('')
  const [evaluation, setEvaluation] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiRequest('/resumes').then((data) => {
      setResumes(data)
      if (data[0]) setResumeId(String(data[0].id))
    }).catch((err) => notify(err.message))
  }, [])

  const start = async (nextMode) => {
    if (!resumeId) return notify('Upload a resume before starting interview practice')
    if (!jobDescription.trim()) return notify('Add a job description first')
    setBusy(true)
    try {
      const result = await apiRequest('/interviews/questions', {
        method: 'POST',
        body: JSON.stringify({
          resume_id: Number(resumeId),
          target_role: 'Software Engineer',
          job_description: jobDescription,
          question_count: 5,
          categories: nextMode === 'practice' ? ['behavioral'] : undefined,
          difficulty: 'medium',
        }),
      })
      setMode(nextMode)
      setSession(result)
      setAnswer('')
      setEvaluation(null)
      notify(nextMode === 'mock' ? 'Mock interview started' : 'Practice question generated')
    } catch (err) { notify(err.message) } finally { setBusy(false) }
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!session || !answer.trim()) return notify('Write an answer before submitting')
    setBusy(true)
    try {
      const result = await apiRequest(`/interviews/${session.session_id}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer }),
      })
      setEvaluation(result.evaluation)
      setAnswer('')
      setSession((current) => ({
        ...current,
        question: result.next_question,
        status: result.interview_completed ? 'completed' : 'in_progress',
      }))
      notify(result.interview_completed ? 'Interview complete' : 'Answer evaluated')
    } catch (err) { notify(err.message) } finally { setBusy(false) }
  }

  const question = session?.question
  return <>
    <Header eyebrow="INTERVIEW PREP" title="Practice with purpose" subtitle="Generate tailored questions and get evidence-based AI feedback." action={<button className="button" disabled={busy} onClick={() => start('mock')}>{busy ? 'Generating…' : 'Start mock interview'} <ArrowRight size={16} /></button>} />
    <section className="card interview-setup"><label>Resume<select value={resumeId} onChange={(e) => setResumeId(e.target.value)}><option value="">Choose a resume</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.original_filename}</option>)}</select></label><label>Target job description<textarea value={jobDescription} onChange={(e) => setJobDescription(e.target.value)} rows="3" /></label></section>
    <div className="overview-grid"><section className="card readiness"><div className="readiness-ring">64</div><span className="eyebrow">OVERALL READINESS</span><h2>Good foundation</h2><p>Keep practicing structured answers and system design fundamentals.</p></section><section className="card"><span className="eyebrow">RECOMMENDED PRACTICE</span><h2>Generate a behavioral question from your resume.</h2><p>AI-generated · evidence-based rubric · genuine feedback</p><div className="tip"><Sparkles size={16} /> Your answer will be evaluated against a role-specific rubric.</div><button className="button" disabled={busy} onClick={() => start('practice')}>{busy ? 'Generating…' : 'Practice question'} <ArrowRight size={16} /></button></section></div>
    {session && <section className="card interview-session"><div className="review-badge"><Target size={14} /> {question ? (mode === 'mock' ? `MOCK INTERVIEW · QUESTION ${question.question_number} OF ${question.total_questions}` : 'PRACTICE QUESTION') : 'INTERVIEW COMPLETE'}</div>{question && <><h2>{question.question}</h2><p>{question.purpose}</p><form onSubmit={submit}><textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Type your answer here…" rows="8" disabled={busy} /><div className="review-actions"><button type="button" className="reject" onClick={() => { setSession(null); setEvaluation(null) }}>Close</button><button className="button" disabled={busy}>{busy ? 'Evaluating…' : 'Submit answer'} <ArrowRight size={16} /></button></div></form></>}{evaluation && <div className="workflow-result"><span className="eyebrow">AI FEEDBACK · {Number(evaluation.percentage || 0).toFixed(0)}%</span><h3>{evaluation.feedback}</h3>{evaluation.strengths?.length > 0 && <p><b>Strengths:</b> {evaluation.strengths.join(' ')}</p>}{evaluation.improvements?.length > 0 && <p><b>Improve:</b> {evaluation.improvements.join(' ')}</p>}{evaluation.missing_concepts?.length > 0 && <p><b>Missing concepts:</b> {evaluation.missing_concepts.join(', ')}</p>}</div>}</section>}
  </>
}
function Empty({ title, text }) { return <div className="empty"><div className="empty-icon"><Sparkles size={16} /></div><strong>{title}</strong><p>{text}</p></div> }
function field(setForm, name) { return (event) => setForm((current) => ({ ...current, [name]: event.target.value })) }
function initials(name) { return name.split(' ').map((word) => word[0]).join('').slice(0, 2).toUpperCase() }

createRoot(document.getElementById('root')).render(<App />)
