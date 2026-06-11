import React, { useEffect, useMemo, useState } from 'react';

const DEFAULT_LEVELS = [
  'Продвинутый уровень',
  'Повышенный уровень',
  'Пороговый уровень',
];

function CompetencyMatrixEditor({ api, fund, setFund, setError, setSuccess, onFundRefresh }) {
  const [selectedId, setSelectedId] = useState('');
  const [draft, setDraft] = useState(null);
  const [isCreating, setCreating] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isDeleting, setDeleting] = useState(false);

  const selected = useMemo(
    () => fund.competencies.find((item) => item.id === selectedId) || null,
    [fund.competencies, selectedId],
  );

  useEffect(() => {
    if (!fund.competencies.length) {
      setSelectedId('');
      setDraft(null);
      return;
    }
    if (!selectedId || !fund.competencies.some((item) => item.id === selectedId)) {
      setSelectedId(fund.competencies[0].id);
    }
  }, [fund.fund_id, fund.competencies]);

  useEffect(() => {
    if (!selected) return;
    setDraft({
      ...selected,
      indicatorsText: selected.indicators.join('\n'),
      levelsText: selected.levels.join('\n'),
    });
  }, [selected?.id]);

  function patchDraft(patch) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  async function saveCompetency() {
    if (!selected || !draft) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/assessment-funds/${fund.fund_id}/competencies/${selected.id}`, {
        code: draft.code,
        description: draft.description,
        indicators: splitLines(draft.indicatorsText),
        levels: splitLines(draft.levelsText),
      });
      setFund(response.data);
      await onFundRefresh();
      setSuccess('Компетенция и индикаторы сохранены.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось сохранить компетенцию.');
    } finally {
      setSaving(false);
    }
  }

  async function deleteCompetency() {
    if (!selected) return;
    setDeleting(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.delete(`/api/assessment-funds/${fund.fund_id}/competencies/${selected.id}`);
      setFund(response.data);
      setSelectedId(response.data.competencies[0]?.id || '');
      await onFundRefresh();
      setSuccess('Компетенция удалена. Связи заданий с ней очищены.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось удалить компетенцию.');
    } finally {
      setDeleting(false);
    }
  }

  async function createCompetency() {
    setCreating(true);
    setError('');
    setSuccess('');
    try {
      const response = await api.post(`/api/assessment-funds/${fund.fund_id}/competencies`, {
        code: buildNewCode(fund.competencies),
        description: '',
        indicators: [],
        levels: DEFAULT_LEVELS,
      });
      setFund(response.data);
      const created = response.data.competencies[response.data.competencies.length - 1];
      setSelectedId(created?.id || '');
      await onFundRefresh();
      setSuccess('Новая компетенция добавлена. Заполните описание и индикаторы.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось добавить компетенцию.');
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="competencyEditor">
      <div className="questionTopline">
        <div>
          <h3>Матрица компетенций</h3>
          <p className="muted">Редактируйте коды, описания, индикаторы достижения и уровни сформированности.</p>
        </div>
        <button className="secondary smallButton" type="button" onClick={createCompetency} disabled={isCreating}>
          {isCreating ? 'Добавляем...' : 'Добавить компетенцию'}
        </button>
      </div>

      {fund.competencies.length ? (
        <>
          <div className="competencyTabs">
            {fund.competencies.map((item) => (
              <button
                className={`competencyTab ${selectedId === item.id ? 'activeCompetencyTab' : ''}`}
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
              >
                {item.code}
              </button>
            ))}
          </div>

          {draft && (
            <div className="competencyForm">
              <label>
                Код компетенции
                <input value={draft.code} onChange={(event) => patchDraft({ code: event.target.value })} />
              </label>
              <label>
                Содержание компетенции
                <textarea value={draft.description} onChange={(event) => patchDraft({ description: event.target.value })} />
              </label>
              <label>
                Индикаторы достижения — каждый с новой строки
                <textarea value={draft.indicatorsText} onChange={(event) => patchDraft({ indicatorsText: event.target.value })} />
              </label>
              <label>
                Уровни сформированности — каждый с новой строки
                <textarea value={draft.levelsText} onChange={(event) => patchDraft({ levelsText: event.target.value })} />
              </label>
              <div className="actionGroup competencyActions">
                <button className="danger" type="button" onClick={deleteCompetency} disabled={isDeleting}>
                  {isDeleting ? 'Удаляем...' : 'Удалить'}
                </button>
                <button className="primary" type="button" onClick={saveCompetency} disabled={isSaving}>
                  {isSaving ? 'Сохраняем...' : 'Сохранить компетенцию'}
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="notice">
          Компетенции не распознаны автоматически. Добавьте первую компетенцию вручную.
        </div>
      )}
    </section>
  );
}

function splitLines(value) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean);
}

function buildNewCode(competencies) {
  const existing = new Set(competencies.map((item) => item.code.toLowerCase()));
  let index = 1;
  while (existing.has(`новая-${index}`)) index += 1;
  return `НОВАЯ-${index}`;
}

export default CompetencyMatrixEditor;
