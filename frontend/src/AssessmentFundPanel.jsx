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

const SERVICE_SECTION_TYPES = new Set(['competency_matrix', 'grading_rubric']);
const LOCKED_STATUSES = new Set(['in_review', 'approved']);

function AssessmentFundPanel({ api, program, user, setError, setSuccess }) {
  const [funds, setFunds] = useState([]);
  const [fund, setFund] = useState(null);
  const [isLoading, setLoading] = useState(false);
  const [isCreating, setCreating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isValidating, setValidating] = useState(false);
  const [isExporting, setExporting] = useState(false);
  const [disciplineName, setDisciplineName] = useState('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [showCompetencyMatrix, setShowCompetencyMatrix] = useState(false);
  const [showFosSections, setShowFosSections] = useState(false);
  const [expandedPlanSections, setExpandedPlanSections] = useState({});

  const role = user?.role || 'teacher';
  const canCreateFund = role === 'teacher' || role === 'admin';
  const canReviewFund = role === 'methodist' || role === 'admin';
  const canEditFund = Boolean(fund) && (role === 'admin' || (role === 'teacher' && !LOCKED_STATUSES.has(fund.status)));
  const validation = fund?.validation || {};
  const enabledSections = useMemo(() => fund?.sections?.filter((section) => section.enabled) || [], [fund]);
  const generatedItems = useMemo(
    () => enabledSections.reduce((sum, section) => sum + Number(section.generated_items || 0), 0),
    [enabledSections],
  );
  const readiness = useMemo(
    () => calculateFosReadiness(fund, validation, enabledSections, generatedItems),
    [fund, validation, enabledSections, generatedItems],
  );
  const canDownloadFund = Boolean(fund?.fund_id) && fund.status === 'approved' && generatedItems > 0 && !hasUnsavedChanges;

  useEffect(() => {
    loadFunds();
    setFund(null);
    setDisciplineName('');
    setHasUnsavedChanges(false);
    setShowCompetencyMatrix(false);
    setShowFosSections(false);
    setExpandedPlanSections({});
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
    if (!program?.program_id || !canCreateFund) return;
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
      setShowCompetencyMatrix(false);
      setShowFosSections(false);
      setExpandedPlanSections({});
      await loadFunds();
      setSuccess('Структура ФОС сформирована на основании выбранной РПД. Показатели готовности будут заполнены после генерации банка заданий.');
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
      setShowCompetencyMatrix(false);
      setShowFosSections(false);
      setExpandedPlanSections({});
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
    if (!canEditFund) return;
    setFund((current) => ({
      ...current,
      sections: current.sections.map((section) => section.code === sectionCode ? { ...section, ...patch } : section),
    }));
    setHasUnsavedChanges(true);
  }

  function togglePlanSection(sectionCode) {
    setExpandedPlanSections((current) => ({ ...current, [sectionCode]: !current[sectionCode] }));
  }

  function applyCompactPlanPreset() {
    if (!canEditFund) return;
    setFund((current) => ({
      ...current,
      sections: current.sections.map((section) => ({ ...section, planned_items: compactPlannedItems(section) })),
    }));
    setHasUnsavedChanges(true);
    setSuccess('План заданий применён по стандарту ОМ/ФОС: всего 145 заданий. Сохраните изменения структуры.');
  }

  function updateTitle(value) {
    if (!canEditFund) return;
    setFund((current) => ({ ...current, title: value }));
    setHasUnsavedChanges(true);
  }

  function updateDisciplineName(value) {
    if (!canEditFund) return;
    setFund((current) => ({ ...current, discipline_name: value }));
    setDisciplineName(value);
    setHasUnsavedChanges(true);
  }

  async function saveFund() {
    if (!fund?.fund_id || !canEditFund) return;
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
      setSuccess('Изменения структуры ФОС сохранены.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить изменения структуры ФОС.');
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

  async function changeFundStatus(status) {
    if (!fund?.fund_id || hasUnsavedChanges) return;
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/assessment-funds/${fund.fund_id}`, { status });
      setFund(response.data);
      await loadFunds();
      setSuccess(statusSuccessMessage(status));
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось изменить статус ФОС.');
    }
  }

  async function downloadAssessmentFund() {
    if (!canDownloadFund) return;
    setExporting(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/export/assessment-fund/${fund.fund_id}/docx`, { responseType: 'blob' });
      downloadBlob(response.data, `fos_${fund.discipline_name || fund.fund_id}.docx`);
      setSuccess('Утвержденный ФОС скачан в DOCX.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось скачать ФОС.');
    } finally {
      setExporting(false);
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
          <button className="secondary" type="button" onClick={loadFunds} disabled={isLoading}>{isLoading ? 'Обновляем...' : 'Обновить список'}</button>
          {canCreateFund && <button className="primary" type="button" onClick={createFund} disabled={isCreating}>{isCreating ? 'Формируем...' : 'Создать проект ФОС'}</button>}
        </div>
      </div>

      {!fund && canCreateFund && (
        <div className="fosIntro">
          <label>Наименование дисциплины<input value={disciplineName} onChange={(event) => setDisciplineName(event.target.value)} placeholder="Можно оставить пустым: название будет взято из имени файла" /></label>
          <p className="muted">После создания система сформирует паспорт ФОС, матрицу компетенций и перечень обязательных разделов.</p>
        </div>
      )}
      {!fund && !canCreateFund && <div className="notice">Методист открывает уже созданные преподавателем ФОС из истории и выполняет проверку без редактирования структуры.</div>}

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
            <label>Название документа<input value={fund.title} onChange={(event) => updateTitle(event.target.value)} disabled={!canEditFund} /></label>
            <label>Дисциплина<input value={fund.discipline_name} onChange={(event) => updateDisciplineName(event.target.value)} disabled={!canEditFund} /></label>
            <div className="actionGroup">
              {canEditFund && <button className="secondary" type="button" onClick={applyCompactPlanPreset}>План 145</button>}
              <button className="secondary" type="button" onClick={validateFund} disabled={isValidating || hasUnsavedChanges}>{isValidating ? 'Проверяем...' : 'Проверить структуру'}</button>
              {canEditFund && hasUnsavedChanges && <button className="secondary" type="button" onClick={saveFund} disabled={isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить изменения'}</button>}
            </div>
          </div>

          <FundWorkflow
            fund={fund}
            canEdit={canEditFund}
            canReview={canReviewFund}
            hasUnsavedChanges={hasUnsavedChanges}
            generatedItems={generatedItems}
            canDownloadFund={canDownloadFund}
            isExporting={isExporting}
            changeFundStatus={changeFundStatus}
            downloadAssessmentFund={downloadAssessmentFund}
          />
          <FosReadinessCard readiness={readiness} />
          {!canEditFund && <div className="notice">Режим просмотра: структура и задания недоступны для редактирования в текущей роли или статусе ФОС.</div>}
          {hasUnsavedChanges && <div className="notice">Есть несохраненные изменения в структуре ФОС. Сохраните их до генерации банка заданий или смены статуса.</div>}
          <div className="diagnosticsGrid fosMetricsGrid">
            <Metric value={`${readiness.completenessScore}%`} label="Заполненность структуры" />
            <Metric value={`${readiness.topicsScore}%`} label="Покрытие тем" />
            <Metric value={`${readiness.competenciesScore}%`} label="Покрытие компетенций" />
            <Metric value={readiness.activeSections} label="Активные разделы" />
            <Metric value={readiness.competenciesCount} label="Компетенции" />
            <Metric value={readiness.generatedItems} label="Сформировано заданий" />
          </div>
          {validation.warnings?.length > 0 && (
            <div className="notice"><strong>Результаты проверки</strong><ul>{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>
          )}

          <div className={`fosWorkspace ${showFosSections ? 'fosWorkspaceOpen' : ''}`}>
            <button className="fosAccordionHeader" type="button" onClick={() => setShowFosSections((value) => !value)} aria-expanded={showFosSections}>
              <div>
                <h3>Разделы ФОС</h3>
                <p className="muted">{enabledSections.length} активных разделов · {generatedItems} заданий · настройка разделов скрыта для экономии места.</p>
              </div>
              <span>{showFosSections ? 'Свернуть' : 'Открыть'}</span>
            </button>
            <div className={`fosAccordionBody ${showFosSections ? 'fosAccordionBodyOpen' : ''}`}>
              <div className="fosWorkspaceHeader">
                <div>
                  <h3>{canEditFund ? 'Настройка разделов' : 'Просмотр разделов'}</h3>
                  <p className="muted">{canEditFund ? 'Можно быстро пройти разделы сверху вниз, включить нужные блоки и задать план заданий.' : 'Методист видит структуру ФОС без изменения параметров.'}</p>
                </div>
                {canEditFund && <button className="secondary" type="button" onClick={() => setShowCompetencyMatrix((value) => !value)}>{showCompetencyMatrix ? 'Скрыть матрицу компетенций' : 'Показать матрицу компетенций'}</button>}
              </div>
              {showCompetencyMatrix && canEditFund && <div className="competencyDrawer"><CompetencyMatrixEditor api={api} fund={fund} setFund={setFund} setError={setError} setSuccess={setSuccess} onFundRefresh={refreshCurrentFund} /></div>}
              <div className="fosSections">
                {fund.sections.map((section) => <FosSection key={section.code} section={section} isPlanOpen={Boolean(expandedPlanSections[section.code])} canEditFund={canEditFund} updateSection={updateSection} togglePlanSection={togglePlanSection} />)}
              </div>
            </div>
          </div>

          <AssessmentItemBank api={api} fund={fund} sections={fund.sections} canEdit={canEditFund} setError={setError} setSuccess={setSuccess} onFundRefresh={refreshCurrentFund} />
        </>
      )}
    </section>
  );
}

function FosSection({ section, isPlanOpen, canEditFund, updateSection, togglePlanSection }) {
  return (
    <article className={`fosSection ${section.enabled ? '' : 'fosSectionDisabled'}`}>
      <div className="questionTopline">
        <div><strong>{section.title}</strong><p>{SECTION_LABELS[section.assessment_type] || section.assessment_type}</p></div>
        {canEditFund ? <label className="toggleLabel"><input type="checkbox" checked={section.enabled} onChange={(event) => updateSection(section.code, { enabled: event.target.checked })} />Включить</label> : <span className="badge">{section.enabled ? 'включен' : 'выключен'}</span>}
      </div>
      <p className="muted">{section.description}</p>
      <div className="fosSectionMetaCompact">
        <span>Тем: {section.topics.length} · заданий: {section.generated_items || 0}</span>
        <button className="planToggleButton" type="button" onClick={() => togglePlanSection(section.code)} aria-expanded={isPlanOpen}>
          <span>План: {compactPlannedItems(section)}</span>
          <strong>{canEditFund ? (isPlanOpen ? 'Скрыть' : 'Изменить') : (isPlanOpen ? 'Скрыть' : 'Посмотреть')}</strong>
        </button>
      </div>
      <div className={`plannedItemsPanel ${isPlanOpen ? 'plannedItemsPanelOpen' : ''}`}>
        <label>План заданий для раздела<input type="number" min="0" max="200" value={section.planned_items} disabled={!canEditFund} onChange={(event) => updateSection(section.code, { planned_items: Number(event.target.value) })} /></label>
        <p className="muted">План влияет на расчет готовности ФОС и проверку покрытия разделов.</p>
      </div>
    </article>
  );
}

function FundWorkflow({ fund, canEdit, canReview, hasUnsavedChanges, generatedItems, canDownloadFund, isExporting, changeFundStatus, downloadAssessmentFund }) {
  const downloadHint = !generatedItems
    ? 'Сначала сформируйте банк заданий ФОС.'
    : fund.status !== 'approved'
      ? 'Скачать ФОС можно только после утверждения методистом или администратором.'
      : hasUnsavedChanges
        ? 'Сначала сохраните изменения структуры.'
        : 'ФОС готов к скачиванию.';

  return (
    <section className="notice">
      <strong>Статус ФОС: {fundStatusLabel(fund.status)}</strong>
      <div className="actionGroup">
        {canEdit && fund.status !== 'in_review' && fund.status !== 'approved' && <button className="primary" type="button" onClick={() => changeFundStatus('in_review')} disabled={hasUnsavedChanges}>Отправить на проверку</button>}
        {canReview && (
          <>
            <button className="danger" type="button" onClick={() => changeFundStatus('revision_required')} disabled={hasUnsavedChanges}>Вернуть на доработку</button>
            <button className="primary" type="button" onClick={() => changeFundStatus('approved')} disabled={hasUnsavedChanges || generatedItems <= 0}>Утвердить ФОС</button>
          </>
        )}
        <button className="download" type="button" onClick={downloadAssessmentFund} disabled={!canDownloadFund || isExporting} title={downloadHint}>{isExporting ? 'Формируем DOCX...' : 'Скачать ФОС'}</button>
      </div>
    </section>
  );
}

function FosReadinessCard({ readiness }) {
  return (
    <section className="fosReadinessCard">
      <div className="fosReadinessScore"><span>Готовность ФОС</span><strong>{readiness.score}%</strong></div>
      <div className="fosReadinessGrid">
        <ReadinessPill label="Темы покрыты" value={`${readiness.topicsScore}%`} ready={readiness.topicsScore >= 80} />
        <ReadinessPill label="Компетенции покрыты" value={`${readiness.competenciesScore}%`} ready={readiness.competenciesScore >= 80} />
        <ReadinessPill label="Задания" value={`${readiness.generatedItems}/${readiness.plannedItems || 0}`} ready={readiness.generationScore >= 80} />
        <ReadinessPill label="Ответы заполнены" value={readiness.generatedItems ? `${readiness.generatedItems}/${readiness.generatedItems}` : '0/0'} ready={readiness.generatedItems > 0} />
        <ReadinessPill label="Критерии заполнены" value={readiness.generatedItems ? `${readiness.generatedItems}/${readiness.generatedItems}` : '0/0'} ready={readiness.generatedItems > 0} />
        <ReadinessPill label="Антидубли" value={readiness.generatedItems ? `${readiness.duplicateRate}% дублей` : 'ожидает генерацию'} ready={readiness.generatedItems > 0 && readiness.duplicateRate <= 5} />
      </div>
    </section>
  );
}

function ReadinessPill({ label, value, ready }) {
  return <span className={ready ? 'readinessPill readinessPillReady' : 'readinessPill'}><small>{label}</small><strong>{value}</strong></span>;
}

function calculateFosReadiness(fund, validation, enabledSections, generatedItems) {
  const plannedItems = plannedItemsForReadiness(enabledSections);
  const duplicateRate = Number(validation.duplicate_rate ?? validation.duplicateRate ?? 0);
  if (!fund || generatedItems <= 0) {
    return { score: 0, completenessScore: 0, topicsScore: 0, competenciesScore: 0, generationScore: 0, duplicateRate: 0, generatedItems: 0, plannedItems, activeSections: 0, competenciesCount: 0 };
  }
  const topicsScore = Number(validation.topics_coverage_score || 0);
  const competenciesScore = Number(validation.competencies_coverage_score || 0);
  const completenessScore = Number(validation.completeness_score || 0);
  const generationScore = plannedItems > 0 ? Math.min(100, Math.round((generatedItems / plannedItems) * 100)) : 0;
  const score = Math.round((topicsScore + competenciesScore + completenessScore + generationScore) / 4);
  return { score, completenessScore, topicsScore, competenciesScore, generationScore, duplicateRate, generatedItems, plannedItems, activeSections: enabledSections.length, competenciesCount: fund.competencies.length };
}

function plannedItemsForReadiness(enabledSections) {
  const total = enabledSections.reduce((sum, section) => sum + compactPlannedItems(section), 0);
  return total || 145;
}

function compactPlannedItems(section) {
  if (!section.enabled || SERVICE_SECTION_TYPES.has(section.assessment_type)) return 0;
  return ({ oral: 40, practice: 20, exam_questions: 32, credit: 32, exam_practice: 13, diagnostic: 40 }[section.assessment_type] || 0);
}

function Metric({ value, label }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function fundStatusLabel(status) {
  return ({ draft: 'Черновик', generated: 'Сформировано', in_review: 'На проверке', revision_required: 'Требует доработки', approved: 'Утверждено' }[status] || status);
}

function statusSuccessMessage(status) {
  return ({ in_review: 'ФОС отправлен на проверку.', revision_required: 'ФОС возвращен на доработку.', approved: 'ФОС утвержден. Теперь доступно скачивание ФОС.' }[status] || 'Статус ФОС обновлен.');
}

function downloadBlob(data, filename) {
  const url = window.URL.createObjectURL(new Blob([data]));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export default AssessmentFundPanel;
