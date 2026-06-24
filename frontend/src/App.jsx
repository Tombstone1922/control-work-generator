import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import AssessmentFundPanel from './AssessmentFundPanel.jsx';

const API_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'control_work_generator_token';
const USER_KEY = 'control_work_generator_user';
const THEME_KEY = 'control_work_generator_theme';
const LOCKED_STATUSES = new Set(['in_review', 'approved']);

const defaultGenerationParams = {
  variants_count: 2,
  questions_per_variant: 5,
  difficulty: 'medium',
  question_types: ['open'],
};

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '');
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem(USER_KEY);
    return stored ? JSON.parse(stored) : null;
  });
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'light');
  const [activePage, setActivePage] = useState('workspace');
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ full_name: '', email: '', password: '' });
  const [file, setFile] = useState(null);
  const [program, setProgram] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [programsHistory, setProgramsHistory] = useState([]);
  const [generationsHistory, setGenerationsHistory] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [params, setParams] = useState(defaultGenerationParams);
  const [reviewComment, setReviewComment] = useState('');
  const [isUploading, setUploading] = useState(false);
  const [isReanalyzing, setReanalyzing] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [isHistoryLoading, setHistoryLoading] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [regeneratingQuestionId, setRegeneratingQuestionId] = useState(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
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
      const payload = authMode === 'login'
        ? { email: authForm.email, password: authForm.password }
        : authForm;
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
    setGeneration(null);
    setProgramsHistory([]);
    setGenerationsHistory([]);
    setAdminUsers([]);
    setHasUnsavedChanges(false);
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
    setGeneration(null);
    setHasUnsavedChanges(false);
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
      setSuccess('РПД повторно проанализирована улучшенным алгоритмом.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось повторно проанализировать РПД.');
    } finally {
      setReanalyzing(false);
    }
  }

  async function runGeneration() {
    if (!canEditWorkspace) return setError('Генерация доступна преподавателю или администратору.');
    if (!program?.program_id) return setError('Сначала загрузите РПД.');
    setError('');
    setSuccess('');
    setGenerating(true);
    setHasUnsavedChanges(false);
    try {
      const response = await api.post('/api/generation/run', { program_id: program.program_id, ...params });
      setGeneration(response.data);
      setReviewComment(response.data.review_comment || '');
      setActivePage('administration');
      await loadHistory();
      setSuccess('Контрольная работа сформирована.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось выполнить генерацию.');
    } finally {
      setGenerating(false);
    }
  }

  async function openProgram(programId) {
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/programs/${programId}`);
      setProgram(response.data);
      setGeneration(null);
      setHasUnsavedChanges(false);
      setActivePage('workspace');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть РПД из истории.');
    }
  }

  async function openGeneration(sessionId) {
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/generation/${sessionId}`);
      setGeneration(response.data);
      setReviewComment(response.data.review_comment || '');
      const programResponse = await api.get(`/api/programs/${response.data.program_id}`);
      setProgram(programResponse.data);
      setHasUnsavedChanges(false);
      setActivePage('administration');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть генерацию из истории.');
    }
  }

  async function saveEditedGeneration() {
    if (!generation?.session_id) return;
    setError('');
    setSuccess('');
    setSaving(true);
    try {
      const response = await api.put(`/api/generation/${generation.session_id}`, { variants: generation.variants });
      setGeneration(response.data);
      setHasUnsavedChanges(false);
      await loadHistory();
      setSuccess('Изменения сохранены. Отчет качества пересчитан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить изменения.');
    } finally {
      setSaving(false);
    }
  }

  async function regenerateQuestion(questionId) {
    if (!generation?.session_id) return;
    if (hasUnsavedChanges) return setError('Сначала сохраните текущие ручные изменения.');
    setError('');
    setSuccess('');
    setRegeneratingQuestionId(questionId);
    try {
      const response = await api.post(`/api/generation/${generation.session_id}/regenerate-question/${questionId}`);
      setGeneration(response.data);
      await loadHistory();
      setSuccess('Задание перегенерировано.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось перегенерировать задание.');
    } finally {
      setRegeneratingQuestionId(null);
    }
  }

  async function changeStatus(status) {
    if (!generation?.session_id) return;
    if (hasUnsavedChanges) return setError('Сначала сохраните ручные изменения.');
    try {
      const response = await api.patch(`/api/generation/${generation.session_id}/status`, { status, review_comment: reviewComment });
      setGeneration(response.data);
      await loadHistory();
      setSuccess('Статус обновлен.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось изменить статус.');
    }
  }

  async function downloadDocx() {
    if (!generation?.session_id) return;
    try {
      const response = await api.get(`/api/export/docx/${generation.session_id}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `control_work_${generation.session_id}.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось скачать DOCX.');
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

  function updateQuestionTypes(value) {
    const types = value.split(',').map((item) => item.trim()).filter(Boolean);
    setParams((current) => ({ ...current, question_types: types.length ? types : ['open'] }));
  }

  function updateQuestion(variantNumber, questionId, field, value) {
    setGeneration((current) => ({
      ...current,
      variants: current.variants.map((variant) => variant.variant_number !== variantNumber ? variant : {
        ...variant,
        questions: variant.questions.map((question) => question.id === questionId ? { ...question, [field]: value } : question),
      }),
    }));
    setHasUnsavedChanges(true);
  }

  function deleteQuestion(variantNumber, questionId) {
    setGeneration((current) => ({
      ...current,
      variants: current.variants.map((variant) => variant.variant_number !== variantNumber ? variant : {
        ...variant,
        questions: variant.questions.filter((question) => question.id !== questionId),
      }),
    }));
    setHasUnsavedChanges(true);
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
          <strong>{user.full_name}</strong>
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
          <span>{user.role === 'admin' ? 'Администрирование' : 'История и сервис'}</span>
          <small>{user.role === 'admin' ? 'История, пользователи, роли' : 'История, диагностика, сервисные инструменты'}</small>
        </button>
      </nav>

      {error && <div className="alert">{error}</div>}
      {success && <div className="success">{success}</div>}

      {activePage === 'workspace' ? (
        <WorkspacePage
          user={user}
          file={file}
          setFile={setFile}
          program={program}
          isUploading={isUploading}
          uploadProgram={uploadProgram}
          isReanalyzing={isReanalyzing}
          reanalyzeProgram={reanalyzeProgram}
          api={api}
          setError={setError}
          setSuccess={setSuccess}
        />
      ) : (
        <AdministrationPage
          user={user}
          program={program}
          params={params}
          setParams={setParams}
          updateQuestionTypes={updateQuestionTypes}
          runGeneration={runGeneration}
          isGenerating={isGenerating}
          programsHistory={programsHistory}
          generationsHistory={generationsHistory}
          loadHistory={loadHistory}
          isHistoryLoading={isHistoryLoading}
          openProgram={openProgram}
          openGeneration={openGeneration}
          generation={generation}
          reviewComment={reviewComment}
          setReviewComment={setReviewComment}
          hasUnsavedChanges={hasUnsavedChanges}
          isSaving={isSaving}
          regeneratingQuestionId={regeneratingQuestionId}
          saveEditedGeneration={saveEditedGeneration}
          regenerateQuestion={regenerateQuestion}
          deleteQuestion={deleteQuestion}
          updateQuestion={updateQuestion}
          changeStatus={changeStatus}
          downloadDocx={downloadDocx}
          adminUsers={adminUsers}
          updateAdminUserRole={updateAdminUserRole}
          toggleAdminUser={toggleAdminUser}
        />
      )}
    </main>
  );
}

function ThemeToggle({ isDark, onToggle }) {
  return (
    <button className={`themeToggle ${isDark ? 'themeToggleDark' : ''}`} type="button" onClick={onToggle} aria-label={isDark ? 'Включить светлую тему' : 'Включить тёмную тему'}>
      <span className="themeToggleTrack">
        <span className="themeIcon themeSun">☀</span>
        <span className="themeIcon themeMoon">☾</span>
        <span className="themeToggleThumb" />
      </span>
      <strong>{isDark ? 'Тёмная' : 'Светлая'}</strong>
    </button>
  );
}

function WorkspacePage({ user, file, setFile, program, isUploading, uploadProgram, isReanalyzing, reanalyzeProgram, api, setError, setSuccess }) {
  const canEdit = user.role === 'teacher' || user.role === 'admin';
  return (
    <div className="workspacePage">
      <section className="pageIntro card">
        <div>
          <p className="eyebrow">{canEdit ? 'Основной сценарий' : 'Сценарий проверки'}</p>
          <h2>{canEdit ? 'РПД → структура ФОС → банк заданий' : 'Проверка РПД, ФОС и банка заданий'}</h2>
          <p className="muted">{canEdit ? 'Здесь оставлены только действия, которые нужны преподавателю при подготовке оценочных материалов.' : 'Методист видит материалы преподавателей, проверяет структуру ФОС и принимает решение по статусу.'}</p>
        </div>
        <div className="stepPills">
          <span>1. РПД</span>
          <span>2. Анализ</span>
          <span>3. ФОС</span>
          <span>4. Экспорт</span>
        </div>
      </section>

      <section className="workspaceGrid">
        {canEdit ? (
          <form className="card uploadCard" onSubmit={uploadProgram}>
            <p className="eyebrow">Загрузка</p>
            <h2>Рабочая программа дисциплины</h2>
            <p className="muted">DOCX, PDF или TXT. После загрузки система выделит темы, компетенции и результаты обучения.</p>
            <input className="fileInput" type="file" accept=".docx,.pdf,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <button className="primary" disabled={isUploading}>{isUploading ? 'Анализируем...' : 'Загрузить и проанализировать'}</button>
            {file && <p className="muted selectedFile">Выбран файл: <strong>{file.name}</strong></p>}
          </form>
        ) : (
          <section className="card uploadCard">
            <p className="eyebrow">Проверка</p>
            <h2>Материалы преподавателей</h2>
            <p className="muted">Методист не загружает и не редактирует РПД. Откройте нужный документ из истории в разделе “История и сервис”.</p>
          </section>
        )}

        <section className="card currentDocCard">
          <p className="eyebrow">Текущий документ</p>
          <h2>{program?.filename || 'РПД пока не выбрана'}</h2>
          {program ? (
            <div className="docStats">
              <Metric value={program.topics?.length || 0} label="тем" />
              <Metric value={program.competencies?.length || 0} label="компетенций" />
              <Metric value={`${program.analysis_report?.diagnostics?.quality_score || 0}%`} label="качество" />
            </div>
          ) : (
            <p className="muted">{canEdit ? 'Загрузите РПД или откройте ранее загруженный документ из раздела “Администрирование”.' : 'Откройте ранее загруженный документ из истории.'}</p>
          )}
        </section>
      </section>

      {program && <ProgramAnalysisSection program={program} canEdit={canEdit} isReanalyzing={isReanalyzing} reanalyzeProgram={reanalyzeProgram} />}
      {program && <AssessmentFundPanel api={api} program={program} user={user} setError={setError} setSuccess={setSuccess} />}
    </div>
  );
}

function AdministrationPage({ user, program, params, setParams, updateQuestionTypes, runGeneration, isGenerating, programsHistory, generationsHistory, loadHistory, isHistoryLoading, openProgram, openGeneration, generation, reviewComment, setReviewComment, hasUnsavedChanges, isSaving, regeneratingQuestionId, saveEditedGeneration, regenerateQuestion, deleteQuestion, updateQuestion, changeStatus, downloadDocx, adminUsers, updateAdminUserRole, toggleAdminUser }) {
  const canUseServiceGeneration = user.role === 'teacher' || user.role === 'admin';
  return (
    <div className="adminPage">
      <section className="pageIntro card adminIntro">
        <div>
          <p className="eyebrow">{user.role === 'admin' ? 'Администрирование и права' : 'История и проверка'}</p>
          <h2>{user.role === 'admin' ? 'Пользователи, роли и сервисные инструменты' : 'История, диагностика и материалы на проверке'}</h2>
          <p className="muted">{user.role === 'admin' ? 'Администратор может повышать пользователей до методистов или администраторов и управлять доступом.' : 'Сюда вынесены история и дополнительные действия, чтобы рабочая область не превращалась в перегруженную панель.'}</p>
        </div>
      </section>

      <section className="adminDashboard">
        {canUseServiceGeneration && (
          <section className="card quickGenerationCard">
            <p className="eyebrow">Сервисный режим</p>
            <h2>Быстрая генерация контрольной</h2>
            <p className="muted">Старый сценарий генерации контрольной работы оставлен как дополнительный инструмент. Основная работа с ФОС находится на первой странице.</p>
            <div className="miniGrid adminMiniGrid">
              <label>Вариантов<input type="number" min="1" max="20" value={params.variants_count} onChange={(event) => setParams({ ...params, variants_count: Number(event.target.value) })} /></label>
              <label>Заданий<input type="number" min="1" max="50" value={params.questions_per_variant} onChange={(event) => setParams({ ...params, questions_per_variant: Number(event.target.value) })} /></label>
              <label>Сложность<select value={params.difficulty} onChange={(event) => setParams({ ...params, difficulty: event.target.value })}><option value="easy">Базовый</option><option value="medium">Средний</option><option value="hard">Повышенный</option></select></label>
            </div>
            <label>Типы заданий<input value={params.question_types.join(', ')} onChange={(event) => updateQuestionTypes(event.target.value)} /></label>
            <button className="primary" type="button" onClick={runGeneration} disabled={isGenerating || !program}>{isGenerating ? 'Генерируем...' : 'Сформировать контрольную'}</button>
          </section>
        )}

        <section className="card systemCard">
          <p className="eyebrow">Техническая подсказка</p>
          <h2>Запуск локальной модели</h2>
          <p className="muted">Для генерации через Qwen окно модели должно быть запущено отдельно.</p>
          <code>scripts\windows\start_qwen.ps1</code>
          <code>scripts\windows\check_local_llm.ps1</code>
          <p className="muted">Профилирование последней генерации отображается внутри банка заданий ФОС.</p>
        </section>
      </section>

      <section className="card historyCard">
        <div className="sectionHeader">
          <div>
            <h2>История работы</h2>
            <p className="muted">Ранее загруженные РПД и сгенерированные контрольные материалы.</p>
          </div>
          <button className="secondary" onClick={loadHistory}>{isHistoryLoading ? 'Обновляем...' : 'Обновить'}</button>
        </div>
        <div className="historyGrid">
          <HistoryList title="РПД" items={programsHistory} getKey={(item) => item.program_id} renderItem={(item) => <><strong>{item.filename}</strong><span>{item.topics.length} тем · качество анализа {item.analysis_report?.diagnostics?.quality_score || 0}%</span></>} onOpen={(item) => openProgram(item.program_id)} />
          <HistoryList title="Генерации" items={generationsHistory} getKey={(item) => item.session_id} renderItem={(item) => <><strong>{item.session_id.slice(0, 8)}...</strong><span>{statusLabel(item.status)} · {item.quality_report.total_questions} заданий</span></>} onOpen={(item) => openGeneration(item.session_id)} />
        </div>
      </section>

      {generation && <GenerationEditor generation={generation} user={user} reviewComment={reviewComment} setReviewComment={setReviewComment} hasUnsavedChanges={hasUnsavedChanges} isSaving={isSaving} regeneratingQuestionId={regeneratingQuestionId} saveEditedGeneration={saveEditedGeneration} regenerateQuestion={regenerateQuestion} deleteQuestion={deleteQuestion} updateQuestion={updateQuestion} changeStatus={changeStatus} downloadDocx={downloadDocx} />}
      {user.role === 'admin' && <AdminPanel currentUser={user} users={adminUsers} updateRole={updateAdminUserRole} toggleUser={toggleAdminUser} />}
    </div>
  );
}

function AuthScreen({ authMode, setAuthMode, authForm, setAuthForm, submitAuth, error, success }) {
  return <main className="page authPage"><section className="authCard card"><p className="eyebrow">Фонд Оценочных Средств</p><h1>Генератор контрольных работ</h1>{error && <div className="alert">{error}</div>}{success && <div className="success">{success}</div>}<div className="authTabs"><button className={authMode === 'login' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('login')}>Вход</button><button className={authMode === 'register' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('register')}>Регистрация</button></div><form onSubmit={submitAuth}>{authMode === 'register' && <label>ФИО<input value={authForm.full_name} onChange={(event) => setAuthForm({ ...authForm, full_name: event.target.value })} required /></label>}<label>Email<input type="email" value={authForm.email} onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })} required /></label><label>Пароль<input type="password" value={authForm.password} onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })} required /></label><button className="primary">{authMode === 'login' ? 'Войти' : 'Создать пользователя'}</button></form></section></main>;
}

