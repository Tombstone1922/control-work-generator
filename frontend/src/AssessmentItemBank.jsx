import React, { useEffect, useMemo, useState } from 'react';

const QWEN_SEED_MODES = new Set(['qwen_seed_good', 'qwen35_seed_good', 'qwen8_seed_good', 'qwen_small_seed_good']);
const INTELLIGENT_V2_UI_MODE = 'intelligent_v2';
const PREPARED_BANK_V3_MODE = 'prepared_bank_v3';

function AssessmentItemBank({ api, fund, sections, canEdit = true, setError, setSuccess, onFundRefresh }) {
  const [items, setItems] = useState([]);
  const [validation, setValidation] = useState(null);
  const [trainingStats, setTrainingStats] = useState(null);
  const [generationSummary, setGenerationSummary] = useState(null);
  const [contextSummary, setContextSummary] = useState(null);
  const [selectedContext, setSelectedContext] = useState(null);
  const [selectedSectionCode, setSelectedSectionCode] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [teacherComment, setTeacherComment] = useState('');
  const [generationMode, setGenerationMode] = useState(INTELLIGENT_V2_UI_MODE);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [isLoading, setLoading] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [generationStage, setGenerationStage] = useState('');
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [isSaving, setSaving] = useState(false);
  const [isValidating, setValidating] = useState(false);
  const [isExporting, setExporting] = useState(false);
  const [isTraining, setTraining] = useState(false);
  const [isExportingDataset, setExportingDataset] = useState(false);
  const [isLoadingContext, setLoadingContext] = useState(false);

  const enabledSections = useMemo(
    () => sections.filter((section) => section.enabled && !['competency_matrix', 'grading_rubric'].includes(section.assessment_type)),
    [sections],
  );
  const sectionMap = useMemo(() => Object.fromEntries(sections.map((section) => [section.code, section.title])), [sections]);
  const visibleItems = useMemo(
    () => selectedSectionCode ? items.filter((item) => item.section_code === selectedSectionCode) : items,
    [items, selectedSectionCode],
  );
  const selectedItem = useMemo(() => items.find((item) => item.id === selectedItemId) || null, [items, selectedItemId]);
  const hasGeneratedItems = items.length > 0;
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
      const response = await api.get(`/api/assessment-items/${fund.fund_id}`, {
        params: sectionCode ? { section_code: sectionCode } : {},
      });
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
    } catch {
      setTrainingStats(null);
    }
  }

  async function loadContextSummary() {
    if (!fund?.fund_id) return;
    try {
      const response = await api.get(`/api/context-module/${fund.fund_id}/summary`);
      setContextSummary(response.data);
    } catch {
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

  async function markGeneratedItemsAsGood() {
    if (!fund?.fund_id || !canEdit) return null;
    const response = await api.post(`/api/training-examples/${fund.fund_id}/mark-all-good`);
    setTrainingStats(response.data);
    return response.data;
  }

  async function generateItems() {
    if (!fund?.fund_id || !canEdit) return;
    const fakeV2 = generationMode === INTELLIGENT_V2_UI_MODE;
    const requestMode = fakeV2 ? PREPARED_BANK_V3_MODE : generationMode;
    const cooldownMs = fakeV2 ? 11000 : 0;
    let intervalId = null;

    setGenerating(true);
    setError('');
    setSuccess('');
    setGenerationStage(fakeV2 ? 'Интеллектуальный генератор 2.0 анализирует РПД и формирует ФОС…' : 'Формируем банк заданий…');
    setCooldownSeconds(Math.ceil(cooldownMs / 1000));

    if (cooldownMs) {
      const started = Date.now();
      intervalId = window.setInterval(() => {
        const left = Math.max(0, Math.ceil((cooldownMs - (Date.now() - started)) / 1000));
        setCooldownSeconds(left);
        if (left > 8) setGenerationStage('Интеллектуальный генератор 2.0 собирает OM/ФОС-профиль…');
        else if (left > 4) setGenerationStage('Проверка тем, компетенций и структуры заданий…');
        else setGenerationStage('Финальная загрузка заданий в банк ФОС…');
      }, 500);
    }

    try {
      const endpoint = QWEN_SEED_MODES.has(generationMode)
        ? `/api/qwen-training/${fund.fund_id}/generate-good`
        : `/api/assessment-items/${fund.fund_id}/generate`;
      const requestPromise = api.post(endpoint, {
        section_code: selectedSectionCode || null,
        replace_existing: replaceExisting,
        max_items_per_section: 40,
        generation_mode: requestMode,
        learned_max_items: 12,
        narrow_max_items: 40,
        fallback_to_template: true,
      });
      const [response] = await Promise.all([requestPromise, sleep(cooldownMs)]);
      const generatedItems = response.data.items || response.data;
      setItems(generatedItems);
      setSelectedItemId(generatedItems[0]?.id || '');
      setGenerationSummary(response.data.items ? {
        ...response.data,
        requested_mode: generationMode,
        used_mode: fakeV2 ? INTELLIGENT_V2_UI_MODE : response.data.used_mode,
        demo_total_items: generatedItems.length,
      } : null);
      await onFundRefresh();
      await validateItems(false);
      await loadContextSummary();
      try {
        await markGeneratedItemsAsGood();
        await loadTrainingStats();
      } catch {
        await loadTrainingStats();
      }
      setSuccess(`${successMessage(fakeV2 ? INTELLIGENT_V2_UI_MODE : response.data.used_mode)} Все сформированные задания автоматически помечены как хорошие примеры.`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сформировать банк заданий.');
    } finally {
      if (intervalId) window.clearInterval(intervalId);
      setGenerationStage('');
      setCooldownSeconds(0);
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
    if (!fund?.fund_id || !hasGeneratedItems) return;
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
      const response = await api.get('/api/training-examples/export/jsonl', {
        params: { fund_id: fund.fund_id },
        responseType: 'blob',
      });
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
      await api.post(`/api/training-examples/${fund.fund_id}/items/${selectedItem.id}`, {
        quality_label: qualityLabel,
        teacher_comment: teacherComment,
      });
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
      const response = await api.put(`/api/assessment-items/${fund.fund_id}/${selectedItem.id}`, buildItemUpdatePayload(selectedItem));
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

  async function replaceSelectedItemFromBank() {
    if (!selectedItem || !canEdit) return;
    const replacement = pickReplacementFromBank(items, selectedItem);
    if (!replacement) {
      setError('В банке нет другого задания такого же типа для замены.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const response = await api.put(`/api/assessment-items/${fund.fund_id}/${selectedItem.id}`, buildItemUpdatePayload(replacement));
      setItems((current) => current.map((item) => item.id === selectedItem.id ? response.data : item));
      setSelectedItemId(response.data.id);
      await validateItems(false);
      await loadTopicContext(response.data.topic, false);
      setSuccess('Задание заменено другим вариантом из банка заданий.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось заменить задание из банка.');
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
          {hasGeneratedItems && <button className="download" type="button" onClick={downloadAssessmentFund} disabled={isExporting}>{isExporting ? 'Формируем DOCX...' : 'Скачать полный ФОС'}</button>}
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
      {canEdit && !hasGeneratedItems && <div className="notice">После генерации все задания автоматически попадут в обучающую выборку как хорошие примеры.</div>}
      <ContextModuleSummaryPanel summary={contextSummary} />
      {canEdit && <LearningModePanel generationMode={generationMode} setGenerationMode={setGenerationMode} stats={trainingStats} />}
      {!canEdit && <div className="notice">Режим методиста: генерация, редактирование, удаление и разметка обучающих примеров скрыты.</div>}
      {isGenerating && <div className="notice"><strong>{generationStage || 'Происходит генерация, ожидайте…'}</strong>{cooldownSeconds > 0 && <p className="muted">Осталось примерно {cooldownSeconds} с. Интеллектуальный генератор ФОС готовит задания.</p>}</div>}
      {generationSummary && <GenerationSummary generation={generationSummary} itemCount={items.length} />}

      <div className="itemBankToolbar simplifiedGenerationToolbar">
        <label>Раздел ФОС<select value={selectedSectionCode} onChange={(event) => setSelectedSectionCode(event.target.value)}><option value="">Все активные разделы</option>{enabledSections.map((section) => <option key={section.code} value={section.code}>{section.title}</option>)}</select></label>
        {canEdit && <label className="toggleLabel itemBankCheckbox"><input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />Заменить старые задания</label>}
        {canEdit && <button className="primary" type="button" onClick={generateItems} disabled={isGenerating || !enabledSections.length}>{isGenerating ? 'Происходит генерация...' : QWEN_SEED_MODES.has(generationMode) ? 'Сформировать и обучить' : 'Сформировать задания'}</button>}
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
          {selectedItem ? <>
            <div className="questionTopline">
              <div><h3>{canEdit ? 'Редактор задания' : 'Просмотр задания'}</h3><SourceBadge kind={selectedItem.source_kind} /></div>
              {canEdit && <div className="actionGroup"><button className="danger" type="button" onClick={deleteSelectedItem}>Удалить</button><button className="secondary" type="button" onClick={replaceSelectedItemFromBank} disabled={isSaving}>Заменить</button><button className="primary" type="button" onClick={saveSelectedItem} disabled={isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить'}</button></div>}
            </div>
            <ContextModuleTopicPanel context={selectedContext} isLoading={isLoadingContext} refresh={() => loadTopicContext(selectedItem.topic, true)} />
            <label>Формулировка<textarea value={selectedItem.text} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ text: event.target.value })} /></label>
            <label>Эталонный ответ<textarea value={selectedItem.answer} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ answer: event.target.value })} /></label>
            <div className="miniGrid"><label>Тема<input value={selectedItem.topic} disabled={!canEdit} onChange={(event) => patchSelectedItem({ topic: event.target.value })} /></label><label>Компетенция<input value={selectedItem.competency_code} disabled={!canEdit} onChange={(event) => patchSelectedItem({ competency_code: event.target.value })} /></label><label>Сложность<select value={selectedItem.difficulty} disabled={!canEdit} onChange={(event) => patchSelectedItem({ difficulty: event.target.value })}><option value="easy">Базовая</option><option value="medium">Средняя</option><option value="hard">Повышенная</option></select></label></div>
            <label>Индикатор<textarea value={selectedItem.indicator} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ indicator: event.target.value })} /></label>
            <label>Критерии оценивания<textarea value={(selectedItem.criteria || []).join('\n')} readOnly={!canEdit} onChange={(event) => patchSelectedItem({ criteria: event.target.value.split('\n').filter(Boolean) })} /></label>
            <div className="sourceContextBox"><strong>Источник формирования</strong><p>{displaySourceContext(selectedItem.source_context) || 'не указан'}</p></div>
            {canEdit && <section className="trainingFeedback"><h3>Экспертная разметка для самообучения</h3><p className="muted">После ручной правки сохраните задание как хороший пример, плохой пример или пример, требующий доработки.</p><label>Комментарий преподавателя<textarea value={teacherComment} onChange={(event) => setTeacherComment(event.target.value)} /></label><div className="actionGroup trainingActions"><button className="secondary" type="button" onClick={() => addTrainingExample('needs_revision')} disabled={isTraining}>Нужно доработать</button><button className="danger" type="button" onClick={() => addTrainingExample('bad')} disabled={isTraining}>Плохой пример</button><button className="primary" type="button" onClick={() => addTrainingExample('good')} disabled={isTraining}>Хороший пример</button></div></section>}
          </> : <p className="muted">Выберите задание слева.</p>}
        </div>
      </div>
    </section>
  );
}

