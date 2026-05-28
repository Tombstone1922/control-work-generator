import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'control_work_generator_token';
const USER_KEY = 'control_work_generator_user';

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
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({
    full_name: '',
    email: '',
    password: '',
    role: 'teacher',
  });

  const [file, setFile] = useState(null);
  const [program, setProgram] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [programsHistory, setProgramsHistory] = useState([]);
  const [generationsHistory, setGenerationsHistory] = useState([]);
  const [params, setParams] = useState(defaultGenerationParams);
  const [isUploading, setUploading] = useState(false);
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

  const exportUrl = useMemo(() => {
    if (!generation?.session_id) return '';
    return `${API_URL}/api/export/docx/${generation.session_id}`;
  }, [generation]);

  useEffect(() => {
    if (token) {
      api.get('/api/auth/me')
        .then((response) => {
          setUser(response.data);
          localStorage.setItem(USER_KEY, JSON.stringify(response.data));
          loadHistory();
        })
        .catch(() => logout(false));
    }
  }, [token]);

  function authHeaders() {
    return token ? { Authorization: `Bearer ${token}` } : {};
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

  async function uploadProgram(event) {
    event.preventDefault();
    if (!file) {
      setError('Выберите файл РПД в формате DOCX, PDF или TXT.');
      return;
    }

    setError('');
    setSuccess('');
    setUploading(true);
    setGeneration(null);
    setHasUnsavedChanges(false);

    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post('/api/programs/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data', ...authHeaders() },
      });
      setProgram(response.data);
      await loadHistory();
      setSuccess('РПД успешно загружена и проанализирована.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось загрузить и проанализировать РПД.');
    } finally {
      setUploading(false);
    }
  }

  async function runGeneration() {
    if (!program?.program_id) {
      setError('Сначала загрузите РПД.');
      return;
    }

    setError('');
    setSuccess('');
    setGenerating(true);
    setHasUnsavedChanges(false);

    try {
      const response = await api.post('/api/generation/run', {
        program_id: program.program_id,
        ...params,
      });
      setGeneration(response.data);
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
      const programResponse = await api.get(`/api/programs/${response.data.program_id}`);
      setProgram(programResponse.data);
      setHasUnsavedChanges(false);
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
      const response = await api.put(`/api/generation/${generation.session_id}`, {
        variants: generation.variants,
      });
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
    if (hasUnsavedChanges) {
      setError('Сначала сохраните текущие ручные изменения, затем выполните повторную генерацию задания.');
      return;
    }

    setError('');
    setSuccess('');
    setRegeneratingQuestionId(questionId);

    try {
      const response = await api.post(`/api/generation/${generation.session_id}/regenerate-question/${questionId}`);
      setGeneration(response.data);
      await loadHistory();
      setSuccess('Задание перегенерировано. Отчет качества пересчитан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось перегенерировать задание.');
    } finally {
      setRegeneratingQuestionId(null);
    }
  }

  function updateQuestionTypes(value) {
    const types = value.split(',').map((item) => item.trim()).filter(Boolean);
    setParams((current) => ({ ...current, question_types: types.length ? types : ['open'] }));
  }

  function updateQuestion(variantNumber, questionId, field, value) {
    setGeneration((current) => {
      if (!current) return current;
      return {
        ...current,
        variants: current.variants.map((variant) => {
          if (variant.variant_number !== variantNumber) return variant;
          return {
            ...variant,
            questions: variant.questions.map((question) => (
              question.id === questionId ? { ...question, [field]: value } : question
            )),
          };
        }),
      };
    });
    setHasUnsavedChanges(true);
  }

  function deleteQuestion(variantNumber, questionId) {
    setGeneration((current) => {
      if (!current) return current;
      return {
        ...current,
        variants: current.variants.map((variant) => {
          if (variant.variant_number !== variantNumber) return variant;
          return {
            ...variant,
            questions: variant.questions.filter((question) => question.id !== questionId),
          };
        }),
      };
    });
    setHasUnsavedChanges(true);
  }

  if (!user) {
    return (
      <main className="page authPage">
        <section className="authCard card">
          <p className="eyebrow">ВКР · закрытый контур</p>
          <h1>Генератор контрольных работ</h1>
          <p className="heroText">Войдите или зарегистрируйтесь, чтобы работать с РПД, генерациями и экспортом контрольных работ.</p>

          {error && <div className="alert">{error}</div>}
          {success && <div className="success">{success}</div>}

          <div className="authTabs">
            <button className={authMode === 'login' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('login')}>Вход</button>
            <button className={authMode === 'register' ? 'primary' : 'secondary'} type="button" onClick={() => setAuthMode('register')}>Регистрация</button>
          </div>

          <form onSubmit={submitAuth}>
            {authMode === 'register' && (
              <label>
                ФИО
                <input value={authForm.full_name} onChange={(event) => setAuthForm({ ...authForm, full_name: event.target.value })} required />
              </label>
            )}
            <label>
              Email
              <input type="email" value={authForm.email} onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })} required />
            </label>
            <label>
              Пароль
              <input type="password" value={authForm.password} onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })} required />
            </label>
            {authMode === 'register' && (
              <label>
                Роль
                <select value={authForm.role} onChange={(event) => setAuthForm({ ...authForm, role: event.target.value })}>
                  <option value="teacher">Преподаватель</option>
                  <option value="methodist">Методист</option>
                  <option value="admin">Администратор</option>
                </select>
              </label>
            )}
            <button className="primary" type="submit">{authMode === 'login' ? 'Войти' : 'Создать пользователя'}</button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <section className="hero card">
        <div>
          <p className="eyebrow">ВКР · MVP-прототип</p>
          <h1>Генератор контрольных работ по РПД</h1>
          <p className="heroText">Загрузите рабочую программу дисциплины, получите извлеченные темы и сформируйте варианты контрольной работы с отчетом качества.</p>
        </div>
        <div className="userBox">
          <strong>{user.full_name}</strong>
          <span>{user.email}</span>
          <span>Роль: {roleLabel(user.role)}</span>
          <button className="secondary smallButton" type="button" onClick={() => logout()}>Выйти</button>
        </div>
      </section>

      {error && <div className="alert">{error}</div>}
      {success && <div className="success">{success}</div>}

      <section className="grid">
        <form className="card" onSubmit={uploadProgram}>
          <h2>1. Загрузка РПД</h2>
          <p className="muted">Поддерживаются DOCX, PDF и TXT. После загрузки backend извлечет текст и выполнит базовый анализ.</p>
          <input className="fileInput" type="file" accept=".docx,.pdf,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <button className="primary" type="submit" disabled={isUploading}>{isUploading ? 'Анализируем...' : 'Загрузить и проанализировать'}</button>
        </form>

        <section className="card">
          <h2>2. Параметры генерации</h2>
          <label>Количество вариантов<input type="number" min="1" max="20" value={params.variants_count} onChange={(event) => setParams({ ...params, variants_count: Number(event.target.value) })} /></label>
          <label>Заданий в варианте<input type="number" min="1" max="50" value={params.questions_per_variant} onChange={(event) => setParams({ ...params, questions_per_variant: Number(event.target.value) })} /></label>
          <label>Уровень сложности<select value={params.difficulty} onChange={(event) => setParams({ ...params, difficulty: event.target.value })}><option value="easy">Базовый</option><option value="medium">Средний</option><option value="hard">Повышенный</option></select></label>
          <label>Типы заданий через запятую<input value={params.question_types.join(', ')} onChange={(event) => updateQuestionTypes(event.target.value)} placeholder="open, test, practice" /></label>
          <button className="primary" type="button" onClick={runGeneration} disabled={isGenerating || !program}>{isGenerating ? 'Генерируем...' : 'Сформировать контрольную'}</button>
        </section>
      </section>

      <section className="card historyCard">
        <div className="sectionHeader">
          <div>
            <h2>История работы</h2>
            <p className="muted">Преподаватель видит свои материалы. Методист и администратор видят все материалы.</p>
          </div>
          <button className="secondary" type="button" onClick={loadHistory} disabled={isHistoryLoading}>{isHistoryLoading ? 'Обновляем...' : 'Обновить историю'}</button>
        </div>
        <div className="historyGrid">
          <HistoryList title="Загруженные РПД" emptyText="История РПД пока пустая" items={programsHistory} getKey={(item) => item.program_id} renderItem={(item) => <><strong>{item.filename}</strong><span>{item.topics.length} тем · {item.competencies.length} компетенций</span></>} onOpen={(item) => openProgram(item.program_id)} />
          <HistoryList title="Сеансы генерации" emptyText="История генераций пока пустая" items={generationsHistory} getKey={(item) => item.session_id} renderItem={(item) => <><strong>{item.session_id.slice(0, 8)}...</strong><span>{item.quality_report.total_questions} заданий · покрытие {item.quality_report.topic_coverage}</span></>} onOpen={(item) => openGeneration(item.session_id)} />
        </div>
      </section>

      {program && (
        <section className="card">
          <h2>Результаты анализа РПД</h2>
          <div className="columns"><List title="Темы" items={program.topics} /><List title="Компетенции" items={program.competencies} /><List title="Результаты обучения" items={program.learning_outcomes} /></div>
        </section>
      )}

      {generation && (
        <section className="card">
          <div className="sectionHeader">
            <div><h2>Сформированная контрольная работа</h2><p className="muted">Можно отредактировать задания, сохранить изменения и экспортировать DOCX.</p></div>
            <div className="actionGroup"><button className="secondary" type="button" onClick={saveEditedGeneration} disabled={isSaving || !hasUnsavedChanges}>{isSaving ? 'Сохраняем...' : 'Сохранить изменения'}</button><a className={`download ${hasUnsavedChanges ? 'disabledLink' : ''}`} href={hasUnsavedChanges ? undefined : exportUrl} target="_blank" rel="noreferrer">Скачать DOCX</a></div>
          </div>
          {hasUnsavedChanges && <div className="notice">Есть несохраненные изменения. Сначала сохраните их, чтобы DOCX экспортировался с актуальными заданиями.</div>}
          <div className="quality"><div><strong>{generation.quality_report.topic_coverage}</strong><span>Покрытие тем</span></div><div><strong>{generation.quality_report.duplicate_rate}</strong><span>Доля дублей</span></div><div><strong>{generation.quality_report.total_questions}</strong><span>Всего заданий</span></div></div>
          <h3>Рекомендации</h3><ul className="recommendations">{generation.quality_report.recommendations.map((item) => <li key={item}>{item}</li>)}</ul>
          <div className="variants">
            {generation.variants.map((variant) => (
              <article className="variant" key={variant.variant_number}>
                <h3>Вариант {variant.variant_number}</h3>
                {variant.questions.map((question, index) => (
                  <div className="question editorQuestion" key={question.id}>
                    <div className="questionTopline"><strong>Задание {index + 1}</strong><div className="questionActions"><button className="secondary smallButton" type="button" onClick={() => regenerateQuestion(question.id)} disabled={regeneratingQuestionId === question.id || hasUnsavedChanges}>{regeneratingQuestionId === question.id ? 'Генерируем...' : 'Перегенерировать'}</button><button className="danger" type="button" onClick={() => deleteQuestion(variant.variant_number, question.id)}>Удалить</button></div></div>
                    <label>Текст задания<textarea value={question.text} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'text', event.target.value)} /></label>
                    <div className="miniGrid"><label>Тема<input value={question.topic} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'topic', event.target.value)} /></label><label>Тип<select value={question.type} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'type', event.target.value)}><option value="open">open</option><option value="test">test</option><option value="practice">practice</option></select></label><label>Сложность<select value={question.difficulty} onChange={(event) => updateQuestion(variant.variant_number, question.id, 'difficulty', event.target.value)}><option value="easy">easy</option><option value="medium">medium</option><option value="hard">hard</option></select></label></div>
                  </div>
                ))}
              </article>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function List({ title, items }) {
  return <div><h3>{title}</h3>{items.length ? <ul className="compactList">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">Не найдено</p>}</div>;
}

function HistoryList({ title, emptyText, items, getKey, renderItem, onOpen }) {
  return <div className="historyColumn"><h3>{title}</h3>{items.length ? <div className="historyItems">{items.slice(0, 8).map((item) => <button className="historyItem" key={getKey(item)} type="button" onClick={() => onOpen(item)}>{renderItem(item)}</button>)}</div> : <p className="muted">{emptyText}</p>}</div>;
}

function roleLabel(role) {
  const labels = { teacher: 'преподаватель', methodist: 'методист', admin: 'администратор' };
  return labels[role] || role;
}

export default App;
