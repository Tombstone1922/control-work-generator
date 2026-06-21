import React, { useEffect, useMemo, useState } from 'react';

function AssessmentItemBank({ api, fund, sections, setError, setSuccess, onFundRefresh }) {
  const [items, setItems] = useState([]);
  const [validation, setValidation] = useState(null);
  const [trainingStats, setTrainingStats] = useState(null);
  const [generationSummary, setGenerationSummary] = useState(null);
  const [localLlmStatus, setLocalLlmStatus] = useState(null);
  const [isCheckingLlm, setCheckingLlm] = useState(false);
  const [selectedSectionCode, setSelectedSectionCode] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [teacherComment, setTeacherComment] = useState('');
  const [generationMode, setGenerationMode] = useState('template');
  const [learnedMaxItems, setLearnedMaxItems] = useState(12);
  const [narrowMaxItems, setNarrowMaxItems] = useState(12);
  const [fallbackToTemplate, setFallbackToTemplate] = useState(true);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [maxItemsPerSection, setMaxItemsPerSection] = useState(20);
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
  const visibleItems = useMemo(
    () => selectedSectionCode ? items.filter((item) => item.section_code === selectedSectionCode) : items,
    [items, selectedSectionCode],
  );
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
    loadItems();
    loadTrainingStats();
    loadLocalLlmStatus(false);
  }, [fund?.fund_id]);

  useEffect(() => setTeacherComment(''), [selectedItemId]);

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

  async function loadLocalLlmStatus(showSuccess = true) {
    setCheckingLlm(true);
    try {
      const response = await api.get('/api/local-llm/status');
      setLocalLlmStatus(response.data);
      if (showSuccess) {
        setSuccess(response.data.available ? 'Локальная LLM доступна.' : 'Локальная LLM пока недоступна. Проверьте llama-server и .env.');
      }
    } catch (err) {
      setLocalLlmStatus(null);
      if (showSuccess) setError(err.response?.data?.detail || 'Не удалось проверить локальную LLM.');
    } finally {
      setCheckingLlm(false);
    }
  }

  async function testLocalLlm() {
    setCheckingLlm(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post('/api/local-llm/test');
      if (response.data.ok) {
        setSuccess('Qwen3 вернула тестовое задание в JSON. Интеграция работает.');
      } else {
        setError(response.data.error || 'Локальная LLM не прошла тест.');
      }
      await loadLocalLlmStatus(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось выполнить тест локальной LLM.');
    } finally {
      setCheckingLlm(false);
    }
  }

  async function generateItems() {
    if (!fund?.fund_id) return;
    setGenerating(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post(`/api/assessment-items/${fund.fund_id}/generate`, {
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
      await loadLocalLlmStatus(false);
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
    if (!fund?.fund_id) return;
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
    if (!selectedItem) return;
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
    setItems((current) => current.map((item) => item.id === selectedItemId ? { ...item, ...patch } : item));
  }

  async function saveSelectedItem() {
    if (!selectedItem) return;
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
      setSuccess('Задание сохранено. Теперь его можно добавить в обучающую выборку.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить задание.');
    } finally {
      setSaving(false);
    }
  }

  async function deleteSelectedItem() {
    if (!selectedItem) return;
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
          <h3>Банк заданий ФОС</h3>
          <p className="muted">Формируйте задания, редактируйте их экспертно и сохраняйте хорошие/плохие примеры для обучения узкой модели ФОС.</p>
        </div>
        <div className="actionGroup">
          <button className="secondary" type="button" onClick={() => loadItems(selectedSectionCode)} disabled={isLoading}>{isLoading ? 'Обновляем...' : 'Обновить банк'}</button>
          <button className="secondary" type="button" onClick={() => validateItems()} disabled={isValidating}>{isValidating ? 'Проверяем...' : 'Проверить банк'}</button>
          <button className="download" type="button" onClick={downloadAssessmentFund} disabled={isExporting}>{isExporting ? 'Формируем DOCX...' : 'Скачать полный ФОС'}</button>
        </div>
      </div>

      <div className="itemBankHero">
        <div>
          <span className="eyebrow">Контур генерации</span>
          <h3>РПД → база знаний → антидубли → локальная Qwen3</h3>
          <p className="muted">Система сначала строит предметный контекст, затем улучшает формулировки через локальную LLM и повторно проверяет банк заданий.</p>
        </div>
        <div className="sourceMiniStats">
          {Object.entries(sourceStats).length ? Object.entries(sourceStats).map(([kind, count]) => <span key={kind}><SourceBadge kind={kind} /> <strong>{count}</strong></span>) : <span className="muted">Источники появятся после генерации.</span>}
        </div>
      </div>

      <TrainingDatasetPanel stats={trainingStats} downloadTrainingDataset={downloadTrainingDataset} isExportingDataset={isExportingDataset} />
      <LocalLlmPanel status={localLlmStatus} isChecking={isCheckingLlm} refreshStatus={() => loadLocalLlmStatus(true)} testLocalLlm={testLocalLlm} />
      <LearningModePanel generationMode={generationMode} setGenerationMode={setGenerationMode} learnedMaxItems={learnedMaxItems} setLearnedMaxItems={setLearnedMaxItems} narrowMaxItems={narrowMaxItems} setNarrowMaxItems={setNarrowMaxItems} fallbackToTemplate={fallbackToTemplate} setFallbackToTemplate={setFallbackToTemplate} stats={trainingStats} />
      {generationSummary && <GenerationSummary generation={generationSummary} />}

      <div className="itemBankToolbar">
        <label>Раздел ФОС<select value={selectedSectionCode} onChange={(event) => setSelectedSectionCode(event.target.value)}><option value="">Все активные разделы</option>{enabledSections.map((section) => <option key={section.code} value={section.code}>{section.title}</option>)}</select></label>
        <label>Максимум заданий на раздел<input type="number" min="1" max="200" value={maxItemsPerSection} onChange={(event) => setMaxItemsPerSection(Number(event.target.value))} /></label>
        <label className="toggleLabel itemBankCheckbox"><input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />Заменить старые задания</label>
        <button className="primary" type="button" onClick={generateItems} disabled={isGenerating || !enabledSections.length}>{isGenerating ? 'Формируем...' : 'Сформировать задания'}</button>
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
              <div className="questionTopline"><div><h3>Редактор задания</h3><SourceBadge kind={selectedItem.source_kind} /></div><div className="actionGroup"><button className="danger" type="button" onClick={deleteSelectedItem}>Удалить</button><button className="primary" type="button" onClick={saveSelectedItem} disabled={isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить'}</button></div></div>
              <label>Формулировка<textarea value={selectedItem.text} onChange={(event) => patchSelectedItem({ text: event.target.value })} /></label>
              <label>Эталонный ответ<textarea value={selectedItem.answer} onChange={(event) => patchSelectedItem({ answer: event.target.value })} /></label>
              <div className="miniGrid"><label>Тема<input value={selectedItem.topic} onChange={(event) => patchSelectedItem({ topic: event.target.value })} /></label><label>Компетенция<input value={selectedItem.competency_code} onChange={(event) => patchSelectedItem({ competency_code: event.target.value })} /></label><label>Сложность<select value={selectedItem.difficulty} onChange={(event) => patchSelectedItem({ difficulty: event.target.value })}><option value="easy">Базовая</option><option value="medium">Средняя</option><option value="hard">Повышенная</option></select></label></div>
              <label>Индикатор<textarea value={selectedItem.indicator} onChange={(event) => patchSelectedItem({ indicator: event.target.value })} /></label>
              <label>Критерии оценивания<textarea value={selectedItem.criteria.join('\n')} onChange={(event) => patchSelectedItem({ criteria: event.target.value.split('\n').filter(Boolean) })} /></label>
              <div className="sourceContextBox"><strong>Источник формирования</strong><p>{selectedItem.source_context || 'не указан'}</p></div>
              <section className="trainingFeedback"><h3>Экспертная разметка для самообучения</h3><p className="muted">После ручной правки сохраните задание как хороший пример, плохой пример или пример, требующий доработки.</p><label>Комментарий преподавателя<textarea value={teacherComment} onChange={(event) => setTeacherComment(event.target.value)} /></label><div className="actionGroup trainingActions"><button className="secondary" type="button" onClick={() => addTrainingExample('needs_revision')} disabled={isTraining}>Нужно доработать</button><button className="danger" type="button" onClick={() => addTrainingExample('bad')} disabled={isTraining}>Плохой пример</button><button className="primary" type="button" onClick={() => addTrainingExample('good')} disabled={isTraining}>Хороший пример</button></div></section>
            </>
          ) : <p className="muted">Выберите задание слева.</p>}
        </div>
      </div>
    </section>
  );
}

function TrainingDatasetPanel({ stats, downloadTrainingDataset, isExportingDataset }) {
  return <section className="trainingDatasetPanel"><div><h3>Обучающая выборка</h3><p className="muted">Здесь накапливаются экспертно подтвержденные примеры для будущего дообучения узкой модели.</p></div><div className="itemBankStats"><span>Всего: <strong>{stats?.total_examples || 0}</strong></span><span>Хороших: <strong>{stats?.good_examples || 0}</strong></span><span>Плохих: <strong>{stats?.bad_examples || 0}</strong></span><span>На доработку: <strong>{stats?.revision_examples || 0}</strong></span><span>Тем: <strong>{stats?.topics_count || 0}</strong></span><span>Компетенций: <strong>{stats?.competencies_count || 0}</strong></span></div><button className="download" type="button" onClick={downloadTrainingDataset} disabled={isExportingDataset}>{isExportingDataset ? 'Экспортируем...' : 'Скачать JSONL датасет'}</button></section>;
}

function LocalLlmPanel({ status, isChecking, refreshStatus, testLocalLlm }) {
  const healthClass = status?.available ? 'llmReady' : status?.enabled ? 'llmWarning' : 'llmDisabled';
  const title = status?.available ? 'Qwen3 подключена' : status?.enabled ? 'Qwen3 включена, но недоступна' : 'Локальная LLM выключена';
  return <section className={`localLlmPanel ${healthClass}`}><div><span className="eyebrow">Локальная LLM</span><h3>{title}</h3><p className="muted">{status?.enabled ? `${status.base_url || ''} · ${status.model || ''}` : 'Включите LOCAL_LLM_ENABLED=true в backend/.env после запуска llama-server.'}</p>{status?.latency_ms !== null && status?.latency_ms !== undefined && <small>Задержка ответа: {status.latency_ms} мс</small>}{status?.error && <small>{status.error}</small>}</div><div className="actionGroup"><button className="secondary" type="button" onClick={refreshStatus} disabled={isChecking}>{isChecking ? 'Проверяем...' : 'Проверить статус'}</button><button className="primary" type="button" onClick={testLocalLlm} disabled={isChecking || !status?.enabled}>{isChecking ? 'Тестируем...' : 'Тест JSON'}</button></div></section>;
}

function LearningModePanel({ generationMode, setGenerationMode, learnedMaxItems, setLearnedMaxItems, narrowMaxItems, setNarrowMaxItems, fallbackToTemplate, setFallbackToTemplate, stats }) {
  const hasGoodExamples = (stats?.good_examples || 0) > 0;
  return <section className="learningModePanel"><div><h3>Генерация с учетом обучающей выборки</h3><p className="muted">Узкая модель ФОС использует хорошие экспертные примеры. Локальная Qwen3, если включена, работает сверху как методист-редактор формулировок.</p></div><div className="learningModeGrid"><label>Режим генерации<select value={generationMode} onChange={(event) => setGenerationMode(event.target.value)}><option value="template">Шаблонный генератор</option><option value="learned">По экспертным примерам</option><option value="narrow_llm">Узкая модель ФОС</option><option value="hybrid">Гибрид: узкая модель + шаблоны</option></select></label><label>Заданий по экспертным примерам<input type="number" min="1" max="200" value={learnedMaxItems} onChange={(event) => setLearnedMaxItems(Number(event.target.value))} disabled={generationMode !== 'learned'} /></label><label>Заданий узкой моделью<input type="number" min="1" max="200" value={narrowMaxItems} onChange={(event) => setNarrowMaxItems(Number(event.target.value))} disabled={generationMode !== 'hybrid'} /></label><label className="toggleLabel itemBankCheckbox"><input type="checkbox" checked={fallbackToTemplate} onChange={(event) => setFallbackToTemplate(event.target.checked)} />Если примеров мало — использовать шаблоны</label></div>{!hasGoodExamples && generationMode !== 'template' && <div className="notice">Для режимов на обучающей выборке нужен хотя бы один пример с меткой “Хороший пример”.</div>}</section>;
}

function GenerationSummary({ generation }) {
  return <section className="generationSummary"><strong>Результат последней генерации</strong><div className="itemBankStats"><span>Запрошенный режим: <strong>{generation.requested_mode}</strong></span><span>Использованный режим: <strong>{generation.used_mode}</strong></span><span>Узкая модель: <strong>{generation.narrow_llm_generated_items || 0}</strong></span><span>По примерам: <strong>{generation.learned_generated_items || 0}</strong></span><span>По шаблонам: <strong>{generation.template_generated_items || 0}</strong></span>{generation.model_version && <span>Версия модели: <strong>{generation.model_version}</strong></span>}</div>{generation.warnings?.length > 0 && <div className="notice"><ul>{generation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}</section>;
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
  if (usedMode === 'narrow_llm') return 'Банк заданий сформирован узкой моделью ФОС на экспертных примерах.';
  if (usedMode === 'learned') return 'Банк заданий сформирован на основе обучающей выборки.';
  if (usedMode === 'hybrid') return 'Банк заданий сформирован гибридно: узкая модель/примеры + шаблоны.';
  return 'Банк заданий сформирован контекстным генератором. Если Qwen3 включена, она улучшила часть формулировок.';
}

function sourceKindLabel(value) {
  return ({
    template: 'шаблон',
    smart_template: 'умный шаблон',
    smart_builder: 'smart-builder',
    knowledge_context: 'база знаний',
    local_llm_qwen3: 'Qwen3 local',
    learned_example: 'по экспертному примеру',
    narrow_llm: 'узкая модель ФОС',
    trained_narrow_llm: 'обученная узкая модель',
  }[value] || value || 'шаблон');
}

function sourceKindClass(value) {
  return ({
    local_llm_qwen3: 'sourceQwen',
    knowledge_context: 'sourceKnowledge',
    smart_builder: 'sourceSmart',
    smart_template: 'sourceSmart',
    trained_narrow_llm: 'sourceNarrow',
    narrow_llm: 'sourceNarrow',
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
  }[value] || value);
}

function difficultyLabel(value) {
  return ({ easy: 'базовая', medium: 'средняя', hard: 'повышенная' }[value] || value);
}

function Metric({ value, label }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

export default AssessmentItemBank;