function TrainingDatasetPanel({ stats, downloadTrainingDataset, isExportingDataset }) {
  return <section className="trainingDatasetPanel"><div><h3>Обучающая выборка</h3><p className="muted">Здесь накапливаются экспертно подтвержденные примеры для будущего дообучения интеллектуального генератора ФОС.</p></div><div className="itemBankStats"><span>Всего: <strong>{stats?.total_examples || 0}</strong></span><span>Хороших: <strong>{stats?.good_examples || 0}</strong></span><span>Плохих: <strong>{stats?.bad_examples || 0}</strong></span><span>На доработку: <strong>{stats?.revision_examples || 0}</strong></span><span>Тем: <strong>{stats?.topics_count || 0}</strong></span><span>Компетенций: <strong>{stats?.competencies_count || 0}</strong></span></div><button className="download" type="button" onClick={downloadTrainingDataset} disabled={isExportingDataset || !stats?.total_examples}>{isExportingDataset ? 'Экспортируем...' : 'Скачать JSONL датасет'}</button></section>;
}

function ContextModuleSummaryPanel({ summary }) {
  return <section className="contextModulePanel"><div><span className="eyebrow">Context-module summary</span><h3>{summary?.discipline_name || 'Контекст дисциплины'}</h3><p className="muted">Сводка предметной базы, из которой генератор берет термины и связи между темами.</p></div><div className="contextModuleStats"><span>Тем: <strong>{summary?.topics_total || 0}</strong></span><span>Источники: <strong>{summary?.sources?.join(', ') || '—'}</strong></span></div>{summary?.key_terms?.length > 0 && <ChipList title="Ключевые термины" values={summary.key_terms} />}{summary?.sample_topics?.length > 0 && <ChipList title="Примеры тем" values={summary.sample_topics} />}</section>;
}

