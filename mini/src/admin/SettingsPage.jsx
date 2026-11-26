import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

const MODES = [
  { id: 'manual', label: 'Ручное (админ подтверждает)', hint: 'Заявка попадает админу с кнопками ✅/❌' },
  { id: 'auto',   label: 'Автоматическое', hint: 'Заявка сразу подтверждена, админ получает уведомление' },
  { id: 'client', label: 'Клиент подтверждает', hint: 'Через час бот спросит клиента «Точно придёте?»' },
];

const WEEKDAYS = [
  { key: 'mon_fri', label: 'Пн–Пт' },
  { key: 'sat',     label: 'Сб' },
  { key: 'sun',     label: 'Вс' },
];

const MAP_PROVIDERS = [
  { id: 'yandex', label: 'Яндекс.Карты' },
  { id: '2gis',   label: '2ГИС' },
  { id: 'both',   label: 'Оба (клиент выберет)' },
];

const CHANNEL_OPTIONS = [
  { id: 'max', label: 'MAX (текущий бот)' },
  { id: 'vk',  label: 'VK (после подключения)' },
];

const NUMERIC_RULES = {
  review_request_delay_hours: { min: 1, max: 168, label: 'Задержка запроса отзыва, часов' },
  review_positive_threshold:  { min: 1, max: 5,   label: 'Порог положительной оценки' },
  client_confirm_delay_min:   { min: 5, max: 1440,  label: 'Через сколько минут спросить клиента' },
  client_confirm_timeout_min: { min: 5, max: 1440,  label: 'Сколько минут ждать ответа' },
  slot_step_min:              { min: 5, max: 240,   label: 'Длительность слота' },
  autocomplete_after_hours:   { min: 0, max: 48,    label: 'Через сколько часов считать визит состоявшимся' },
  pending_timeout_min:        { min: 0, max: 10080, label: 'Через сколько минут отменять неподтверждённые' },
  evening_summary_hour:       { min: 0, max: 23,    label: 'Час вечерней сводки' },
  max_bookings_per_day:       { min: 0, max: 50,    label: 'Максимум записей на один день' },
  schedule_horizon_days:      { min: 1, max: 365,   label: 'Горизонт генерации слотов' },
  auto_manual_no_show_threshold:       { min: 0, max: 100,  label: 'Порог неявок для manual' },
  client_at_risk_days:                 { min: 1, max: 365,  label: 'Клиент «под риском», дней' },
  client_inactive_days:                { min: 1, max: 3650, label: 'Клиент «потерянный», дней' },
  quiet_hours_start:                   { min: 0, max: 23,   label: 'Начало тихих часов' },
  quiet_hours_end:                     { min: 0, max: 23,   label: 'Конец тихих часов' },
  slot_backfill_delay_minutes:         { min: 0, max: 1440, label: 'Уведомлять лист ожидания через, минут' },
  slot_backfill_waitlist_wait_minutes: { min: 0, max: 1440, label: 'Ждать реакции листа, минут' },
  slot_backfill_batch_minutes:         { min: 0, max: 1440, label: 'Копить слоты пачкой, минут' },
  slot_backfill_sent_ttl_hours:        { min: 1, max: 720,  label: 'Сколько «живёт» неотвеченное предложение' },
  slot_backfill_min_gap_hours:         { min: 1, max: 720,  label: 'Мин. отрыв от текущей записи, часов' },
  slot_backfill_max_candidates:        { min: 1, max: 20,   label: 'Сколько клиентов опрашивать' },
  slot_backfill_cooldown_hours:        { min: 1, max: 168,  label: 'Не дёргать клиента чаще, часов' },
};

const TABS = [
  { id: 'org',      label: '🏢 Организация' },
  { id: 'confirm',  label: '✅ Заявки' },
  { id: 'schedule', label: '📅 Расписание' },
  { id: 'visits',   label: '📊 Учёт' },
  { id: 'clients',  label: '👥 Клиенты' },
  { id: 'backfill', label: '🔥 Горящие окна' },
  { id: 'reviews',  label: '⭐ Отзывы' },
];

