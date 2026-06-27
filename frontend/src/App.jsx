import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import AssessmentFundPanel from './AssessmentFundPanel.jsx';
import DemoBankPanel from './DemoBankPanel.jsx';

const API_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'control_work_generator_token';
const USER_KEY = 'control_work_generator_user';
const THEME_KEY = 'control_work_generator_theme';
const ADVANCED_UI_KEY = 'control_work_generator_advanced_ui';

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '');
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem(USER_KEY);
    return stored ? JSON.parse(stored) : null;
  });
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'light');
  const [showAdvancedUi, setShowAdvancedUi] = useState(() => localStorage.getItem(ADVANCED_UI_KEY) === 'enabled');
  const [activePage, setActivePage] = useState('workspace');
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ full_name: '', email: '', password: '' });
  const [file, setFile] = useState(null);
  const [program, setProgram] = useState(null);
  const [programsHistory, setProgramsHistory] = useState([]);
  const [generationsHistory, setGenerationsHistory] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [isUploading, setUploading] = useState(false);
  const [isReanalyzing, setReanalyzing] = useState(false);
  const [isHistoryLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const api = useMemo(() => axios.create({
    baseURL: API_URL,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }), [token]);

  const canEditWorkspace = user?.role === 'teacher' || user?.role === 'admin';
  const isDarkTheme = theme === 'dark';

  useEffect(() => {
    document.body.dataset.theme = theme;
    document.body.classList.toggle('darkTheme', theme === 'dark');
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(ADVANCED_UI_KEY, showAdvancedUi ? 'enabled' : 'disabled');
  }, [showAdvancedUi]);

  useEffect(() => {
    if (!token) return;
    api.get('/api/auth/me')
      .then(async (response) => {
        setUser(response.data);
        localStorage.setItem(USER_KEY, JSON.stringify(response.data));
        await loadHistory();
        if (response.data.role === 'admin') await loadAdminUsers();
        else setAdminUsers([]);
      })
      .catch(() => logout(false));
  }, [token]);

  function toggleTheme() {
    setTheme((current) => current === 'dark' ? 'light' : 'dark');
  }

  async function submitAuth(event) {
    event.preventDefault();
    setError('');
    setSuccess('');
    try {
      const url = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const payload = authMode === 'login' ? { email: authForm.email, password: authForm.password } : authForm;
      const response = await axios.post(`${API_URL}${url}`, payload);
      setToken(response.data.access_token);
      setUser(response.data.user);
      localStorage.setItem(TOKEN_KEY, response.data.access_token);
      localStorage.setItem(USER_KEY, JSON.stringify(response.data.user));
      setSuccess(authMode === 'login' ? 'Вход выполнен.' : 'Пользователь зарегистрирован.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка авторизации.');
    }
  }

  function logout(showMessage = true) {
    setToken('');
    setUser(null);
    setProgram(null);
    setProgramsHistory([]);
    setGenerationsHistory([]);
    setAdminUsers([]);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (showMessage) setSuccess('Вы вышли из системы.');
  }

  async function loadHistory() {
    if (!token) return;
    setHistoryLoading(true);
    try {
      const [programsResponse, generationsResponse] = await Promise.all([
        api.get('/api/programs/'),
        api.get('/api/generation/'),
      ]);
      setProgramsHistory(programsResponse.data);
      setGenerationsHistory(generationsResponse.data);
    } catch (err) {
      console.warn('Не удалось загрузить историю:', err);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadAdminUsers() {
    try {
      const response = await api.get('/api/admin/users');
      setAdminUsers(response.data);
    } catch (err) {
      console.warn('Не удалось загрузить пользователей:', err);
    }
  }

  async function uploadProgram(event) {
    event.preventDefault();
    if (!canEditWorkspace) return setError('Загрузка РПД доступна преподавателю или администратору.');
    if (!file) return setError('Выберите файл РПД в формате DOCX, PDF или TXT.');
    setError('');
    setSuccess('');
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post('/api/programs/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setProgram(response.data);
      setActivePage('workspace');
      await loadHistory();
      setSuccess('РПД успешно загружена и проанализирована.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось загрузить и проанализировать РПД.');
    } finally {
      setUploading(false);
    }
  }

  async function reanalyzeProgram() {
    if (!program?.program_id || !canEditWorkspace) return;
    setError('');
    setSuccess('');
    setReanalyzing(true);
    try {
      const response = await api.post(`/api/programs/${program.program_id}/reanalyze`);
      setProgram(response.data);
      await loadHistory();
      setSuccess('РПД повторно проанализирована.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось повторно проанализировать РПД.');
    } finally {
      setReanalyzing(false);
    }
  }

  async function openProgram(programId) {
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/programs/${programId}`);
      setProgram(response.data);
      setActivePage('workspace');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть РПД из истории.');
    }
  }

  async function openProgramForDemo(programId) {
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/programs/${programId}`);
      setProgram(response.data);
      setActivePage('administration');
      setSuccess('РПД выбрана для набора заданий и рабочего режима.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть РПД.');
    }
  }

  async function updateAdminUserRole(userId, role) {
    try {
      await api.patch(`/api/admin/users/${userId}/role`, { role });
      await loadAdminUsers();
      setSuccess(roleChangeMessage(role));
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось изменить роль.');
    }
  }

  async function toggleAdminUser(userId, isActive) {
    try {
      await api.patch(`/api/admin/users/${userId}/active`, { is_active: !isActive });
      await loadAdminUsers();
      setSuccess(isActive ? 'Пользователь заблокирован.' : 'Пользователь разблокирован.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось изменить состояние пользователя.');
    }
  }

  if (!user) {
    return <AuthScreen authMode={authMode} setAuthMode={setAuthMode} authForm={authForm} setAuthForm={setAuthForm} submitAuth={submitAuth} error={error} success={success} />;
  }

  return (
    <main className="page appShell">
      <section className="hero appHero card">
        <div>
          <p className="eyebrow">Фонд Оценочных Средств</p>
          <h1>Формирование ФОС по РПД</h1>
        </div>
        <div className="userBox">
          <ThemeToggle isDark={isDarkTheme} onToggle={toggleTheme} />
          <div className="userNameRow"><strong>{user.full_name}</strong><StarButton active={showAdvancedUi} onClick={() => setShowAdvancedUi((value) => !value)} /></div>
          <span>{user.email}</span>
          <span>Роль: {roleLabel(user.role)}</span>
          <button className="secondary smallButton" onClick={() => logout()}>Выйти</button>
        </div>
      </section>

      <nav className="appNav card" aria-label="Основные разделы">
        <button className={activePage === 'workspace' ? 'navTab activeNavTab' : 'navTab'} type="button" onClick={() => setActivePage('workspace')}>
          <span>{user.role === 'methodist' ? 'Проверка ФОС' : 'Рабочая область'}</span>
          <small>{user.role === 'methodist' ? 'РПД, ФОС, банк заданий' : 'РПД, ФОС, задания, экспорт'}</small>
        </button>
        <button className={activePage === 'administration' ? 'navTab activeNavTab' : 'navTab'} type="button" onClick={() => setActivePage('administration')}>
          <span>Администрирование</span>
          <small>Набор заданий, рабочий режим, история</small>
        </button>
      </nav>

      {error && <div className="alert">{error}</div>}
      {success && <div className="success">{success}</div>}

      {activePage === 'workspace' ? (
        <WorkspacePage user={user} file={file} setFile={setFile} program={program} isUploading={isUploading} uploadProgram={uploadProgram} isReanalyzing={isReanalyzing} reanalyzeProgram={reanalyzeProgram} api={api} showAdvancedUi={showAdvancedUi} setError={setError} setSuccess={setSuccess} />
      ) : (
        <AdministrationPage user={user} api={api} program={program} programsHistory={programsHistory} generationsHistory={generationsHistory} loadHistory={loadHistory} isHistoryLoading={isHistoryLoading} openProgram={openProgram} openProgramForDemo={openProgramForDemo} adminUsers={adminUsers} updateAdminUserRole={updateAdminUserRole} toggleAdminUser={toggleAdminUser} showAdvancedUi={showAdvancedUi} toggleAdvancedUi={() => setShowAdvancedUi((value) => !value)} setError={setError} setSuccess={setSuccess} />
      )}
    </main>
  );
}