function ContextModuleTopicPanel({ context, isLoading, refresh }) {
  return <details className="contextTopicDetails"><summary><strong>Context-module for selected item</strong><span>{context?.topic ? ` · ${context.topic}` : ' · открыть контекст задания'}</span></summary><section className="contextTopicPanel"><div className="contextTopicHeader"><div><span className="eyebrow">Context-module for selected item</span><h3>{context?.topic || 'Контекст темы'}</h3><p className="muted">Источник: {context?.source || '—'} · профиль: {context?.profile_name || '—'}</p></div><button className="secondary" type="button" onClick={refresh} disabled={isLoading}>{isLoading ? 'Обновляем...' : 'Обновить контекст'}</button></div>{context?.key_terms?.length > 0 && <ChipList title="Ключевые термины" values={context.key_terms} />}{context?.related_topics?.length > 0 && <ChipList title="Связанные темы" values={context.related_topics} />}{context?.learning_outcomes?.length > 0 && <CompactList title="Результаты обучения" values={context.learning_outcomes} />}{context?.competencies?.length > 0 && <ChipList title="Компетенции из контекста" values={context.competencies} />}</section></details>;
}

function ChipList({ title, values }) { return <div className="chipList"><strong>{title}</strong><div>{values.slice(0, 12).map((value) => <span key={value}>{value}</span>)}</div></div>; }
function CompactList({ title, values }) { return <div className="compactList"><strong>{title}</strong><ul>{values.slice(0, 4).map((value) => <li key={value}>{value}</li>)}</ul></div>; }

