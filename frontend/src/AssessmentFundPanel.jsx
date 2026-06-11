import React, { useEffect, useMemo, useState } from 'react';
import AssessmentItemBank from './AssessmentItemBank.jsx';
import CompetencyMatrixEditor from './CompetencyMatrixEditor.jsx';

const SECTION_LABELS = {
  competency_matrix: 'Матрица компетенций',
  oral: 'Устный опрос',
  practice: 'Практические задания',
  exam_questions: 'Вопросы для экзамена',
  exam_practice: 'Практические задания для экзамена',
  credit: 'Зачет',
  control_work: 'Контрольная работа',
  coursework: 'Курсовая работа',
  course_project: 'Курсовой проект',
  laboratory: 'Лабораторные работы',
  test_bank: 'Банк тестовых заданий',
  report_topics: 'Темы рефератов и докладов',
  diagnostic: 'Итоговая диагностическая работа',
  grading_rubric: 'Критерии оценивания',
};

function AssessmentFundPanel({ api, program, setError, setSuccess }) {
  const [funds, setFunds] = useState([]);
  const [fund, setFund] = useState(null);
  const [isLoading, setLoading] = useState(false);
  const [isCreating, setCreating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isValidating, setValidating] = useState(false);
  const [disciplineName, setDisciplineName] = useState('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const validation = fund?.validation || {};
  const enabledSections = useMemo(() => fund?.sections?.filter((section) => section.enabled) || [], [fund]);
  const generatedItems = useMemo(
    () => enabledSections.reduce((sum, section) => sum + (section.generated_items || 0), 0),
    [enabledSections],
  );

  useEffect(() => {
    loadFunds();
    setFund(null);
    setDisciplineName('');
    setHasUnsavedChanges(false);
  }, [program?.program_id]);

  async function loadFunds() {
    if (!program?.program_id) return;
    setLoading(true);
    try {
      const response = await api.get('/api/assessment-funds/');
      const related = response.data.filter((item) => item.program_id === program.program_id);
      setFunds(related);
      if (related.length && !fund) {
        setFund(related[0]);
        setDisciplineName(related[0].discipline_name);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось загрузить проекты ФОС.');
    } finally {
      setLoading(false);
    }
  }

  async function createFund() {
    if (!program?.program_id) return;
    setCreating(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/api/assessment-funds/', {
        program_id: program.program_id,
        discipline_name: disciplineName.trim() || null,
      });
      setFund(response.data);
      setDisciplineName(response.data.discipline_name);
      setHasUnsavedChanges(false);
      await loadFunds();
      setSuccess('Структура ФОС сформирована на основании выбранной РПД.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось создать структуру ФОС.');
    } finally {
      setCreating(false);
    }
  }

  async function openFund(fundId) {
    setError('');
    try {
      const response = await api.get(`/api/assessment-funds/${fundId}`);
      setFund(response.data);
      setDisciplineName(response.data.discipline_name);
      setHasUnsavedChanges(false);
      return response.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть ФОС.');
      return null;
    }
  }

  async function refreshCurrentFund() {
    if (!fund?.fund_id) return;
    await openFund(fund.fund_id);
    await loadFunds();
  }

  function updateSection(sectionCode, patch) {
    setFund((current) => ({
      ...current,
      sections: current.sections.map((section) => (
        section.code === sectionCode ? { ...section, ...patch } : section
      )),
    }));
    setHasUnsavedChanges(true);
  }

  function updateTitle(value) {
    setFund((current) => ({ ...current, title: value }));
    setHasUnsavedChanges(true);
  }

  function updateDisciplineName(value) {
    setFund((current) => ({ ...current, discipline_name: value }));
    setDisciplineName(value);
    setHasUnsavedChanges(true);
  }

  async function saveFund() {
    if (!fund?.fund_id) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/assessment-funds/${fund.fund_id}`, {
        title: fund.title,
        discipline_name: fund.discipline_name,
        status: fund.status,
        assessment_types: fund.assessment_types,
        sections: fund.sections,
      });
      setFund(response.data);
      setDisciplineName(response.data.discipline_name);
      setHasUnsavedChanges(false);
      await loadFunds();
      setSuccess('Структура ФОС сохранена.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить ФОС.');
    } finally {
      setSaving(false);
    }
  }

  async function validateFund() {
    if (!fund?.fund_id) return;
    setValidating(true);
    setError('');
    try {
      const response = await api.post(`/api/assessment-funds/${fund.fund_id}/validate`);
      setFund(response.data);
      setHasUnsavedChanges(false);
      setSuccess('Проверка структуры ФОС завершена.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось проверить ФОС.');
    } finally {
      setValidating(false);
    }
  }

  return (
    <section className="card fosCard">
      <div className="sectionHeader">
        <div>
          <p className="eyebrow">Модуль формирования ФОС</p>
          <h2>Фонд оценочных средств</h2>
          <p className="muted">Создайте структуру ФОС по РПД, настройте разделы и сформируйте редактируемый банк заданий.</p>
        </div>
        <div className="actionGroup">
          <button className="secondary" type="button" onClick={loadFunds} disabled={isLoading}>
            {isLoading ? 'Обновляем...' : 'Обновить список'}
          </button>
          <button className="primary" type="button" onClick={createFund} disabled={isCreating}>
            {isCreating ? 'Формируем...' : 'Создать проект ФОС'}
          </button>
        </div>
      </div>

      {!fund && (
        <div className="fosIntro">
          <label>
            Наименование дисциплины
            <input
              value={disciplineName}
              onChange={(event) => setDisciplineName(event.target.value)}
              placeholder="Можно оставить пустым: название будет взято из имени файла"
            />
          </label>
          <p className="muted">После создания система сформирует паспорт ФОС, матрицу компетенций и перечень обязательных разделов.</p>
        </div>
      )}

      {funds.length > 0 && (
        <div className="fosHistory">
          <h3>Проекты ФОС по выбранной РПД</h3>
          <div className="fosHistoryItems">
            {funds.map((item) => (
              <button className={`historyItem ${fund?.fund_id === item.fund_id ? 'activeHistoryItem' : ''}`} key={item.fund_id} type="button" onClick={() => openFund(item.fund_id)}>
                <strong>{item.discipline_name}</strong>
                <span>{fundStatusLabel(item.status)} · заполненность {item.validation.completeness_score}%</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {fund && (
        <>
          <div className="fosToolbar">
            <label>
              Название документа
              <input value={fund.title} onChange={(event) => updateTitle(event.target.value)} />
            </label>
            <label>
              Дисциплина
              <input value={fund.discipline_name} onChange={(event) => updateDisciplineName(event.target.value)} />
            </label>
            <div className="actionGroup">
              <button className="secondary" type="button" onClick={validateFund} disabled={isValidating || hasUnsavedChanges}>
                {isValidating ? 'Проверяем...' : 'Проверить структуру'}
              </button>
              <button className="primary" type="button" onClick={saveFund} disabled={isSaving || !hasUnsavedChanges}>
                {isSaving ? 'Сохраняем...' : 'Сохранить ФОС'}
              </button>
            </div>
          </div>

          {hasUnsavedChanges && <div className="notice">Есть несохраненные изменения в структуре ФОС. Сохраните их до генерации банка заданий.</div>}

          <div className="diagnosticsGrid">
            <Metric value={`${validation.completeness_score || 0}%`} label="Заполненность структуры" />
            <Metric value={`${validation.topics_coverage_score || 0}%`} label="Покрытие тем" />
            <Metric value={`${validation.competencies_coverage_score || 0}%`} label="Покрытие компетенций" />
            <Metric value={enabledSections.length} label="Активные разделы" />
            <Metric value={fund.competencies.length} label="Компетенции" />
            <Metric value={generatedItems} label="Сформировано заданий" />
          </div>

          {validation.warnings?.length > 0 && (
            <div className="notice">
              <strong>Результаты проверки</strong>
              <ul>{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </div>
          )}

          <div className="fosGrid">
            <div>
              <h3>Разделы ФОС</h3>
              <div className="fosSections">
                {fund.sections.map((section) => (
                  <article className={`fosSection ${section.enabled ? '' : 'fosSectionDisabled'}`} key={section.code}>
                    <div className="questionTopline">
                      <div>
                        <strong>{section.title}</strong>
                        <p>{SECTION_LABELS[section.assessment_type] || section.assessment_type}</p>
                      </div>
                      <label className="toggleLabel">
                        <input type="checkbox" checked={section.enabled} onChange={(event) => updateSection(section.code, { enabled: event.target.checked })} />
                        Включить
                      </label>
                    </div>
                    <p className="muted">{section.description}</p>
                    <div className="fosSectionMeta">
                      <span>Тем: {section.topics.length} · заданий: {section.generated_items || 0}</span>
                      <label>
                        План заданий
                        <input type="number" min="0" max="1000" value={section.planned_items} onChange={(event) => updateSection(section.code, { planned_items: Number(event.target.value) })} />
                      </label>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <CompetencyMatrixEditor
              api={api}
              fund={fund}
              setFund={setFund}
              setError={setError}
              setSuccess={setSuccess}
              onFundRefresh={refreshCurrentFund}
            />
          </div>

          {!hasUnsavedChanges && (
            <AssessmentItemBank
              api={api}
              fund={fund}
              sections={fund.sections}
              setError={setError}
              setSuccess={setSuccess}
              onFundRefresh={refreshCurrentFund}
            />
          )}
        </>
      )}
    </section>
  );
}

function Metric({ value, label }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function fundStatusLabel(status) {
  return ({ draft: 'Черновик', generated: 'Сформировано', in_review: 'На проверке', revision_required: 'Требует доработки', approved: 'Утверждено' }[status] || status);
}

export default AssessmentFundPanel;
