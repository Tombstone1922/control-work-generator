import React, { useEffect, useState } from 'react';

function DemoBankPanel({ api, program, setError, setSuccess }) {
  const [mode, setMode] = useState('seed');
  const [summary, setSummary] = useState(null);
  const [isSeeding, setSeeding] = useState(false);
  const [isOpening, setOpening] = useState(false);
  const [isDownloadingCurrent, setDownloadingCurrent] = useState(false);
  const [isDownloadingAll, setDownloadingAll] = useState(false);

  useEffect(() => {
    setSummary(null);
  }, [program?.program_id]);

  async function seedBank() {
    if (!program?.program_id) return setError('Сначала загрузите РПД в рабочей области или выберите ее из истории.');
    setSeeding(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post(`/api/demo-bank/${program.program_id}/seed`);
      setSummary(response.data);
      const pipeline = response.data.llm?.used
        ? ` Общая система подготовила банк: context-builder + контекст РПД + Qwen-refiner; улучшено ${response.data.llm.refined} заданий за ${response.data.llm.seconds} с.`
        : ' Банк подготовлен context-builder по контексту РПД; Qwen не использовался, проверьте запуск локальной модели.';
      const persistent = response.data.persistent ? ' Банк сохранен на постоянку в локальный JSON-файл.' : '';
      setSuccess(`Банк заданий подготовлен: ${response.data.total_items} заданий.${pipeline}${persistent}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось подготовить банк заданий.');
    } finally {
      setSeeding(false);
    }
  }

  async function openWorkMode() {
    if (!program?.program_id) return setError('Сначала загрузите РПД в рабочей области. Историю выбирать не обязательно.');
    setOpening(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.get(`/api/demo-bank/${program.program_id}/work-mode`);
      setSummary(response.data);
      if (response.data.ready) {
        const matchText = response.data.restored_from_file
          ? ' Банк восстановлен из постоянного JSON-файла по названию РПД.'
          : response.data.matched_by_name
            ? ' Банк был найден по совпадению названия РПД.'
            : '';
        setSuccess(`Рабочий режим открыт: задания взяты из подготовленного банка без генерации.${matchText}`);
      } else {
        setError('Для этой РПД банк еще не набит и совпадение по названию не найдено. Сначала нажмите “Набить банк заданий”.');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось открыть рабочий режим.');
    } finally {
      setOpening(false);
    }
  }

  async function downloadCurrentBank() {
    if (!program?.program_id) return setError('Сначала выберите текущую РПД.');
    setDownloadingCurrent(true);
    setError('');
    try {
      const response = await api.get(`/api/demo-bank/${program.program_id}/download-current`, { responseType: 'blob' });
      downloadBlob(response.data, `bank_${safeFilename(program.filename || 'current_rpd')}.json`);
      setSuccess('JSON-банк текущей РПД скачан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось скачать банк текущей РПД.');
    } finally {
      setDownloadingCurrent(false);
    }
  }

  async function downloadAllBanks() {
    setDownloadingAll(true);
    setError('');
    try {
      const response = await api.get('/api/demo-bank/download/all', { responseType: 'blob' });
      downloadBlob(response.data, 'prepared_banks_all.zip');
      setSuccess('Архив со всеми подготовленными JSON-банками скачан.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось скачать общий архив банков.');
    } finally {
      setDownloadingAll(false);
    }
  }

  return (
    <section className="card quickGenerationCard">
      <p className="eyebrow">Демонстрационный режим защиты</p>
      <h2>Подготовленный банк общей системы</h2>
      <p className="muted">Система берет темы, компетенции и контекст РПД, затем context-builder делает каркас задания и ответа, а Qwen улучшает формулировку и эталонный ответ.</p>

      <div className="authTabs demoModeTabs">
        <button className={mode === 'seed' ? 'primary' : 'secondary'} type="button" onClick={() => setMode('seed')}>Набор заданий</button>
        <button className={mode === 'work' ? 'primary' : 'secondary'} type="button" onClick={() => setMode('work')}>Рабочий режим</button>
      </div>

      <div className="notice">
        <strong>План банка:</strong> 40 устных вопросов, 20 практических заданий, 32 вопроса к зачету, 13 практических заданий к зачету, 40 тестовых диагностических заданий. Итого 145 элементов.
      </div>

      {mode === 'seed' ? (
        <div className="demoModeBlock">
          <h3>Набор заданий</h3>
          <p className="muted">Этот режим запускается заранее. Общая система строит вопросы и ответы по РПД: устные вопросы, практику, тесты с A-D, эталонные ответы и критерии.</p>
          <div className="demoBankActions">
            <button className="primary" type="button" onClick={seedBank} disabled={isSeeding || !program}>{isSeeding ? 'Общая система набивает банк...' : 'Набить банк заданий для текущей РПД'}</button>
            <button className="secondary" type="button" onClick={downloadCurrentBank} disabled={isDownloadingCurrent || !program}>{isDownloadingCurrent ? 'Скачиваем...' : 'Скачать банк текущей РПД'}</button>
            <button className="download" type="button" onClick={downloadAllBanks} disabled={isDownloadingAll}>{isDownloadingAll ? 'Скачиваем архив...' : 'Скачать весь банк'}</button>
          </div>
        </div>
      ) : (
        <div className="demoModeBlock">
          <h3>Рабочий режим</h3>
          <p className="muted">Можно просто загрузить РПД заново. Если имя совпадает, например RP_09.03.02_5990_2925_2025, система найдет постоянный банк и покажет задания без генерации.</p>
          <div className="demoBankActions">
            <button className="primary" type="button" onClick={openWorkMode} disabled={isOpening || !program}>{isOpening ? 'Ищем банк по названию...' : 'Показать готовые задания'}</button>
            <button className="secondary" type="button" onClick={downloadCurrentBank} disabled={isDownloadingCurrent || !program}>{isDownloadingCurrent ? 'Скачиваем...' : 'Скачать банк текущей РПД'}</button>
            <button className="download" type="button" onClick={downloadAllBanks} disabled={isDownloadingAll}>{isDownloadingAll ? 'Скачиваем архив...' : 'Скачать весь банк'}</button>
          </div>
        </div>
      )}

      {summary && <PreparedBankSummary summary={summary} />}
    </section>
  );
}

function PreparedBankSummary({ summary }) {
  return (
    <div className="generationSummary demoBankSummary">
      <strong>{summary.ready ? 'Банк готов' : 'Банк не подготовлен'}</strong>
      <div className="itemBankStats">
        <span>Всего: <strong>{summary.total_items}</strong></span>
        <span>План: <strong>{summary.planned_items}</strong></span>
        <span>Версия: <strong>{summary.model_version}</strong></span>
        <span>Файл: <strong>{summary.filename}</strong></span>
        {summary.llm && <span>Pipeline: <strong>{summary.llm.pipeline || (summary.llm.used ? 'context+qwen' : 'context-builder')}</strong></span>}
        {summary.llm && <span>Qwen-refiner: <strong>{summary.llm.used ? `${summary.llm.refined} улучшено` : 'не использован'}</strong></span>}
        {summary.llm?.rejected > 0 && <span>Отклонено: <strong>{summary.llm.rejected}</strong></span>}
        {summary.llm?.seconds > 0 && <span>Время: <strong>{summary.llm.seconds} с</strong></span>}
        <span>Постоянное хранение: <strong>{summary.persistent ? 'да' : 'нет'}</strong></span>
        {summary.restored_from_file && <span>Источник: <strong>JSON-файл</strong></span>}
        {summary.matched_by_name && <span>Мэтч: <strong>по названию РПД</strong></span>}
      </div>
      {summary.persistent_path && <p className="muted">Файл банка: {summary.persistent_path}</p>}

      <div className="coverageTableWrap">
        <h3>Разделы банка</h3>
        <table className="coverageTable">
          <thead><tr><th>Раздел</th><th>Тип</th><th>План</th><th>Готово</th></tr></thead>
          <tbody>{summary.sections.map((section) => <tr key={section.code}><td>{section.title}</td><td>{section.assessment_type}</td><td>{section.planned_items}</td><td>{section.generated_items}</td></tr>)}</tbody>
        </table>
      </div>

      {summary.sample_items?.length > 0 && (
        <div className="demoBankItems">
          <h3>Примеры заданий в рабочем режиме</h3>
          {summary.sample_items.map((item, index) => (
            <article className="itemBankListItem demoBankItem" key={item.id}>
              <div className="itemCardHeader"><strong>{index + 1}. {item.topic}</strong><span className="sourceBadge sourceLearned">готовый банк системы</span></div>
              <p>{item.text}</p>
              {item.answer && <small><strong>Ответ:</strong> {item.answer}</small>}
              <small>{item.assessment_type} · {item.difficulty} · {item.competency_code || 'без компетенции'}</small>
            </article>
          ))}
        </div>
      )}
    </div>
  );
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

function safeFilename(value) {
  return String(value || 'bank').replace(/\.(docx|pdf|txt)$/i, '').replace(/[^a-zа-я0-9_-]+/gi, '_').toLowerCase();
}

export default DemoBankPanel;