export default function SettingsPage({ orgId, onOrgRenamed }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState(null);
  const [timezones, setTimezones] = useState([]);
  const [orgName, setOrgName] = useState('');
  const [tab, setTab] = useState('org');

  useEffect(() => {
    Promise.all([
      adminApi.getSettings(orgId),
      adminApi.getTimezones().catch(() => ({ timezones: [] })),
    ])
      .then(([settingsData, tzData]) => {
        setSettings(settingsData.settings);
        setOrgName(settingsData.name || '');
        setTimezones(tzData.timezones || []);
        setStep('ready');
      })
      .catch((e) => {
        setError(e.message);
        setStep('error');
      });
  }, [orgId]);

  function update(field, value) {
    setSettings((s) => ({ ...s, [field]: value }));
    setSaveMsg('');
  }

  function updateNumeric(field, raw) {
    setSaveMsg('');
    if (raw === '') {
      setSettings((s) => ({ ...s, [field]: '' }));
      return;
    }
    if (/^\d+$/.test(raw)) {
      setSettings((s) => ({ ...s, [field]: raw }));
    }
  }

  function updateWorkHours(dayKey, field, value) {
    setSettings((s) => {
      const wh = { ...(s.work_hours || {}) };
      const day = wh[dayKey] ? { ...wh[dayKey] } : { start: '09:00', end: '18:00' };
      day[field] = value;
      wh[dayKey] = day;
      return { ...s, work_hours: wh };
    });
    setSaveMsg('');
  }

  function toggleDay(dayKey, enabled) {
    setSettings((s) => {
      const wh = { ...(s.work_hours || {}) };
      if (enabled) {
        wh[dayKey] = wh[dayKey] || { start: '09:00', end: '18:00' };
      } else {
        wh[dayKey] = null;
      }
      return { ...s, work_hours: wh };
    });
    setSaveMsg('');
  }

  async function handleSave() {
    const prepared = { ...settings };
    for (const [field, rule] of Object.entries(NUMERIC_RULES)) {
      if (prepared[field] === undefined) continue;
      const raw = prepared[field];
      if (raw === '' || raw === null) {
        setSaveMsg(`❌ «${rule.label}»: поле не может быть пустым`);
        return;
      }
      const num = typeof raw === 'number' ? raw : parseInt(raw, 10);
      if (!Number.isFinite(num) || num < rule.min || num > rule.max) {
        setSaveMsg(`❌ «${rule.label}»: допустимо от ${rule.min} до ${rule.max}`);
        return;
      }
      prepared[field] = num;
    }

    const trimmedName = (orgName || '').trim();
    if (!trimmedName) {
      setSaveMsg('❌ Название организации не может быть пустым');
      return;
    }
    if (trimmedName.length > 200) {
      setSaveMsg('❌ Название организации — не длиннее 200 символов');
      return;
    }

    setSaving(true);
    setSaveMsg('');
    try {
      const payload = { ...prepared, name: trimmedName };
      const data = await adminApi.saveSettings(orgId, payload);
      setSettings(data.settings);
      if (data.name) setOrgName(data.name);
      setSaveMsg('✅ Сохранено');
      if (onOrgRenamed) onOrgRenamed();
    } catch (e) {
      setSaveMsg('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  }

  if (step === 'loading') return <div className="loading">Загрузка настроек…</div>;
  if (step === 'error') return <div className="error-box">Ошибка: {error}</div>;
  if (!settings) return null;

  const currentTz = settings.timezone || '';
  const hasCurrentTz = timezones.some((t) => t.id === currentTz);
  const currentMap = settings.map_provider || 'both';
  const currentChannel = settings.channel_default || 'max';

  return (
    <div>
      <div className="filters-scroll" style={{ marginBottom: 12 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={'filter-btn' + (tab === t.id ? ' active' : '')}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'org' && (
        <>
          <div className="card">
            <h2 className="card-title">Организация</h2>
            <div className="form-group">
              <label className="form-label">Название</label>
              <input
                className="form-input"
                type="text"
                value={orgName}
                onChange={(e) => { setOrgName(e.target.value); setSaveMsg(''); }}
                maxLength={200}
                disabled={saving}
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Отображается в шапке админки, в приветствии бота, в вечерней сводке и у суперадмина в списке организаций.
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Часовой пояс</h2>
            <div className="form-group">
              <select
                className="form-input"
                value={currentTz}
                onChange={(e) => update('timezone', e.target.value)}
                disabled={timezones.length === 0}
              >
                {currentTz && !hasCurrentTz && (
                  <option value={currentTz}>{currentTz}</option>
                )}
                {timezones.map((tz) => (
                  <option key={tz.id} value={tz.id}>{tz.label}</option>
                ))}
                {timezones.length === 0 && !currentTz && (
                  <option value="">Загрузка…</option>
                )}
              </select>
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Определяет, в каком поясе ведутся записи. Влияет на отображение
                времени, расчёт «слот в прошлом», «тихие часы» (22:00–9:00),
                напоминания и вечернюю сводку.<br />
                Меняйте, только если клиника физически находится в другом поясе —
                уже созданные записи будут интерпретироваться в новом поясе.
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Сервис карт</h2>
            <div className="form-group">
              <label className="form-label">Какие ссылки на маршрут показывать клиенту</label>
              <select
                className="form-input"
                value={currentMap}
                onChange={(e) => update('map_provider', e.target.value)}
              >
                {MAP_PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Ссылка на маршрут добавляется в подтверждение записи и в напоминания.
                «Оба» — клиент сам выберет удобный сервис (Яндекс популярнее в Москве
                и Питере, 2ГИС — в регионах).
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Канал связи с клиентом</h2>
            <div className="form-group">
              <label className="form-label">Канал по умолчанию</label>
              <select
                className="form-input"
                value={currentChannel}
                onChange={(e) => update('channel_default', e.target.value)}
              >
                {CHANNEL_OPTIONS.map((c) => (
                  <option key={c.id} value={c.id}>{c.label}</option>
                ))}
              </select>
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Куда отправлять уведомления, если клиент есть в нескольких каналах.
                Сейчас реально работает только MAX — VK появится после подключения.
              </div>
            </div>
            <label className="radio-row" style={{ marginTop: 8 }}>
              <input
                type="checkbox"
                checked={!!settings.channel_duplicate}
                onChange={(e) => update('channel_duplicate', e.target.checked)}
              />
              <span>
                Дублировать во все каналы клиента
                <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                  Если выключено — отправляем только в канал по умолчанию.
                  Если включено — клиент получит уведомление и в MAX, и в VK.
                  Полезно на время переезда, но легко задвоить напоминания.
                </div>
              </span>
            </label>
          </div>
        </>
      )}

      {tab === 'confirm' && (
        <>
          <div className="card">
            <h2 className="card-title">Подтверждение заявок</h2>
            {MODES.map((m) => (
              <label key={m.id} className="radio-row">
                <input
                  type="radio"
                  name="mode"
                  value={m.id}
                  checked={settings.confirmation_mode === m.id}
                  onChange={() => update('confirmation_mode', m.id)}
                />
                <div>
                  <div className="radio-label">{m.label}</div>
                  <div className="radio-hint">{m.hint}</div>
                </div>
              </label>
            ))}

            {settings.confirmation_mode === 'client' && (
              <div className="nested-fields">
                <div className="form-group">
                  <label className="form-label">Через сколько минут спросить клиента</label>
                  <input
                    className="form-input"
                    type="number"
                    min="5"
                    max="1440"
                    value={settings.client_confirm_delay_min ?? ''}
                    onChange={(e) => updateNumeric('client_confirm_delay_min', e.target.value)}
                    disabled={saving}
                  />
                  <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                    От 5 до 1440 минут. Если до приёма меньше — спросим раньше (минимум 2 минуты после записи).
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Сколько минут ждать ответа</label>
                  <input
                    className="form-input"
                    type="number"
                    min="5"
                    max="1440"
                    value={settings.client_confirm_timeout_min ?? ''}
                    onChange={(e) => updateNumeric('client_confirm_timeout_min', e.target.value)}
                    disabled={saving}
                  />
                  <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                    От 5 до 1440 минут.
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="card-title">Напоминания клиентам</h2>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={!!settings.reminder_24h}
                onChange={(e) => update('reminder_24h', e.target.checked)}
              />
              <span>Напоминать за 24 часа до приёма</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={!!settings.reminder_2h}
                onChange={(e) => update('reminder_2h', e.target.checked)}
              />
              <span>Напоминать за 2 часа до приёма</span>
            </label>
          </div>
        </>
      )}

      {tab === 'schedule' && (
        <>
          <div className="card">
            <h2 className="card-title">Рабочие часы</h2>
            {WEEKDAYS.map((w) => {
              const day = settings.work_hours && settings.work_hours[w.key];
              const enabled = !!day;
              return (
                <div key={w.key} className="workday-row">
                  <label className="checkbox-row" style={{ minWidth: 100 }}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => toggleDay(w.key, e.target.checked)}
                    />
                    <span>{w.label}</span>
                  </label>
                  {enabled && (
                    <>
                      <input
                        className="time-input"
                        type="time"
                        value={day.start}
                        onChange={(e) => updateWorkHours(w.key, 'start', e.target.value)}
                      />
                      <span className="dash">—</span>
                      <input
                        className="time-input"
                        type="time"
                        value={day.end}
                        onChange={(e) => updateWorkHours(w.key, 'end', e.target.value)}
                      />
                    </>
                  )}
                  {!enabled && <span className="day-off">выходной</span>}
                </div>
              );
            })}
          </div>

          <div className="card">
            <h2 className="card-title">Шаг слотов</h2>
            <div className="form-group">
              <label className="form-label">Длительность одного слота (минут)</label>
              <input
                className="form-input"
                type="number"
                min="5"
                max="240"
                step="5"
                value={settings.slot_step_min ?? ''}
                onChange={(e) => updateNumeric('slot_step_min', e.target.value)}
                disabled={saving}
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                От 5 до 240 минут.
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Горизонт генерации</h2>
            <div className="form-group">
              <label className="form-label">
                Горизонт генерации слотов из графиков, дней
              </label>
              <input
                className="form-input"
                type="number"
                min="1"
                max="365"
                value={settings.schedule_horizon_days ?? ''}
                onChange={(e) => updateNumeric('schedule_horizon_days', e.target.value)}
                disabled={saving}
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                На сколько дней вперёд автоматически создаются слоты из графика специалиста.
                Фоновый воркер продлевает горизонт раз в сутки. Допустимо 1–365, по умолчанию 60.
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">🌙 Тихие часы</h2>
            <div className="form-group">
              <label className="form-label">Начало тихих часов (0–23)</label>
              <input
                className="form-input"
                type="number"
                min="0"
                max="23"
                value={settings.quiet_hours_start ?? ''}
                onChange={(e) => updateNumeric('quiet_hours_start', e.target.value)}
                disabled={saving}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Конец тихих часов (0–23)</label>
              <input
                className="form-input"
                type="number"
                min="0"
                max="23"
                value={settings.quiet_hours_end ?? ''}
                onChange={(e) => updateNumeric('quiet_hours_end', e.target.value)}
                disabled={saving}
              />
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              В этом интервале не отправляются напоминания 24/2 ч и запрос
              на подтверждение в режиме «Клиент подтверждает». Исключения:
              <ul style={{ margin: '6px 0 0 16px', padding: 0 }}>
                <li>«Последний шанс» за час до приёма — работает всегда.</li>
                <li>Если приём наступит до конца тихих часов — спросим/напомним
                  раньше, чтобы клиент успел ответить.</li>
              </ul>
              По умолчанию 22 → 9 (МСК-подобные часы клиники). Если начало
              меньше конца (например, 1 → 6) — интервал трактуется как
              «с 1 до 6». Если оба равны — тихие часы выключены.
            </div>
          </div>
        </>
      )}

      {tab === 'visits' && (
        <div className="card">
          <h2 className="card-title">Учёт визитов</h2>
          <div className="form-group">
            <label className="form-label">
              Через сколько часов после приёма считать запись состоявшейся
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="48"
              value={settings.autocomplete_after_hours ?? ''}
              onChange={(e) => updateNumeric('autocomplete_after_hours', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Прошедшая подтверждённая запись сама станет «пришёл». От этого зависят
              «Спасибо за визит» и сегменты клиентов. 0 — не отмечать автоматически.
              Если админ нажал «Не пришёл», отметка не перезаписывается.
              Допустимо 0–48.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">
              Отменять неподтверждённые заявки через, минут
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="10080"
              value={settings.pending_timeout_min ?? ''}
              onChange={(e) => updateNumeric('pending_timeout_min', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Чтобы слот не висел занятым, пока админ не подтвердил. 0 — не отменять.
              Допустимо 0–10080.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">
              Максимум активных записей на один день у одного клиента
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="50"
              value={settings.max_bookings_per_day ?? ''}
              onChange={(e) => updateNumeric('max_bookings_per_day', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Защита от «забивания» всех слотов одним клиентом. Дополнительно
              система не даст записаться дважды на одно и то же время (даже
              к разным специалистам). 0 — без ограничений. Допустимо 0–50.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">
              Порог неявок для ручного подтверждения
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="100"
              value={settings.auto_manual_no_show_threshold ?? ''}
              onChange={(e) => updateNumeric('auto_manual_no_show_threshold', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Если у клиента накопилось столько неявок (или больше), новые записи
              попадают в ручное подтверждение — даже если в организации стоит
              автоматическое подтверждение. 0 — не применять. Допустимо 0–100.
              Счётчик неявок админ видит в карточке клиента и может сбросить.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">
              Час вечерней сводки
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="23"
              value={settings.evening_summary_hour ?? ''}
              onChange={(e) => updateNumeric('evening_summary_hour', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              В какое время владельцу отправлять итоги дня. По часовому поясу организации.
              Допустимо 0–23.
            </div>
          </div>
        </div>
      )}

      {tab === 'clients' && (
        <div className="card">
          <h2 className="card-title">Статусы клиентов</h2>
          <div className="form-group">
            <label className="form-label">
              Клиент «под риском», если не был, дней
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="365"
              value={settings.client_at_risk_days ?? ''}
              onChange={(e) => updateNumeric('client_at_risk_days', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Если клиент не приходил столько дней — в карточке бейдж «🟡 Под риском».
              Используется в рассылках (сегмент «Под риском»). По умолчанию 30.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">
              Клиент «потерянный», если не был, дней
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="3650"
              value={settings.client_inactive_days ?? ''}
              onChange={(e) => updateNumeric('client_inactive_days', e.target.value)}
              disabled={saving}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Если клиент не приходил столько дней — в карточке бейдж «🔴 Потерянный».
              Используется в рассылках (сегмент «Потерянные»). По умолчанию 90.
            </div>
          </div>
        </div>
      )}

      {tab === 'backfill' && (
        <div className="card">
          <h2 className="card-title">🔥 Горящие окна</h2>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={!!settings.slot_backfill_enabled}
              onChange={(e) => update('slot_backfill_enabled', e.target.checked)}
            />
            <span>Предлагать перенос клиентам, записанным на более позднее время</span>
          </label>

          <div className="form-group" style={{ marginTop: 12 }}>
            <label className="form-label">
              Уведомлять лист ожидания через, минут
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="1440"
              value={settings.slot_backfill_delay_minutes ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_delay_minutes', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Слот сначала висит в свободном доступе (клиент может найти его в Mini App),
              и только через N минут отправляем уведомление в лист ожидания. 0 — сразу.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Ждать реакции листа, минут
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="1440"
              value={settings.slot_backfill_waitlist_wait_minutes ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_waitlist_wait_minutes', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Если через N минут никто из листа не нажал «Записаться» — параллельно
              запускаем backfill (предложение переноса клиентам с более поздней записью).
              Кнопки у клиентов из листа остаются рабочими.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Копить слоты пачкой, минут
            </label>
            <input
              className="form-input"
              type="number"
              min="0"
              max="1440"
              value={settings.slot_backfill_batch_minutes ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_batch_minutes', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Если несколько слотов освободились за короткое время, клиенту
              уходит одно сообщение со списком, а не по одному на каждый слот.
              Копим N минут от первого pending-оффера, потом отправляем пачкой.
              0 — отправлять сразу по одному. По умолчанию 15.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Сколько «живёт» неотвеченное предложение, часов
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="720"
              value={settings.slot_backfill_sent_ttl_hours ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_sent_ttl_hours', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Пока клиент не ответил на предложение, новые предложения по его
              заявке не отправляются. Через N часов неотвеченное считается
              «просроченным», и заявка снова может получать предложения.
              По умолчанию 24 часа.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Мин. отрыв освободившегося слота от текущей записи, часов
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="720"
              value={settings.slot_backfill_min_gap_hours ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_min_gap_hours', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Клиент получит предложение переноса, только если освободившийся слот
              как минимум на N часов раньше его текущей записи. Так не предлагаем
              перенос «через 2 часа на тот же день» — это обычно неудобно.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Сколько клиентов опрашивать
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="20"
              value={settings.slot_backfill_max_candidates ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_max_candidates', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              При backfill берём N клиентов с самой близкой подходящей записью
              (по времени). Слишком много — спам; слишком мало — слот останется
              свободным.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              Не дёргать одного клиента чаще, часов
            </label>
            <input
              className="form-input"
              type="number"
              min="1"
              max="168"
              value={settings.slot_backfill_cooldown_hours ?? ''}
              onChange={(e) => updateNumeric('slot_backfill_cooldown_hours', e.target.value)}
              disabled={saving || !settings.slot_backfill_enabled}
            />
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
              Cooldown между backfill-предложениями одному клиенту. Защита от
              усталости. По умолчанию 24 часа.
            </div>
          </div>
        </div>
      )}

      {tab === 'reviews' && (
        <>
          <div className="card">
            <h2 className="card-title">⭐ Отзывы клиентов</h2>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={!!settings.review_request_enabled}
                onChange={(e) => update('review_request_enabled', e.target.checked)}
              />
              <span>Запрашивать отзыв после визита</span>
            </label>

            <div className="form-group" style={{ marginTop: 12 }}>
              <label className="form-label">
                Через сколько часов после визита отправлять запрос
              </label>
              <input
                className="form-input"
                type="number"
                min="1"
                max="168"
                value={settings.review_request_delay_hours ?? ''}
                onChange={(e) => updateNumeric('review_request_delay_hours', e.target.value)}
                disabled={saving || !settings.review_request_enabled}
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Через N часов после визита клиенту придёт сообщение с просьбой
                оценить визит от 1 до 5 звёзд. По умолчанию 2 часа.
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">
                Порог положительной оценки (от 1 до 5)
              </label>
              <input
                className="form-input"
                type="number"
                min="1"
                max="5"
                value={settings.review_positive_threshold ?? 4}
                onChange={(e) => updateNumeric('review_positive_threshold', e.target.value)}
                disabled={saving || !settings.review_request_enabled}
              />
              <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
                Оценки <b>от порога и выше</b> считаются положительными — клиент
                получает ссылки на Яндекс/2ГИС, чтобы оставить отзыв публично.
                Оценки <b>ниже порога</b> отправляются только администратору
                приватно. По умолчанию 4 (т.е. 4 и 5 — позитив, 1–3 — негатив).
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">🗺 Ссылки на карточку организации</h2>
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 12 }}>
              Клиенту после положительной оценки показываются кнопки на эти ссылки.
              Скопируйте URL вашей карточки в Яндекс.Картах и/или 2ГИС. Оставьте
              пустым — если не хотите показывать эту площадку.
            </div>

            <div className="form-group">
              <label className="form-label">Яндекс.Карты</label>
              <input
                className="form-input"
                type="url"
                placeholder="https://yandex.ru/maps/org/..."
                value={settings.review_yandex_url ?? ''}
                onChange={(e) => update('review_yandex_url', e.target.value)}
                disabled={saving || !settings.review_request_enabled}
              />
            </div>

            <div className="form-group">
              <label className="form-label">2ГИС</label>
              <input
                className="form-input"
                type="url"
                placeholder="https://2gis.ru/..."
                value={settings.review_2gis_url ?? ''}
                onChange={(e) => update('review_2gis_url', e.target.value)}
                disabled={saving || !settings.review_request_enabled}
              />
            </div>
          </div>
        </>
      )}

      <div className="save-bar">
        <button className="btn-save" onClick={handleSave} disabled={saving}>
          {saving ? 'Сохранение…' : '💾 Сохранить'}
        </button>
        {saveMsg && <span className="save-msg">{saveMsg}</span>}
      </div>
    </div>
  );
}