function ProgramAnalysisSection({ program, canEdit, isReanalyzing, reanalyzeProgram }) {
  const report = program.analysis_report || {};
  const diagnostics = report.diagnostics || {};
  return <section className="card"><div className="sectionHeader"><div><h2>Результаты анализа РПД</h2><p className="muted">Структурированный отчет показывает, какие элементы документа удалось выделить автоматически.</p></div>{canEdit && <button className="secondary" type="button" onClick={reanalyzeProgram} disabled={isReanalyzing}>{isReanalyzing ? 'Анализируем...' : 'Повторить анализ'}</button>}</div><div className="diagnosticsGrid"><Metric value={`${diagnostics.quality_score || 0}%`} label="Качество распознавания" /><Metric value={diagnostics.topics_count || 0} label="Темы" /><Metric value={diagnostics.competencies_count || 0} label="Компетенции" /><Metric value={diagnostics.learning_outcomes_count || 0} label="Результаты обучения" /><Metric value={diagnostics.detected_sections_count || 0} label="Разделы документа" /><Metric value={diagnostics.ignored_lines || 0} label="Отфильтровано строк" /></div>{diagnostics.warnings?.length > 0 && <div className="notice"><strong>Предупреждения анализатора</strong><ul>{diagnostics.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}<div className="columns"><List title="Темы" items={program.topics} /><List title="Компетенции" items={program.competencies} /><List title="Результаты обучения" items={program.learning_outcomes} /></div><div className="analysisDetails"><List title="Распознанные разделы документа" items={report.detected_sections || []} /><List title="Исходные строки для тем" items={report.topic_sources || []} /></div></section>;
}

function Metric({ value, label }) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }

function GenerationEditor({ generation, user, reviewComment, setReviewComment, hasUnsavedChanges, isSaving, regeneratingQuestionId, saveEditedGeneration, regenerateQuestion, deleteQuestion, updateQuestion, changeStatus, downloadDocx }) {
  const canEdit = user.role === 'admin' || (user.role === 'teacher' && !LOCKED_STATUSES.has(generation.status));
  return <section className="card"><div className="sectionHeader"><div><h2>{canEdit ? 'Сформированная контрольная работа' : 'Просмотр контрольной работы'}</h2><span className="badge">{statusLabel(generation.status)}</span></div><div className="actionGroup">{canEdit && <button className="secondary" onClick={saveEditedGeneration} disabled={!hasUnsavedChanges || isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить изменения'}</button>}<button className="download" onClick={downloadDocx} disabled={hasUnsavedChanges}>Скачать DOCX</button></div></div>{generation.review_comment && <div className="notice">Комментарий проверяющего: {generation.review_comment}</div>}<div className="quality"><div><strong>{generation.quality_report.topic_coverage}</strong><span>Покрытие тем</span></div><div><strong>{generation.quality_report.duplicate_rate}</strong><span>Доля дублей</span></div><div><strong>{generation.quality_report.total_questions}</strong><span>Всего заданий</span></div></div><Workflow user={user} generation={generation} reviewComment={reviewComment} setReviewComment={setReviewComment} changeStatus={changeStatus} /><div className="variants">{generation.variants.map((variant) => <article className="variant" key={variant.variant_number}><h3>Вариант {variant.variant_number}</h3>{variant.questions.map((question, index) => <div className="question editorQuestion" key={question.id}><div className="questionTopline"><strong>Задание {index + 1}</strong>{canEdit && <div className="questionActions"><button className="secondary smallButton" onClick={() => regenerateQuestion(question.id)} disabled={regeneratingQuestionId === question.id || hasUnsavedChanges}>{regeneratingQuestionId === question.id ? 'Генерируем...' : 'Перегенерировать'}</button><button className="danger" onClick={() => deleteQuestion(variant.variant_number, question.id)}>Удалить</button></div>}</div><label>Текст<textarea value={question.text} readOnly={!canEdit} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'text', event.target.value)} /></label><div className="miniGrid"><label>Тема<input value={question.topic} disabled={!canEdit} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'topic', event.target.value)} /></label><label>Тип<select value={question.type} disabled={!canEdit} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'type', event.target.value)}><option value="open">open</option><option value="test">test</option><option value="practice">practice</option></select></label><label>Сложность<select value={question.difficulty} disabled={!canEdit} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'difficulty', event.target.value)}><option value="easy">easy</option><option value="medium">medium</option><option value="hard">hard</option></select></label></div></div>)}</article>)}</div></section>;
}

function Workflow({ user, generation, reviewComment, setReviewComment, changeStatus }) {
  if (user.role === 'teacher') {
    if (LOCKED_STATUSES.has(generation.status)) return <div className="notice">Материал отправлен на проверку или утвержден. Редактирование закрыто.</div>;
    return <div className="workflow"><button className="primary" onClick={() => changeStatus('in_review')}>Отправить на проверку</button></div>;
  }
  if (user.role === 'methodist' || user.role === 'admin') {
    return <div className="workflow"><label>Комментарий проверяющего<textarea value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} /></label><div className="actionGroup"><button className="danger" onClick={() => changeStatus('revision_required')}>Требует доработки</button><button className="primary" onClick={() => changeStatus('approved')}>Утвердить</button></div></div>;
  }
  return null;
}

function AdminPanel({ users, updateRole, toggleUser }) {
  const teachers = users.filter((item) => item.role === 'teacher').length;
  const methodists = users.filter((item) => item.role === 'methodist').length;
  const admins = users.filter((item) => item.role === 'admin').length;
  return <section className="card"><div className="sectionHeader"><div><h2>Администрирование пользователей</h2><p className="muted">Роль пользователя изменяется через выпадающий список. Администратор может назначить преподавателя методистом или повысить методиста до администратора.</p></div><div className="itemBankStats"><span>Преподавателей: <strong>{teachers}</strong></span><span>Методистов: <strong>{methodists}</strong></span><span>Админов: <strong>{admins}</strong></span></div></div><div className="adminList">{users.map((userItem) => <div className="adminRow" key={userItem.id}><div><strong>{userItem.full_name}</strong><span>{userItem.email}</span><span>{roleLabel(userItem.role)} · {userItem.is_active ? 'активен' : 'заблокирован'}</span></div><select value={userItem.role} onChange={(event) => updateRole(userItem.id, event.target.value)}><option value="teacher">Преподаватель</option><option value="methodist">Методист</option><option value="admin">Администратор</option></select><div className="actionGroup"><button className="secondary" onClick={() => toggleUser(userItem.id, userItem.is_active)}>{userItem.is_active ? 'Заблокировать' : 'Разблокировать'}</button></div></div>)}</div></section>;
}

function List({ title, items }) { return <div><h3>{title}</h3>{items.length ? <ul className="compactList">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Не найдено</p>}</div>; }
function HistoryList({ title, items, getKey, renderItem, onOpen }) { return <div className="historyColumn"><h3>{title}</h3>{items.length ? <div className="historyItems">{items.slice(0, 8).map((item) => <button className="historyItem" key={getKey(item)} onClick={() => onOpen(item)}>{renderItem(item)}</button>)}</div> : <p className="muted">Пока пусто</p>}</div>; }
function roleLabel(role) { return ({ teacher: 'преподаватель', methodist: 'методист', admin: 'администратор' }[role] || role); }
function statusLabel(status) { return ({ generated: 'Сформировано', in_review: 'На проверке', revision_required: 'Требует доработки', approved: 'Утверждено' }[status] || status); }
function roleChangeMessage(role) { return ({ teacher: 'Права пользователя снижены до преподавателя.', methodist: 'Пользователь назначен методистом.', admin: 'Пользователь повышен до администратора.' }[role] || 'Роль пользователя обновлена.'); }

export default App;
