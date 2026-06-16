import React, { useEffect, useMemo, useState } from 'react';

function AssessmentItemBank({ api, fund, sections, setError, setSuccess, onFundRefresh }) {
  const [items, setItems] = useState([]);
  const [validation, setValidation] = useState(null);
  const [trainingStats, setTrainingStats] = useState(null);
  const [selectedSectionCode, setSelectedSectionCode] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [teacherComment, setTeacherComment] = useState('');
  const [isLoading, setLoading] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isValidating, setValidating] = useState(false);
  const [isExporting, setExporting] = useState(false);
  const [isTraining, setTraining] = useState(false);
  const [isExportingDataset, setExportingDataset] = useState(false);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [maxItemsPerSection, setMaxItemsPerSection] = useState(20);

  const enabledSections = useMemo(
    () => sections.filter((section) => section.enabled && !['competency_matrix', 'grading_rubric'].includes(section.assessment_type)),
    [sections],
  );

  const sectionMap = useMemo(
    () => Object.fromEntries(sections.map((section) => [section.code, section.title])),
    [sections],
  );

  const visibleItems = useMemo(
    () => selectedSectionCode ? items.filter((item) => item.section_code === selectedSectionCode) : items,
    [items, selectedSectionCode],
  );

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) || null,
    [items, selectedItemId],
  );

  useEffect(() => {
    if (!fund?.fund_id) return;
    setSelectedSectionCode('');
    setSelectedItemId('');
    setValidation(null);
    setTeacherComment('');
    loadItems();
    loadTrainingStats();
  }, [fund?.fund_id]);

  useEffect(() => {
    setTeacherComment('');
  }, [selectedItemId]);

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
    } catch (err) {
      setTrainingStats(null);
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
        generation_mode: 'template',
        fallback_to_template: true,
      });
      const generatedItems = response.data.items || response.data;
      setItems(generatedItems);
      setSelectedItemId(generatedItems[0]?.id || '');
      await onFundRefresh();
      await validateItems(false);
      setSuccess('Банк заданий сформирован. После экспертной правки сохраняйте удачные и неудачные задания в обучающую выборку.');
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
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `fos_${fund.discipline_name || fund.fund_id}.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccess('DOCX-файл ФОС сформирован и скачан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сформировать DOCX-файл ФОС.');
    } finally {
      setExporting(false);
    }
  }

  async function addTrainingExample(qualityLabel) {
    if (!selectedItem) return;
    setTraining(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/api/training-examples/${fund.fund_id}/items/${selectedItem.id}`, {
        quality_label: qualityLabel,
        teacher_comment: teacherComment,
      });
      await loadTrainingStats();
      const label = qualityLabel === 'good' ? 'хороший пример' : qualityLabel === 'bad' ? 'плохой пример' : 'пример на доработку';
      setSuccess(`Задание сохранено в обучающую выборку как ${label}.`);
      setTeacherComment('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить обучающий пример.');
    } finally {
      setTraining(false);
    }
  }

  async function downloadTrainingDataset() {
    if (!fund?.fund_id) return;
    setExportingDataset(true);
    setError('');
    try {
      const response = await api.get('/api/training-examples/export/jsonl', {
        params: { fund_id: fund.fund_id },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `training_dataset_${fund.discipline_name || fund.fund_id}.jsonl`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccess('Обучающая выборка JSONL сформирована и скачана.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось экспортировать обучающую выборку.');
    } finally {
      setExportingDataset(false);
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
          <p className="muted">Формируйте задания, редактируйте их экспертно и сохраняйте хорошие/плохие примеры для последующего обучения модели.</p>
        </div>
        <div className="actionGroup">
          <button className="secondary" type="button" onClick={() => loadItems(selectedSectionCode)} disabled={isLoading}>
            {isLoading ? 'Обновляем...' : 'Обновить банк'}
          </button>
          <button className="secondary" type="button" onClick={() => validateItems()} disabled={isValidating}>
            {isValidating ? 'Проверяем...' : 'Проверить банк'}
          </button>
          <button className="download" type="button" onClick={downloadAssessmentFund} disabled={isExporting}>
            {isExporting ? 'Формируем DOCX...' : 'Скачать полный ФОС'}
          </button>
        </div>
      </div>

      <TrainingDatasetPanel
        stats={trainingStats}
        downloadTrainingDataset={downloadTrainingDataset}
        isExportingDataset={isExportingDataset}
      />

      <div className="itemBankToolbar">
        <label>
          Раздел ФОС
          <select value={selectedSectionCode} onChange={(event) => setSelectedSectionCode(event.target.value)}>
            <option value="">Все активные разделы</option>
            {enabledSections.map((section) => <option key={section.code} value={section.code}>{section.title}</option>)}
          </select>
        </label>
        <label>
          Максимум заданий на раздел
          <input type="number" min="1" max="200" value={maxItemsPerSection} onChange={(event) => setMaxItemsPerSection(Number(event.target.value))} />
        </label>
        <label className="toggleLabel itemBankCheckbox">
          <input type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />
          Заменить старые задания
        </label>
        <button className="primary" type="button" onClick={generateItems} disabled={isGenerating || !enabledSections.length}>
          {isGenerating ? 'Формируем...' : 'Сформировать задания'}
        </button>
      </div>

      <div className="itemBankStats">
        <span>Всего заданий: <strong>{items.length}</strong></span>
        <span>В выбранном разделе: <strong>{visibleItems.length}</strong></span>
      </div>

      {validation && <ValidationDashboard validation={validation} sectionMap={sectionMap} />}

      <div className="itemBankGrid">
        <div className="itemBankList">
          {visibleItems.length ? visibleItems.map((item, index) => (
            <button
              className={`itemBankListItem ${selectedItemId === item.id ? 'activeItemBankListItem' : ''}`}
              key={item.id}
              type="button"
              onClick={() => setSelectedItemId(item.id)}
            >
              <strong>{index + 1}. {item.topic}</strong>
              <span>{item.assessment_type} · {item.difficulty} · {item.competency_code || 'без компетенции'}</span>
              <small>{item.source_kind || 'template'}</small>
            </button>
          )) : <p className="muted">Задания еще не сформированы.</p>}
        </div>

        <div className="itemBankEditor">
          {selectedItem ? (
            <>
              <div className="questionTopline">
                <h3>Редактор задания</h3>
                <div className="actionGroup">
                  <button className="danger" type="button" onClick={deleteSelectedItem}>Удалить</button>
                  <button className="primary" type="button" onClick={saveSelectedItem} disabled={isSaving}>{isSaving ? 'Сохраняем...' : 'Сохранить'}</button>
                </div>
              </div>
              <label>Формулировка<textarea value={selectedItem.text} onChange={(event) => patchSelectedItem({ text: event.target.value })} /></label>
              <label>Эталонный ответ<textarea value={selectedItem.answer} onChange={(event) => patchSelectedItem({ answer: event.target.value })} /></label>
              <div className="miniGrid">
                <label>Тема<input value={selectedItem.topic} onChange={(event) => patchSelectedItem({ topic: event.target.value })} /></label>
                <label>Компетенция<input value={selectedItem.competency_code} onChange={(event) => patchSelectedItem({ competency_code: event.target.value })} /></label>
                <label>Сложность<select value={selectedItem.difficulty} onChange={(event) => patchSelectedItem({ difficulty: event.target.value })}><option value="easy">Базовая</option><option value="medium">Средняя</option><option value="hard">Повышенная</option></select></label>
              </div>
              <label>Индикатор<textarea value={selectedItem.indicator} onChange={(event) => patchSelectedItem({ indicator: event.target.value })} /></label>
              <label>Критерии оценивания<textarea value={selectedItem.criteria.join('\n')} onChange={(event) => patchSelectedItem({ criteria: event.target.value.split('\n').filter(Boolean) })} /></label>
              <p className="muted">Источник: {selectedItem.source_context || 'не указан'} · способ формирования: {selectedItem.source_kind}</p>

              <section className="trainingFeedback">
                <h3>Экспертная разметка для самообучения</h3>
                <p className="muted">После ручной правки сохраните задание как хороший пример, плохой пример или пример, требующий доработки.</p>
                <label>
                  Комментарий преподавателя
                  <textarea value={teacherComment} onChange={(event) => setTeacherComment(event.target.value)} placeholder="Например: удачная практическая формулировка; не хватает эталонного ответа; слишком общий вопрос..." />
                </label>
                <div className="actionGroup trainingActions">
                  <button className="secondary" type="button" onClick={() => addTrainingExample('needs_revision')} disabled={isTraining}>Нужно доработать</button>
                  <button className="danger" type="button" onClick={() => addTrainingExample('bad')} disabled={isTraining}>Плохой пример</button>
                  <button className="primary" type="button" onClick={() => addTrainingExample('good')} disabled={isTraining}>Хороший пример</button>
                </div>
              </section>
            </>
          ) : <p className="muted">Выберите задание слева.</p>}
        </div>
      </div>
    </section>
  );
}

function TrainingDatasetPanel({ stats, downloadTrainingDataset, isExportingDataset }) {
  return (
    <section className="trainingDatasetPanel">
      <div>
        <h3>Обучающая выборка</h3>
        <p className="muted">Здесь накапливаются экспертно подтвержденные примеры для будущего дообучения генератора.</p>
      </div>
      <div className="itemBankStats">
        <span>Всего: <strong>{stats?.total_examples || 0}</strong></span>
        <span>Хороших: <strong>{stats?.good_examples || 0}</strong></span>
        <span>Плохих: <strong>{stats?.bad_examples || 0}</strong></span>
        <span>На доработку: <strong>{stats?.revision_examples || 0}</strong></span>
        <span>Тем: <strong>{stats?.topics_count || 0}</strong></span>
        <span>Компетенций: <strong>{stats?.competencies_count || 0}</strong></span>
      </div>
      <button className="download" type="button" onClick={downloadTrainingDataset} disabled={isExportingDataset}>
        {isExportingDataset ? 'Экспортируем...' : 'Скачать JSONL датасет'}
      </button>
    </section>
  );
}

function ValidationDashboard({ validation, sectionMap }) {
  return (
    <section className="itemValidation">
      <div className="diagnosticsGrid">
        <Metric value={validation.total_items} label="Всего заданий" />
        <Metric value={`${validation.topics_coverage_score}%`} label="Покрытие тем" />
        <Metric value={`${validation.competencies_coverage_score}%`} label="Покрытие компетенций" />
        <Metric value={`${validation.answers_readiness_score}%`} label="Готовность ответов" />
        <Metric value={`${validation.criteria_readiness_score}%`} label="Готовность критериев" />
        <Metric value={`${validation.duplicate_rate}%`} label="Потенциальные дубли" />
      </div>

      {validation.warnings?.length > 0 && (
        <div className="notice">
          <strong>Результаты проверки банка</strong>
          <ul>{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </div>
      )}

      <div className="coverageTableWrap">
        <h3>Матрица покрытия тем</h3>
        <table className="coverageTable">
          <thead>
            <tr>
              <th>Тема</th>
              <th>Всего заданий</th>
              <th>Разделы</th>
              <th>Компетенции</th>
            </tr>
          </thead>
          <tbody>
            {validation.coverage_rows.map((row) => (
              <tr key={row.topic}>
                <td>{row.topic}</td>
                <td>{row.total_items}</td>
                <td>{Object.entries(row.section_counts).map(([code, count]) => `${sectionMap[code] || code}: ${count}`).join('; ') || '—'}</td>
                <td>{row.competencies.join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {validation.duplicate_groups?.length > 0 && (
        <div className="duplicateList">
          <h3>Потенциальные дубли</h3>
          {validation.duplicate_groups.map((group, index) => (
            <article className="duplicateItem" key={`${group.sample_text}-${index}`}>
              <strong>Группа {index + 1} · сходство {Math.round(group.similarity * 100)}%</strong>
              <p>{group.sample_text}</p>
              <small>Связанных заданий: {group.item_ids.length}</small>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Metric({ value, label }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

export default AssessmentItemBank;
