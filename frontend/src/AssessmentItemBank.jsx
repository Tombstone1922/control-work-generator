import React, { useEffect, useMemo, useState } from 'react';

function AssessmentItemBank({ api, fund, sections, setError, setSuccess, onFundRefresh }) {
  const [items, setItems] = useState([]);
  const [selectedSectionCode, setSelectedSectionCode] = useState('');
  const [selectedItemId, setSelectedItemId] = useState('');
  const [isLoading, setLoading] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [maxItemsPerSection, setMaxItemsPerSection] = useState(20);

  const enabledSections = useMemo(
    () => sections.filter((section) => section.enabled && !['competency_matrix', 'grading_rubric'].includes(section.assessment_type)),
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
    loadItems();
  }, [fund?.fund_id]);

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
      });
      setItems(response.data);
      setSelectedItemId(response.data[0]?.id || '');
      await onFundRefresh();
      setSuccess(selectedSectionCode ? 'Задания выбранного раздела сформированы.' : 'Банк заданий ФОС сформирован.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сформировать банк заданий.');
    } finally {
      setGenerating(false);
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
      setSuccess('Задание сохранено.');
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
          <p className="muted">Локальный шаблонный генератор создает редактируемые заготовки с привязкой к темам и компетенциям.</p>
        </div>
        <button className="secondary" type="button" onClick={() => loadItems(selectedSectionCode)} disabled={isLoading}>
          {isLoading ? 'Обновляем...' : 'Обновить банк'}
        </button>
      </div>

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
            </>
          ) : <p className="muted">Выберите задание слева.</p>}
        </div>
      </div>
    </section>
  );
}

export default AssessmentItemBank;