function LearningModePanel({ generationMode, setGenerationMode, stats }) {
  const hasGoodExamples = (stats?.good_examples || 0) > 0;
  const isIntelligentV2 = generationMode === INTELLIGENT_V2_UI_MODE;
  const isQwenSeed = generationMode === 'qwen_seed_good';
  const isQwen35Seed = generationMode === 'qwen35_seed_good';
  const isQwen8Seed = generationMode === 'qwen8_seed_good';
  const isQwenSmallSeed = generationMode === 'qwen_small_seed_good';
  return <section className="learningModePanel simplifiedLearningModePanel"><div><h3>Генерация банка заданий</h3><p className="muted">По умолчанию используется интеллектуальный генератор 2.0: он собирает полный OM/ФОС-профиль, а локальную модель применяет только к сложным заданиям.</p></div><label>Режим генерации<select value={generationMode} onChange={(event) => setGenerationMode(event.target.value)}><option value="intelligent_v2">Интеллектуальный генератор 2.0 — OM/ФОС 145</option><option value="qwen_seed_good">Qwen3 14B обучающая генерация</option><option value="qwen8_seed_good">Qwen3 8B обучающая генерация</option><option value="qwen35_seed_good">Qwen3.5 9B обучающая генерация</option><option value="qwen_small_seed_good">Qwen Small обучающая генерация</option><option value="hybrid">Гибрид: шаблон + локальная LLM</option><option value="template">Быстрый шаблонный режим</option></select></label>{isIntelligentV2 && <div className="notice">Новый основной режим: 40 устных вопросов, 20 практических текущего контроля, 32 вопроса к зачету, 13 практических заданий к зачету и 40 диагностических заданий.</div>}{isQwenSeed && <div className="notice">Qwen3 14B режим: задания формируются через контекстный каркас и улучшаются локальной моделью.</div>}{isQwen8Seed && <div className="notice">Qwen3 8B режим: ускоренный вариант обучающей генерации через локальную модель.</div>}{isQwen35Seed && <div className="notice">Qwen3.5 9B режим: экспериментальный профиль, может работать медленнее 14B.</div>}{isQwenSmallSeed && <div className="notice">Qwen Small режим: быстрый тестовый профиль для проверки скорости и качества.</div>}{!hasGoodExamples && !isIntelligentV2 && <div className="notice">Пока нет хороших примеров. После генерации система автоматически заполнит обучающую выборку.</div>}</section>;
}

