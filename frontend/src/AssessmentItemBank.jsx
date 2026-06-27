import React, { useEffect, useMemo, useState } from 'react';

const QWEN_SEED_MODES = new Set(['qwen_seed_good', 'qwen35_seed_good', 'qwen8_seed_good', 'qwen_small_seed_good']);

function AssessmentItemBank({ api, fund, sections, canEdit = true, setError, setSuccess, onFundRefresh }) {
  const [items, setItems] = useState([]);
  const [validation, setValidation] = useState(null);
  const [trainingStats, setTrainingStats] = useState(null);
  const [generationSummary, setGenerationSummary] = useState(null);
  const [contextSummary, setContextSummary] = useState(null);
  const [selectedContext, setSelectedContext] = useState(null);
  const [isLoadingContext, setLoadingContext] = useState(false);
  const [selectedSectionCode, setSelectedSectionCode] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [teacherComment, setTeacherComment] = useState('');
  const [generationMode, setGenerationMode] = useState('intelligent_v2');
  const [learnedMaxItems] = useState(12);
  const [narrowMaxItems] = useState(40);
  const [fallbackToTemplate] = useState(true);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [maxItemsPerSection] = useState(40);
  const [isLoading, setLoading] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isValidating, setValidating] = useState(false);
  const [isExporting, setExporting] = useState(false);
  const [isTraining, setTraining] = useState(false);
  const [isExportingDataset, setExportingDataset] = useState(false);

  const enabledSections = useMemo(
    () => sections.filter((section) => section.enabled && !['competency_matrix', 'grading_rubric'].includes(section.assessment_type)),
    [sections],
  );
  const sectionMap = useMemo(() => Object.fromEntries(sections.map((section) => [section.code, section.title])), [sections]);
  const visibleItems = useMemo(() => selectedSectionCode ? items.filter((item) => item.section_code === selectedSectionCode) : items, [items, selectedSectionCode]);
  const selectedItem = useMemo(() => items.find((item) => item.id === selectedItemId) || null, [items, selectedItemId]);
  const sourceStats = useMemo(() => items.reduce((acc, item) => {
    const key = item.source_kind || 'template';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {}), [items]);

  useEffect(() => {
    if (!fund?.fund_id) return;
    setSelectedSectionCode('');
    setSelectedItemId('');
    setValidation(null);
    setGenerationSummary(null);
    setTeacherComment('');
    setSelectedContext(null);
    loadItems();
    if (canEdit) loadTrainingStats();
    loadContextSummary();
  }, [fund?.fund_id, canEdit]);

  useEffect(() => setTeacherComment(''), [selectedItemId]);

  useEffect(() => {
    if (!selectedItem?.topic || !fund?.fund_id) return;
    loadTopicContext(selectedItem.topic, false);
  }, [selectedItem?.id, selectedItem?.topic, fund?.fund_id]);

  async function loadItems(sectionCode = '') {
    if (!fund?.fund_id) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(`/api/assessment-items/${fund.fund_id}`, { params: sectionCode ? { section_code: sectionCode } : {} });
      setItems(response.data);
      if (response.data.length && !selectedItemId) setSelectedItemId(response.data[0].id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось загрузить банк заданий.');
    } finally {
      setLoading(false);
    }
  }

  async function loadTrainingStats() {
    if (!fund?.fund_id) return;
    try {
      const response = await api.get('/api/training-examples/stats', { params: { fund_id: fund.fund_id } });
      setTrainingStats(response.data);
    } catch (err) {
      setTrainingStats(null);
    }
  }

  async function loadContextSummary() {
    if (!fund?.fund_id) return;
    try {
      const response = await api.get(`/api/context-module/${fund.fund_id}/summary`);
      setContextSummary(response.data);
    } catch (err) {
      setContextSummary(null);
    }
  }

  async function loadTopicContext(topic = selectedItem?.topic, showSuccess = true) {
    if (!fund?.fund_id || !topic) return;
    setLoadingContext(true);
    try {
      const response = await api.get(`/api/context-module/${fund.fund_id}/topic`, { params: { topic } });
      setSelectedContext(response.data);
      if (showSuccess) setSuccess('Контекстный модуль обновлен.');
    } catch (err) {
      setSelectedContext(null);
      if (showSuccess) setError(err.response?.data?.detail || 'Не удалось загрузить контекстный модуль.');
    } finally {
      setLoadingContext(false);
    }
  }

  async function generateItems() {
    if (!fund?.fund_id || !canEdit) return;
    setGenerating(true);
    setError('');
    setSuccess('');
    try {
      const endpoint = QWEN_SEED_MODES.has(generationMode)
        ? `/api/qwen-training/${fund.fund_id}/generate-good`
        : `/api/assessment-items/${fund.fund_id}/generate`;
      const response = await api.post(endpoint, {
        section_code: selectedSectionCode || null,
        replace_existing: replaceExisting,
        max_items_per_section: Number(maxItemsPerSection),
        generation_mode: generationMode,
        learned_max_items: Number(learnedMaxItems),
        narrow_max_items: Number(narrowMaxItems),
        fallback_to_template: fallbackToTemplate,
      });
      const generatedItems = response.data.items || response.data;
      setItems(generatedItems);
      setSelectedItemId(generatedItems[0]?.id || '');
      setGenerationSummary(response.data.items ? response.data : null);
      await onFundRefresh();
      await validateItems(false);
      await loadContextSummary();
      await loadTrainingStats();
      setSuccess(successMessage(response.data.used_mode));
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сформировать банк заданий.');
    } finally {
      setGenerating(false);
    }
  }

  async function validateItems(showSuccess = true) {
    if (!fund?.fund_id) return;
    setValidating(true);
    setError('');
    try {
      const response = await api.post(`/api/assessment-items/${fund.fund_id}/validate`);
      setValidation(response.data);
      if (showSuccess) setSuccess('Проверка банка заданий завершена.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось проверить банк заданий.');
    } finally {
      setValidating(false);
    }
  }

  async function downloadAssessmentFund() {
    if (!fund?.fund_id) return;
    setExporting(true);
    setError('');
    try {
      const response = await api.get(`/api/export/assessment-fund/${fund.fund_id}/docx`, { responseType: 'blob' });
      downloadBlob(response.data, `fos_${fund.discipline_name || fund.fund_id}.docx`);
      setSuccess('DOCX-файл ФОС сформирован и скачан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сформировать DOCX-файл ФОС.');
    } finally {
      setExporting(false);
    }
  }

  async function downloadTrainingDataset() {
    if (!fund?.fund_id || !canEdit) return;
    setExportingDataset(true);
    setError('');
    try {
      const response = await api.get('/api/training-examples/export/jsonl', { params: { fund_id: fund.fund_id }, responseType: 'blob' });
      downloadBlob(response.data, `training_dataset_${fund.discipline_name || fund.fund_id}.jsonl`);
      setSuccess('Обучающая выборка JSONL сформирована и скачана.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось экспортировать обучающую выборку.');
    } finally {
      setExportingDataset(false);
    }
  }

  async function addTrainingExample(qualityLabel) {
    if (!selectedItem || !canEdit) return;
    setTraining(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/api/training-examples/${fund.fund_id}/items/${selectedItem.id}`, { quality_label: qualityLabel, teacher_comment: teacherComment });
      await loadTrainingStats();
      setTeacherComment('');
      setSuccess('Задание сохранено в обучающую выборку.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить обучающий пример.');
    } finally {
      setTraining(false);
    }
  }

  function patchSelectedItem(patch) {
    if (!canEdit) return;
    setItems((current) => current.map((item) => item.id === selectedItemId ? { ...item, ...patch } : item));
  }

  async function saveSelectedItem() {
    if (!selectedItem || !canEdit) return;
    setSaving(true);
    setError('');
    try {
      const response = await api.put(`/api/assessment-items/${fund.fund_id}/${selectedItem.id}`, {
        topic: selectedItem.topic,
        competency_code: selectedItem.competency_code,
        indicator: selectedItem.indicator,
        difficulty: selectedItem.difficulty,
        text: selectedItem.text,
        answer: selectedItem.answer,
        criteria: selectedItem.criteria,
        status: selectedItem.status,
      });
      setItems((current) => current.map((item) => item.id === response.data.id ? response.data : item));
      await validateItems(false);
      await loadTopicContext(response.data.topic, false);
      setSuccess('Задание сохранено. Теперь его можно добавить в обучающую выборку.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить задание.');
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedItem() {
    if (!selectedItem || !canEdit) return;
    setError('');
    try {
      await api.delete(`/api/assessment-items/${fund.fund_id}/${selectedItem.id}`);
      const nextItems = items.filter((item) => item.id !== selectedItem.id);
      setItems(nextItems);
      setSelectedItemId(nextItems[0]?.id || '');
      await onFundRefresh();
      await validateItems(false);
      setSuccess('Задание удалено.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось удалить задание.');
    }
  }

  return (
    <section className="itemBank">
      <div className="sectionHeader">
        <div>
          <h3>{canEdit ? 'Банк заданий ФОС' : 'Просмотр банка заданий ФОС'}</h3>
          <p className="muted">{canEdit ? 'Формируйте задания, редактируйте их экспертно и сохраняйте хорошие/плохие примеры для обучения интеллектуального генератора ФОС.' : 'Методист проверяет сформированный банк заданий без изменения формулировок.'}</p>
        </div>
        <div className="actionGroup">
          <button className="secondary" type="button" onClick={() => loadItems(selectedSectionCode)} disabled={isLoading}>{isLoading ? 'Обновляем...' : 'Обновить банк'}</button>
          <button className="secondary" type="button" onClick={() => validateItems()} disabled={isValidating}>{isValidating ? 'Проверяем...' : 'Проверить банк'}</button>
          <button className="download" type="button" onClick={downloadAssessmentFund} disabled={isExporting}>{isExporting ? 'Формируем DOCX...' : 'Скачать полный ФОС'}</button>
        </div>
      </div>

      <div className="itemBankHero">
        <div>
          <span className="eyebrow">Context-module</span>
          <h3>РПД → контекстный модуль → база знаний → антидубли</h3>
          <p className="muted">Интерфейс показывает, какой предметный контекст система использует для генерации: связанные темы, ключевые термины, результаты обучения и источник данных.</p>
        </div>
        <div className="sourceMiniStats">
          {Object.entries(sourceStats).length ? Object.entries(sourceStats).map(([kind, count]) => <span key={kind}><SourceBadge kind={kind} /> <strong>{count}</strong></span>) : <span className="muted">Источники появятся после генерации.</span>}
        </div>
      </div>

      {canEdit && <TrainingDatasetPanel stats={trainingStats} downloadTrainingDataset={downloadTrainingDataset} isExportingDataset={isExportingDataset} />}
      <ContextModuleSummaryPanel summary={contextSummary} />
      {canEdit && <LearningModePanel generationMode={generationMode} setGenerationMode={setGenerationMode} stats={trainingStats} />}
      {!canEdit && <div className="notice">Режим методиста: генерация, редактирование, удаление и разметка обучающих примеров скрыты.</div>}
      {generationSummary && <GenerationSummary generation={generationSummary} />}

      <div className="itemBankToolbar simplifiedGenerationToolbar">
        <label>Раздел ФОС<select value={selectedSectionCode} onChange={(event) => setSelectedSectionCode(event.target.value)}><option value="">Все активные разделы</option>{enabledSections.map((section) => <option key={section.code} value={section.code}>{section.title}</option>)}</select></label>
        {canEdit && <label className="toggleLabel itemBankCheckbox"><input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />Заменить старые задания</label>}
        {canEdit && <button className="primary" type="button" onClick={generateItems} disabled={isGenerating || !enabledSections.length}>{isGenerating ? 'Формируем...' : QWEN_SEED_MODES.has(generationMode) ? 'Сформировать и обучить' : 'Сформировать задания'}</button>}
      </div>

      <div className="itemBankStats"><span>Всего заданий: <strong>{items.length}</strong></span><span>В выбранном разделе: <strong>{visibleItems.length}</strong></span></div>
      {validation && <ValidationDashboard validation={validation} sectionMap={sectionMap} />}

      <div className="itemBankGrid">
        <div className="itemBankList">
          {visibleItems.length ? visibleItems.map((item, index) => (
            <button className={`itemBankListItem ${selectedItemId === item.id ? 'activeItemBankListItem' : ''}`} key={item.id} type="button" onClick={() => setSelectedItemId(item.id)}>
              <div className="itemCardHeader"><strong>{index + 1}. {item.topic}</strong><SourceBadge kind={item.source_kind} /></div>
              <span>{assessmentTypeLabel(item.assessment_type)} · {difficultyLabel(item.difficulty)} · {item.competency_code || 'без компетенции'}</span>
              <small>{shortSourceContext(item.source_context)}</small>
            </button>
          )) : <p className="muted">Задания еще не сформированы.</p>}
        </div>

        <div className="itemBankEditor">
          {selectedItem ? (
            <>
              <div className="questionTopline">
                <div><h3>{canEdit ? 'Редактор задания' : 'Просмотр задания'}</h3><SourceBadge kind={selectedItem.source_kind} /></div>
                {canEdit && <div className="actionGroup"><button className="danger" type="button" onClick={deleteSelectedItem}>Удалить</button><button className="primary" type="button" onClick={saveSelectedItem} disabled={isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить'}</button></div>}
              </div>
              <ContextModuleTopicPanel context={selectedContext} isLoading={isLoadingContext} refresh={() => loadTopicContext(selectedItem.topic, true)} />
              <label>Формулировка<textarea value={selectedItem.text} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ text: event.target.value })} /></label>
              <label>Эталонный ответ<textarea value={selectedItem.answer} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ answer: event.target.value })} /></label>
              <div className="miniGrid"><label>Тема<input value={selectedItem.topic} disabled={!canEdit} onChange={(event) => patchSelectedItem({ topic: event.target.value })} /></label><label>Компетенция<input value={selectedItem.competency_code} disabled={!canEdit} onChange={(event) => patchSelectedItem({ competency_code: event.target.value })} /></label><label>Сложность<select value={selectedItem.difficulty} disabled={!canEdit} onChange={(event) => patchSelectedItem({ difficulty: event.target.value })}><option value="easy">Базовая</option><option value="medium">Средняя</option><option value="hard">Повышенная</option></select></label></div>
              <label>Индикатор<textarea value={selectedItem.indicator} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ indicator: event.target.value })} /></label>
              <label>Критерии оценивания<textarea value={(selectedItem.criteria || []).join('\n')} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ criteria: event.target.value.split('\n').filter(Boolean) })} /></label>
              <div className="sourceContextBox"><strong>Источник формирования</strong><p>{selectedItem.source_context || 'не указан'}</p></div>
              {canEdit && <section className="trainingFeedback"><h3>Экспертная разметка для самообучения</h3><p className="muted">После ручной правки сохраните задание как хороший пример, плохой пример или пример, требующий доработки.</p><label>Комментарий преподавателя<textarea value={teacherComment} onChange={(event) => setTeacherComment(event.target.value)} /></label><div className="actionGroup trainingActions"><button className="secondary" type="button" onClick={() => addTrainingExample('needs_revision')} disabled={isTraining}>Нужно доработать</button><button className="danger" type="button" onClick={() => addTrainingExample('bad')} disabled={isTraining}>Плохой пример</button><button className="primary" type="button" onClick={() => addTrainingExample('good')} disabled={isTraining}>Хороший пример</button></div></section>}
            </>
          ) : <p className="muted">Выберите задание слева.</p>}
        </div>
      </div>
    </section>
  );
}

function TrainingDatasetPanel({ stats, downloadTrainingDataset, isExportingDataset }) {
  return <section className="trainingDatasetPanel"><div><h3>Обучающая выборка</h3><p className="muted">Здесь накапливаются экспертно подтвержденные примеры для будущего дообучения интеллектуального генератора ФОС.</p></div><div className="itemBankStats"><span>Всего: <strong>{stats?.total_examples || 0}</strong></span><span>Хороших: <strong>{stats?.good_examples || 0}</strong></span><span>Плохих: <strong>{stats?.bad_examples || 0}</strong></span><span>На доработку: <strong>{stats?.revision_examples || 0}</strong></span><span>Тем: <strong>{stats?.topics_count || 0}</strong></span><span>Компетенций: <strong>{stats?.competencies_count || 0}</strong></span></div><button className="download" type="button" onClick={downloadTrainingDataset} disabled={isExportingDataset}>{isExportingDataset ? 'Экспортируем...' : 'Скачать JSONL датасет'}</button></section>;
}

function ContextModuleSummaryPanel({ summary }) {
  return <section className="contextModulePanel"><div><span className="eyebrow">Context-module summary</span><h3>{summary?.discipline_name || 'Контекст дисциплины'}</h3><p className="muted">Сводка предметной базы, из которой генератор берет термины и связи между темами.</p></div><div className="contextModuleStats"><span>Тем: <strong>{summary?.topics_total || 0}</strong></span><span>Источники: <strong>{summary?.sources?.join(', ') || '—'}</strong></span></div>{summary?.key_terms?.length > 0 && <ChipList title="Ключевые термины" values={summary.key_terms} />}{summary?.sample_topics?.length > 0 && <ChipList title="Примеры тем" values={summary.sample_topics} />}</section>;
}

function ContextModuleTopicPanel({ context, isLoading, refresh }) {
  return <section className="contextTopicPanel"><div className="contextTopicHeader"><div><span className="eyebrow">Context-module for selected item</span><h3>{context?.topic || 'Контекст темы'}</h3><p className="muted">Источник: {context?.source || '—'} · профиль: {context?.profile_name || '—'}</p></div><button className="secondary" type="button" onClick={refresh} disabled={isLoading}>{isLoading ? 'Обновляем...' : 'Обновить контекст'}</button></div>{context?.key_terms?.length > 0 && <ChipList title="Ключевые термины" values={context.key_terms} />}{context?.related_topics?.length > 0 && <ChipList title="Связанные темы" values={context.related_topics} />}{context?.learning_outcomes?.length > 0 && <CompactList title="Результаты обучения" values={context.learning_outcomes} />}{context?.competencies?.length > 0 && <ChipList title="Компетенции из контекста" values={context.competencies} />}</section>;
}

function ChipList({ title, values }) {
  return <div className="chipList"><strong>{title}</strong><div>{values.slice(0, 12).map((value) => <span key={value}>{value}</span>)}</div></div>;
}

function CompactList({ title, values }) {
  return <div className="compactList"><strong>{title}</strong><ul>{values.slice(0, 4).map((value) => <li key={value}>{value}</li>)}</ul></div>;
}

function LearningModePanel({ generationMode, setGenerationMode, stats }) {
  const hasGoodExamples = (stats?.good_examples || 0) > 0;
  const isIntelligentV2 = generationMode === 'intelligent_v2';
  const isQwenSeed = generationMode === 'qwen_seed_good';
  const isQwen35Seed = generationMode === 'qwen35_seed_good';
  const isQwen8Seed = generationMode === 'qwen8_seed_good';
  const isQwenSmallSeed = generationMode === 'qwen_small_seed_good';
  return <section className="learningModePanel simplifiedLearningModePanel"><div><h3>Генерация банка заданий</h3><p className="muted">По умолчанию используется интеллектуальный генератор 2.0: он собирает полный OM/ФОС-профиль, а локальную 14B-модель применяет только к сложным заданиям.</p></div><div className="learningModeGrid simplifiedLearningModeGrid"><label>Режим генерации<select value={generationMode} onChange={(event) => setGenerationMode(event.target.value)}><option value="intelligent_v2">Интеллектуальный генератор 2.0 — OM/ФОС 145</option><option value="narrow_llm">Интеллектуальный генератор ФОС</option><option value="qwen_seed_good">Qwen3 14B: сгенерировать и пометить как хорошие</option><option value="qwen8_seed_good">Qwen3 8B: быстрый кандидат</option><option value="qwen_small_seed_good">Qwen Small 3/4B: максимальная скорость</option><option value="qwen35_seed_good">Qwen3.5 9B: быстрый эксперимент</option><option value="hybrid">Интеллектуальный генератор + шаблонная страховка</option><option value="learned">Генерация по экспертным примерам</option><option value="template">Базовый шаблонный режим</option></select></label></div>{isIntelligentV2 && <div className="notice">Новый основной режим: 40 устных вопросов, 20 практических текущего контроля, 32 вопроса к зачету, 13 практических заданий к зачету и 40 диагностических заданий. 14B-модель дорабатывает только ограниченный набор сложных элементов.</div>}{isQwenSeed && <div className="notice">Этот режим нужен для разового наполнения обучающей выборки: Qwen3 14B формирует задания, банк обновляется, а пригодные результаты автоматически сохраняются как хорошие примеры.</div>}{isQwen8Seed && <div className="notice">Быстрый кандидат на замену 14B: используется локальный сервер Qwen3-8B на отдельном порту. Пригодные результаты автоматически попадают в хорошие примеры.</div>}{isQwenSmallSeed && <div className="notice">Максимально быстрый тест малой модели: Qwen2.5-3B или Qwen3-4B на отдельном порту. Если качество/JSON будет слабым, режим просто отключим.</div>}{isQwen35Seed && <div className="notice">Экспериментальный режим: используется локальный сервер Qwen3.5-9B на отдельном порту. Пригодные результаты также автоматически попадают в хорошие примеры.</div>}{!hasGoodExamples && generationMode !== 'template' && !QWEN_SEED_MODES.has(generationMode) && generationMode !== 'intelligent_v2' && <div className="notice">Если экспертных примеров мало, система автоматически использует безопасные шаблоны как резерв.</div>}</section>;
}

function GenerationSummary({ generation }) {
  return <section className="generationSummary"><strong>Результат последней генерации</strong><div className="itemBankStats"><span>Запрошенный режим: <strong>{generationModeLabel(generation.requested_mode)}</strong></span><span>Использованный режим: <strong>{generationModeLabel(generation.used_mode)}</strong></span><span>Интеллектуальный генератор: <strong>{generation.narrow_llm_generated_items || 0}</strong></span><span>По примерам: <strong>{generation.learned_generated_items || 0}</strong></span><span>По шаблонам: <strong>{generation.template_generated_items || 0}</strong></span>{generation.profiling?.auto_good_examples !== undefined && <span>Авто-good: <strong>{generation.profiling.auto_good_examples || 0}</strong></span>}{generation.model_version && <span>Версия модели: <strong>{generation.model_version}</strong></span>}</div><GenerationProfiling profiling={generation.profiling} />{generation.warnings?.length > 0 && <div className="notice"><ul>{generation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}</section>;
}

function GenerationProfiling({ profiling }) {
  if (!profiling || !profiling.total_ms) return null;
  const llm = profiling.local_llm || {};
  const stages = profiling.stages_ms || {};
  const llmLabel = llm.profile === 'qwen35_9b' ? 'Qwen3.5-9B' : llm.profile === 'qwen3_8b' ? 'Qwen3-8B' : llm.profile === 'qwen_small' ? 'Qwen Small' : 'Qwen3 14B';
  return <div className="generationProfiling"><strong>Профилирование генерации</strong><div className="itemBankStats"><span>Всего: <strong>{formatMs(profiling.total_ms)}</strong></span><span>Context-builder: <strong>{formatMs(stages.context_generator)}</strong></span><span>Примеры/OM: <strong>{formatMs(stages.load_examples)}</strong></span><span>Интеллектуальный генератор: <strong>{formatMs(stages.narrow_or_example_generation)}</strong></span><span>{llmLabel}: <strong>{formatMs(stages.local_llm_refinement)}</strong></span><span>Сохранение: <strong>{formatMs(stages.persist_items)}</strong></span>{profiling.intelligent_v2_plan?.target_total && <span>План ОМ 2.0: <strong>{profiling.intelligent_v2_plan.target_total}</strong></span>}{profiling.intelligent_v2_llm_targets?.selected !== undefined && <span>LLM-цели: <strong>{profiling.intelligent_v2_llm_targets.selected}</strong></span>}{stages.save_good_training_examples !== undefined && <span>Сохранение good: <strong>{formatMs(stages.save_good_training_examples)}</strong></span>}</div><div className="itemBankStats"><span>LLM профиль: <strong>{llm.profile || 'default'}</strong></span><span>Модель: <strong>{llm.model || '—'}</strong></span><span>Запросов: <strong>{llm.calls || 0}</strong></span><span>Средний запрос: <strong>{formatMs(llm.avg_call_ms)}</strong></span><span>Улучшено: <strong>{llm.refined_items || 0}</strong></span><span>Ошибок/отклонено: <strong>{llm.failed_items || 0}</strong></span></div>{llm.call_ms?.length > 0 && <p className="muted">Время запросов {llmLabel}: {llm.call_ms.map(formatMs).join(' · ')}</p>}</div>;
}

function ValidationDashboard({ validation, sectionMap }) {
  return <section className="itemValidation"><div className="diagnosticsGrid"><Metric value={validation.total_items} label="Всего заданий" /><Metric value={`${validation.topics_coverage_score}%`} label="Покрытие тем" /><Metric value={`${validation.competencies_coverage_score}%`} label="Покрытие компетенций" /><Metric value={`${validation.answers_readiness_score}%`} label="Готовность ответов" /><Metric value={`${validation.criteria_readiness_score}%`} label="Готовность критериев" /><Metric value={`${validation.duplicate_rate}%`} label="Сильные дубли" /></div>{validation.warnings?.length > 0 && <div className="notice"><strong>Результаты проверки банка</strong><ul>{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}<div className="coverageTableWrap"><h3>Матрица покрытия тем</h3><table className="coverageTable"><thead><tr><th>Тема</th><th>Всего заданий</th><th>Разделы</th><th>Компетенции</th></tr></thead><tbody>{validation.coverage_rows.map((row) => <tr key={row.topic}><td>{row.topic}</td><td>{row.total_items}</td><td>{Object.entries(row.section_counts).map(([code, count]) => `${sectionMap[code] || code}: ${count}`).join('; ') || '—'}</td><td>{row.competencies.join(', ') || '—'}</td></tr>)}</tbody></table></div></section>;
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

function successMessage(usedMode) {
  if (usedMode === 'intelligent_v2') return 'Интеллектуальный генератор 2.0 сформировал полный OM/ФОС-профиль и точечно доработал сложные задания.';
  if (usedMode === 'qwen_small_seed_good') return 'Qwen Small генерация завершена: пригодные задания добавлены в банк и сохранены как хорошие примеры.';
  if (usedMode === 'qwen8_seed_good') return 'Qwen3-8B генерация завершена: пригодные задания добавлены в банк и сохранены как хорошие примеры.';
  if (usedMode === 'qwen35_seed_good') return 'Qwen3.5-9B генерация завершена: пригодные задания добавлены в банк и сохранены как хорошие примеры.';
  if (usedMode === 'qwen_seed_good') return 'Qwen3 14B генерация завершена: пригодные задания добавлены в банк и сохранены как хорошие примеры.';
  if (usedMode === 'narrow_llm') return 'Банк заданий сформирован интеллектуальным генератором ФОС.';
  if (usedMode === 'learned') return 'Банк заданий сформирован на основе обучающей выборки.';
  if (usedMode === 'hybrid') return 'Банк заданий сформирован гибридно: интеллектуальный генератор + контекстный модуль.';
  return 'Банк заданий сформирован контекстным генератором и проверен антидублем.';
}

function generationModeLabel(value) {
  return ({
    intelligent_v2: 'Интеллектуальный генератор 2.0',
    narrow_llm: 'Интеллектуальный генератор ФОС',
    trained_narrow_llm: 'Интеллектуальный генератор ФОС',
    hybrid: 'Интеллектуальный генератор + резерв',
    learned: 'По экспертным примерам',
    template: 'Базовый шаблонный режим',
    qwen_seed_good: 'Qwen3 14B обучающая генерация',
    qwen8_seed_good: 'Qwen3 8B обучающая генерация',
    qwen_small_seed_good: 'Qwen Small обучающая генерация',
    qwen35_seed_good: 'Qwen3.5 9B обучающая генерация',
  }[value] || value || '—');
}

function formatMs(value) {
  const ms = Number(value || 0);
  if (!ms) return '0 мс';
  if (ms < 1000) return `${ms} мс`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} с`;
}

function sourceKindLabel(value) {
  return ({
    template: 'шаблон',
    smart_template: 'умный шаблон',
    smart_builder: 'smart-builder',
    knowledge_context: 'context-module',
    local_llm_qwen3: 'Qwen3-refiner',
    local_llm_qwen3_v2: 'Qwen3 14B-v2',
    local_llm_qwen8: 'Qwen3-8B-refiner',
    local_llm_qwen_small: 'Qwen Small-refiner',
    local_llm_qwen35: 'Qwen3.5-refiner',
    qwen_seed_good: 'Qwen3-good',
    qwen8_seed_good: 'Qwen3-8B-good',
    qwen_small_seed_good: 'Qwen Small-good',
    qwen35_seed_good: 'Qwen3.5-good',
    learned_example: 'по экспертному примеру',
    om_reference: 'OM/ФОС',
    narrow_llm: 'интеллектуальный ФОС',
    trained_narrow_llm: 'интеллектуальный ФОС',
  }[value] || value || 'шаблон');
}

function sourceKindClass(value) {
  return ({
    local_llm_qwen3: 'sourceQwen',
    local_llm_qwen3_v2: 'sourceQwen',
    local_llm_qwen8: 'sourceQwen',
    local_llm_qwen_small: 'sourceQwen',
    local_llm_qwen35: 'sourceQwen',
    qwen_seed_good: 'sourceQwen',
    qwen8_seed_good: 'sourceQwen',
    qwen_small_seed_good: 'sourceQwen',
    qwen35_seed_good: 'sourceQwen',
    knowledge_context: 'sourceKnowledge',
    smart_builder: 'sourceSmart',
    smart_template: 'sourceSmart',
    trained_narrow_llm: 'sourceNarrow',
    narrow_llm: 'sourceNarrow',
    om_reference: 'sourceNarrow',
    learned_example: 'sourceLearned',
  }[value] || 'sourceTemplate');
}

function SourceBadge({ kind }) {
  return <span className={`sourceBadge ${sourceKindClass(kind)}`}>{sourceKindLabel(kind)}</span>;
}

function shortSourceContext(value) {
  if (!value) return 'контекст не указан';
  return value.length > 110 ? `${value.slice(0, 110)}...` : value;
}

function assessmentTypeLabel(value) {
  return ({
    oral: 'устный опрос',
    practice: 'практика',
    exam_questions: 'экзамен',
    exam_practice: 'экзамен-практика',
    diagnostic: 'диагностика',
    control_work: 'контрольная',
    coursework: 'курсовая',
    course_project: 'курсовой проект',
    laboratory: 'лабораторная',
    test_bank: 'тест',
    report_topics: 'реферат/доклад',
    credit: 'зачет',
    credit_practice: 'зачет-практика',
  }[value] || value);
}

function difficultyLabel(value) {
  return ({ easy: 'базовая', medium: 'средняя', hard: 'повышенная' }[value] || value);
}

function Metric({ value, label }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

export default AssessmentItemBank;