function ThemeToggle({ isDark, onToggle }) { return <button className={`themeToggle ${isDark ? 'themeToggleDark' : ''}`} type="button" onClick={onToggle} aria-label={isDark ? 'Включить светлую тему' : 'Включить тёмную тему'}><span className="themeToggleTrack"><span className="themeIcon themeSun">☀</span><span className="themeIcon themeMoon">☾</span><span className="themeToggleThumb" /></span><strong>{isDark ? 'Тёмная' : 'Светлая'}</strong></button>; }
function StarButton({ active, onClick }) { return <button className={`starToggle ${active ? 'starToggleActive' : ''}`} type="button" onClick={onClick}>★</button>; }

function WorkspacePage({ user, file, setFile, program, isUploading, uploadProgram, isReanalyzing, reanalyzeProgram, api, showAdvancedUi, setError, setSuccess }) {
  const canEdit = user.role === 'teacher' || user.role === 'admin';
  return <div className="workspacePage"><section className="pageIntro card"><div><p className="eyebrow">Рабочая область</p><h2>{canEdit ? 'РПД → структура ФОС → банк заданий' : 'Проверка РПД, ФОС и банка заданий'}</h2><p className="muted">Основной сценарий работы с РПД и ФОС. Для демонстрации на защите используйте раздел “Администрирование”.</p></div><div className="stepPills"><span>1. РПД</span><span>2. Анализ</span><span>3. ФОС</span><span>4. Экспорт</span></div></section><section className="workspaceGrid">{canEdit ? <form className="card uploadCard" onSubmit={uploadProgram}><p className="eyebrow">Загрузка</p><h2>Рабочая программа дисциплины</h2><p className="muted">DOCX, PDF или TXT. После загрузки система выделит темы, компетенции и результаты обучения.</p><input className="fileInput" type="file" accept=".docx,.pdf,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} /><button className="primary" disabled={isUploading}>{isUploading ? 'Анализируем...' : 'Загрузить и проанализировать'}</button>{file && <p className="muted selectedFile">Выбран файл: <strong>{file.name}</strong></p>}</form> : <section className="card uploadCard"><p className="eyebrow">Проверка</p><h2>Материалы преподавателей</h2><p className="muted">Методист открывает РПД из истории и проверяет материалы без редактирования.</p></section>}<section className="card currentDocCard"><p className="eyebrow">Текущий документ</p><h2>{program?.filename || 'РПД пока не выбрана'}</h2>{program ? <div className="docStats"><Metric value={program.topics?.length || 0} label="тем" /><Metric value={program.competencies?.length || 0} label="компетенций" /><Metric value={`${program.analysis_report?.diagnostics?.quality_score || 0}%`} label="качество" /></div> : <p className="muted">Загрузите РПД или откройте документ из администрирования.</p>}</section></section>{program && <ProgramAnalysisSection program={program} canEdit={canEdit} isReanalyzing={isReanalyzing} reanalyzeProgram={reanalyzeProgram} />}{program && showAdvancedUi && <AssessmentFundPanel api={api} program={program} user={user} setError={setError} setSuccess={setSuccess} />}</div>;
}

function AdministrationPage({ user, api, program, programsHistory, generationsHistory, loadHistory, isHistoryLoading, openProgram, openProgramForDemo, adminUsers, updateAdminUserRole, toggleAdminUser, showAdvancedUi, toggleAdvancedUi, setError, setSuccess }) {
  return <div className="adminPage"><section className="pageIntro card adminIntro"><div><p className="eyebrow">Администрирование защиты</p><h2>Набор заданий и рабочий режим</h2><p className="muted">Для защиты ВКР заранее набиваем банк заданий под выбранную РПД, а затем показываем рабочий режим, где задания открываются практически сразу.</p></div></section>{showAdvancedUi && <section className="adminDashboard"><DemoBankPanel api={api} program={program} setError={setError} setSuccess={setSuccess} /><section className="card systemCard"><p className="eyebrow">Текущая РПД</p><h2>{program?.filename || 'РПД не выбрана'}</h2><p className="muted">Выберите РПД из истории ниже, затем откройте “Набор заданий” или “Рабочий режим”.</p></section></section>}<section className="card historyCard"><div className="sectionHeader"><div><h2>История работы</h2><p className="muted">Ранее загруженные РПД и сгенерированные материалы.</p></div><button className="secondary" onClick={loadHistory}>{isHistoryLoading ? 'Обновляем...' : 'Обновить'}</button></div><div className="historyGrid"><HistoryList title="РПД" items={programsHistory} getKey={(item) => item.program_id} renderItem={(item) => <><strong>{item.filename}</strong><span>{item.topics.length} тем · качество {item.analysis_report?.diagnostics?.quality_score || 0}%</span></>} onOpen={(item) => openProgramForDemo(item.program_id)} /><HistoryList title="Генерации" items={generationsHistory} getKey={(item) => item.session_id} renderItem={(item) => <><strong>{item.session_id.slice(0, 8)}...</strong><span>{statusLabel(item.status)} · {item.quality_report.total_questions} заданий</span></>} onOpen={(item) => openProgram(item.program_id)} /></div></section>{user.role === 'admin' && <AdminPanel users={adminUsers} currentUser={user} showAdvancedUi={showAdvancedUi} toggleAdvancedUi={toggleAdvancedUi} updateRole={updateAdminUserRole} toggleUser={toggleAdminUser} />}</div>;
}

function AuthScreen({ authMode, setAuthMode, authForm, setAuthForm, submitAuth, error, success }) { return <main className="page authPage"><section className="authCard card"><p className="eyebrow">Фонд Оценочных Средств</p><h1>Генератор контрольных работ</h1>{error && <div className="alert">{error}</div>}{success && <div className="success">{success}</div>}<div className="authTabs"><button className={authMode === 'login' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('login')}>Вход</button><button className={authMode === 'register' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('register')}>Регистрация</button></div><form onSubmit={submitAuth}>{authMode === 'register' && <label>ФИО<input value={authForm.full_name} onChange={(event) => setAuthForm({ ...authForm, full_name: event.target.value })} required /></label>}<label>Email<input type="email" value={authForm.email} onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })} required /></label><label>Пароль<input type="password" value={authForm.password} onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })} required /></label><button className="primary">{authMode === 'login' ? 'Войти' : 'Создать пользователя'}</button></form></section></main>; }
function ProgramAnalysisSection({ program, canEdit, isReanalyzing, reanalyzeProgram }) { const report = program.analysis_report || {}; const diagnostics = report.diagnostics || {}; return <section className="card"><div className="sectionHeader"><div><h2>Результаты анализа РПД</h2><p className="muted">Структурированный отчет показывает, какие элементы документа удалось выделить автоматически.</p></div>{canEdit && <button className="secondary" type="button" onClick={reanalyzeProgram} disabled={isReanalyzing}>{isReanalyzing ? 'Анализируем...' : 'Повторить анализ'}</button>}</div><div className="diagnosticsGrid"><Metric value={`${diagnostics.quality_score || 0}%`} label="Качество распознавания" /><Metric value={diagnostics.topics_count || 0} label="Темы" /><Metric value={diagnostics.competencies_count || 0} label="Компетенции" /><Metric value={diagnostics.learning_outcomes_count || 0} label="Результаты обучения" /><Metric value={diagnostics.detected_sections_count || 0} label="Разделы документа" /><Metric value={diagnostics.ignored_lines || 0} label="Отфильтровано строк" /></div>{diagnostics.warnings?.length > 0 && <div className="notice"><strong>Предупреждения анализатора</strong><ul>{diagnostics.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}<div className="columns"><List title="Темы" items={program.topics} /><List title="Компетенции" items={program.competencies} /><List title="Результаты обучения" items={program.learning_outcomes} /></div></section>; }
function Metric({ value, label }) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }
function List({ title, items }) { return <div><h3>{title}</h3>{items.length ? <ul className="compactList">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Не найдено</p>}</div>; }
function HistoryList({ title, items, getKey, renderItem, onOpen }) { return <div className="historyColumn"><h3>{title}</h3>{items.length ? <div className="historyItems">{items.slice(0, 8).map((item) => <button className="historyItem" key={getKey(item)} onClick={() => onOpen(item)}>{renderItem(item)}</button>)}</div> : <p className="muted">Пока пусто</p>}</div>; }
function AdminPanel({ users, currentUser, showAdvancedUi, toggleAdvancedUi, updateRole, toggleUser }) { const teachers = users.filter((item) => item.role === 'teacher').length; const methodists = users.filter((item) => item.role === 'methodist').length; const admins = users.filter((item) => item.role === 'admin').length; return <section className="card"><div className="sectionHeader"><div><h2>Администрирование пользователей</h2><p className="muted">Роль пользователя изменяется через выпадающий список.</p></div><div className="itemBankStats"><span>Преподавателей: <strong>{teachers}</strong></span><span>Методистов: <strong>{methodists}</strong></span><span>Админов: <strong>{admins}</strong></span></div></div><div className="adminList">{users.map((userItem) => <div className="adminRow" key={userItem.id}><div><div className="adminNameLine"><strong>{userItem.full_name}</strong>{(userItem.id === currentUser.id || userItem.email === currentUser.email) && <StarButton active={showAdvancedUi} onClick={toggleAdvancedUi} />}</div><span>{userItem.email}</span><span>{roleLabel(userItem.role)} · {userItem.is_active ? 'активен' : 'заблокирован'}</span></div><select value={userItem.role} onChange={(event) => updateRole(userItem.id, event.target.value)}><option value="teacher">Преподаватель</option><option value="methodist">Методист</option><option value="admin">Администратор</option></select><div className="actionGroup"><button className="secondary" onClick={() => toggleUser(userItem.id, userItem.is_active)}>{userItem.is_active ? 'Заблокировать' : 'Разблокировать'}</button></div></div>)}</div></section>; }
function roleLabel(role) { return ({ teacher: 'преподаватель', methodist: 'методист', admin: 'администратор' }[role] || role); }
function statusLabel(status) { return ({ generated: 'Сформировано', in_review: 'На проверке', revision_required: 'Требует доработки', approved: 'Утверждено' }[status] || status); }
function roleChangeMessage(role) { return ({ teacher: 'Права пользователя снижены до преподавателя.', methodist: 'Пользователь назначен методистом.', admin: 'Пользователь повышен до администратора.' }[role] || 'Роль пользователя обновлена.'); }
export default App;