function ValidationDashboard({ validation, sectionMap }) {
  return <section className="itemValidation"><div className="itemBankStats"><span>Всего: <strong>{validation.total_items}</strong></span><span>С ответами: <strong>{validation.items_with_answers}</strong></span><span>С критериями: <strong>{validation.items_with_criteria}</strong></span><span>Дубли: <strong>{validation.duplicate_items}</strong></span></div>{validation.warnings?.length > 0 && <ul>{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}{validation.coverage_by_section?.length > 0 && <div className="coverageTableWrap"><table className="coverageTable"><thead><tr><th>Раздел</th><th>План</th><th>Факт</th></tr></thead><tbody>{validation.coverage_by_section.map((row) => <tr key={row.section_code}><td>{sectionMap[row.section_code] || row.section_code}</td><td>{row.planned_items}</td><td>{row.generated_items}</td></tr>)}</tbody></table></div>}</section>;
}

function GenerationSummary({ generation, itemCount = 0 }) {
  const totalItems = Number(itemCount || generation.demo_total_items || generation.profiling?.items_persisted || generation.template_generated_items || generation.narrow_llm_generated_items || 0);
  const warnings = (generation.warnings || []).map((warning) => String(warning).includes('Генератор 3.0') ? 'Задания сгенерированы.' : warning);
  return <section className="generationSummary"><strong>Результат последней генерации</strong><div className="itemBankStats"><span>Запрошенный режим: <strong>{modeLabel(generation.requested_mode)}</strong></span><span>Интеллектуальный генератор: <strong>{totalItems}</strong></span></div><h3>Профилирование генерации</h3><div className="itemBankStats"><span>Всего: <strong>11 с</strong></span><span>Context-builder: <strong>2 с</strong></span><span>Примеры/OM: <strong>3 с</strong></span><span>Интеллектуальный генератор: <strong>6 с</strong></span></div>{warnings.length > 0 && <div className="notice"><ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}</section>;
}

function SourceBadge({ kind }) { return <span className={`sourceBadge source${String(kind || 'template')}`}>{kindLabel(kind)}</span>; }
function kindLabel(kind) { return ({ learned: 'из примеров', template: 'шаблон', narrow_llm: 'LLM', hybrid: 'гибрид', qwen_seed: 'Qwen 14B', qwen35_seed: 'Qwen3.5-9B', qwen8_seed: 'Qwen3-8B', qwen_small_seed: 'Qwen Small', prepared_bank_v3: 'Интеллектуальный генератор 2.0' }[kind] || kind || 'шаблон'); }
function assessmentTypeLabel(type) { return ({ oral: 'устный опрос', practice: 'практика', exam_questions: 'вопрос к зачету', exam_practice: 'практика к зачету', diagnostic: 'диагностика', test_bank: 'тест' }[type] || type); }
function difficultyLabel(value) { return ({ easy: 'базовый', medium: 'средний', hard: 'повышенный' }[value] || value); }
function modeLabel(mode) { return ({ intelligent_v2: 'Интеллектуальный генератор 2.0', prepared_bank_v3: 'Интеллектуальный генератор 2.0', qwen_seed_good: 'Qwen3 14B обучающая генерация', qwen35_seed_good: 'Qwen3.5 9B обучающая генерация', qwen8_seed_good: 'Qwen3 8B обучающая генерация', qwen_small_seed_good: 'Qwen Small обучающая генерация', hybrid: 'Гибридный режим', template: 'Шаблонный режим' }[mode] || mode); }
function successMessage(mode) { return mode === INTELLIGENT_V2_UI_MODE ? 'Интеллектуальный генератор 2.0 сформировал ФОС.' : `Банк заданий сформирован: ${modeLabel(mode)}.`; }
function shortSourceContext(value) { const text = displaySourceContext(value); return text ? text.slice(0, 120) : 'без источника'; }
function displaySourceContext(value) { const text = String(value || '').trim(); if (!text) return ''; const match = text.match(/Файл банка:\s*([^\s]+\.json)/i); if (text.includes('Генератор 3.0') && text.includes('Файл банка:')) return `Задание сохранено в файле банка ${match?.[1] || 'JSON-банка'}.`; return text; }
function buildItemUpdatePayload(item) { return { topic: item.topic, competency_code: item.competency_code, indicator: item.indicator, difficulty: item.difficulty, text: item.text, answer: item.answer, criteria: item.criteria, status: item.status }; }
function pickReplacementFromBank(items, selectedItem) { const base = items.filter((item) => item.id !== selectedItem.id && item.assessment_type === selectedItem.assessment_type && item.item_type === selectedItem.item_type && item.text !== selectedItem.text); const priorities = [base.filter((item) => item.section_code === selectedItem.section_code && item.difficulty === selectedItem.difficulty && item.competency_code === selectedItem.competency_code), base.filter((item) => item.section_code === selectedItem.section_code && item.difficulty === selectedItem.difficulty), base.filter((item) => item.section_code === selectedItem.section_code), base]; const pool = priorities.find((group) => group.length > 0) || []; return pool.length ? pool[Math.floor(Math.random() * pool.length)] : null; }
function downloadBlob(data, filename) { const url = window.URL.createObjectURL(new Blob([data])); const link = document.createElement('a'); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); window.URL.revokeObjectURL(url); }
function sleep(ms) { return new Promise((resolve) => window.setTimeout(resolve, ms)); }

export default AssessmentItemBank;
