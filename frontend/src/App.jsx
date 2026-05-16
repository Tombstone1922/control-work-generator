import React, { useMemo, useState } from 'react';
import axios from 'axios';

const API_URL = 'http://127.0.0.1:8000';

const defaultGenerationParams = {
  variants_count: 2,
  questions_per_variant: 5,
  difficulty: 'medium',
  question_types: ['open'],
};

function App() {
  const [file, setFile] = useState(null);
  const [program, setProgram] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [params, setParams] = useState(defaultGenerationParams);
  const [isUploading, setUploading] = useState(false);
  const [isGenerating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const exportUrl = useMemo(() => {
    if (!generation?.session_id) return '';
    return `${API_URL}/api/export/docx/${generation.session_id}`;
  }, [generation]);

  async function uploadProgram(event) {
    event.preventDefault();
    if (!file) {
      setError('Выберите файл РПД в формате DOCX, PDF или TXT.');
      return;
    }

    setError('');
    setUploading(true);
    setGeneration(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await axios.post(`${API_URL}/api/programs/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setProgram(response.data);
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
    setGenerating(true);

    try {
      const response = await axios.post(`${API_URL}/api/generation/run`, {
        program_id: program.program_id,
        ...params,
      });
      setGeneration(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Не удалось выполнить генерацию.');
    } finally {
      setGenerating(false);
    }
  }

  function updateQuestionTypes(value) {
    const types = value.split(',').map((item) => item.trim()).filter(Boolean);
    setParams((current) => ({ ...current, question_types: types.length ? types : ['open'] }));
  }

  return (
    <main className="page">
      <section className="hero card">
        <div>
          <p className="eyebrow">ВКР · MVP-прототип</p>
          <h1>Генератор контрольных работ по РПД</h1>
          <p className="heroText">
            Загрузите рабочую программу дисциплины, получите извлеченные темы и сформируйте варианты контрольной работы с отчетом качества.
          </p>
        </div>
        <div className="statusBox">
          <span className="statusDot" />
          Закрытый контур: без обязательной передачи данных во внешние сервисы
        </div>
      </section>

      {error && <div className="alert">{error}</div>}

      <section className="grid">
        <form className="card" onSubmit={uploadProgram}>
          <h2>1. Загрузка РПД</h2>
          <p className="muted">Поддерживаются DOCX, PDF и TXT. После загрузки backend извлечет текст и выполнит базовый анализ.</p>
          <input
            className="fileInput"
            type="file"
            accept=".docx,.pdf,.txt"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          <button className="primary" type="submit" disabled={isUploading}>
            {isUploading ? 'Анализируем...' : 'Загрузить и проанализировать'}
          </button>
        </form>

        <section className="card">
          <h2>2. Параметры генерации</h2>
          <label>
            Количество вариантов
            <input
              type="number"
              min="1"
              max="20"
              value={params.variants_count}
              onChange={(event) => setParams({ ...params, variants_count: Number(event.target.value) })}
            />
          </label>
          <label>
            Заданий в варианте
            <input
              type="number"
              min="1"
              max="50"
              value={params.questions_per_variant}
              onChange={(event) => setParams({ ...params, questions_per_variant: Number(event.target.value) })}
            />
          </label>
          <label>
            Уровень сложности
            <select
              value={params.difficulty}
              onChange={(event) => setParams({ ...params, difficulty: event.target.value })}
            >
              <option value="easy">Базовый</option>
              <option value="medium">Средний</option>
              <option value="hard">Повышенный</option>
            </select>
          </label>
          <label>
            Типы заданий через запятую
            <input
              value={params.question_types.join(', ')}
              onChange={(event) => updateQuestionTypes(event.target.value)}
              placeholder="open, test, practice"
            />
          </label>
          <button className="primary" type="button" onClick={runGeneration} disabled={isGenerating || !program}>
            {isGenerating ? 'Генерируем...' : 'Сформировать контрольную'}
          </button>
        </section>
      </section>

      {program && (
        <section className="card">
          <h2>Результаты анализа РПД</h2>
          <div className="columns">
            <List title="Темы" items={program.topics} />
            <List title="Компетенции" items={program.competencies} />
            <List title="Результаты обучения" items={program.learning_outcomes} />
          </div>
        </section>
      )}

      {generation && (
        <section className="card">
          <div className="sectionHeader">
            <h2>Сформированная контрольная работа</h2>
            <a className="download" href={exportUrl}>Скачать DOCX</a>
          </div>

          <div className="quality">
            <div><strong>{generation.quality_report.topic_coverage}</strong><span>Покрытие тем</span></div>
            <div><strong>{generation.quality_report.duplicate_rate}</strong><span>Доля дублей</span></div>
            <div><strong>{generation.quality_report.total_questions}</strong><span>Всего заданий</span></div>
          </div>

          <h3>Рекомендации</h3>
          <ul className="recommendations">
            {generation.quality_report.recommendations.map((item) => <li key={item}>{item}</li>)}
          </ul>

          <div className="variants">
            {generation.variants.map((variant) => (
              <article className="variant" key={variant.variant_number}>
                <h3>Вариант {variant.variant_number}</h3>
                {variant.questions.map((question, index) => (
                  <div className="question" key={question.id}>
                    <b>{index + 1}. {question.text}</b>
                    <p>Тема: {question.topic}</p>
                    <small>Тип: {question.type}; сложность: {question.difficulty}</small>
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
  return (
    <div>
      <h3>{title}</h3>
      {items.length ? (
        <ul className="compactList">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p className="muted">Не найдено</p>
      )}
    </div>
  );
}

export default App;
