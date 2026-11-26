import { useEffect, useState } from 'react';
import { adminApi } from './adminApi.js';

// Модальное окно редактирования/добавления VK-бота
function BotEditModal({ bot, orgId, onClose, onSave, busy }) {
  const [formData, setFormData] = useState(
    bot || {
      platform: 'vk',
      group_id: '',
      token: '',
      confirmation_code: '',
      title: '',
    }
  );
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [checking, setChecking] = useState(false);

  // Обновить formData, когда bot prop изменяется
  useEffect(() => {
    if (bot) {
      setFormData({
        platform: bot.platform || 'vk',
        group_id: bot.group_id || '',
        token: bot.token || '',
        confirmation_code: bot.confirmation_code || '',
        title: bot.title || '',
      });
    } else {
      setFormData({
        platform: 'vk',
        group_id: '',
        token: '',
        confirmation_code: '',
        title: '',
      });
    }
    setError('');
    setMsg('');
  }, [bot]);

  function handleChange(field, value) {
    setFormData((f) => ({ ...f, [field]: value }));
    setError('');
  }

  async function checkToken() {
    if (!formData.token.trim()) {
      setError('Введите токен');
      return;
    }
    if (formData.platform === 'vk' && !formData.group_id.trim()) {
      setError('Укажите ID сообщества VK');
      return;
    }

    setChecking(true);
    setError('');
    setMsg('');
    try {
      const payload = {
        platform: formData.platform,
        token: formData.token.trim(),
        group_id: formData.group_id.trim() || undefined,
      };
      const data = await adminApi.checkBotToken(orgId, payload);
      setMsg(`✅ ${data.message}`);
      if (data.bot_name && !formData.title) {
        setFormData((f) => ({ ...f, title: data.bot_name }));
      }
    } catch (e) {
      setError('❌ ' + e.message);
    } finally {
      setChecking(false);
    }
  }

  async function handleSave() {
    if (!formData.platform) {
      setError('Выберите платформу');
      return;
    }
    if (!formData.token.trim()) {
      setError('Введите токен');
      return;
    }
    if (formData.platform === 'vk') {
      if (!formData.group_id.trim()) {
        setError('Укажите ID сообщества VK');
        return;
      }
      if (!formData.confirmation_code.trim()) {
        setError('Введите confirmation code для webhook');
        return;
      }
    }

    await onSave(formData);
  }

  return (
    <div className='modal-backdrop' onClick={() => !busy && !checking && onClose()}>
      <div className='modal' onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
        <h2 className='card-title'>{bot ? '✏️ Редактировать VK-бот' : '➕ Добавить VK-бот'}</h2>

        <div className='form-group'>
          <label className='form-label'>Платформа</label>
          <select
            className='form-input'
            value={formData.platform}
            onChange={(e) => handleChange('platform', e.target.value)}
            disabled={busy || !!bot}
          >
            <option value='vk'>VK (Вконтакте)</option>
          </select>
        </div>

        <div className='form-group'>
          <label className='form-label'>ID сообщества VK *</label>
          <input
            className='form-input'
            type='text'
            placeholder='Например: 168839913'
            value={formData.group_id}
            onChange={(e) => handleChange('group_id', e.target.value)}
            disabled={busy}
          />
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Найдите в адресе сообщества: vk.com/club<b>123456</b> → 123456
          </div>
        </div>

        <div className='form-group'>
          <label className='form-label'>Токен сообщества (Callback API) *</label>
          <input
            className='form-input'
            type='password'
            placeholder='Получите в настройках сообщества → API → Ключи доступа'
            value={formData.token}
            onChange={(e) => handleChange('token', e.target.value)}
            disabled={busy}
          />
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Токен сообщества (не пользовательский!) из раздела Callback API.
            Доступ: 📲 Управление сообществом → Работа с API → Ключи доступа.
          </div>
        </div>

        <div className='form-group'>
          <label className='form-label'>Confirmation Code *</label>
          <input
            className='form-input'
            type='text'
            placeholder='Случайная строка для подтверждения webhook'
            value={formData.confirmation_code}
            onChange={(e) => handleChange('confirmation_code', e.target.value)}
            disabled={busy}
          />
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Любая строка (цифры, буквы). При первом запросе от ВК наш сервер вернёт её обратно для подтверждения адреса.
            Это требуется ВК для проверки, что сервер контролирует этот адрес.
          </div>
        </div>

        <div className='form-group'>
          <label className='form-label'>Название бота (опционально)</label>
          <input
            className='form-input'
            type='text'
            placeholder='Например: Записи клиники'
            value={formData.title}
            onChange={(e) => handleChange('title', e.target.value)}
            disabled={busy}
          />
        </div>

        {bot && bot.webhook_secret && (
          <div className='form-group'>
            <label className='form-label'>Секрет вебхука</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                className='form-input'
                type='text'
                value={bot.webhook_secret}
                readOnly
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
              <button
                type='button'
                className='btn-action'
                onClick={() => navigator.clipboard && navigator.clipboard.writeText(bot.webhook_secret)}
                title='Скопировать'
              >
                📋
              </button>
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
              Секрет для подписи вебхуков. Кнопка «🔌» в списке ботов регистрирует
              Callback-адрес в VK сама — вручную ничего вводить не нужно.
            </div>
          </div>
        )}

        {error && (
          <div
            style={{
              backgroundColor: '#ffebee',
              color: '#c62828',
              padding: 8,
              borderRadius: 4,
              fontSize: 13,
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}

        {msg && (
          <div
            style={{
              backgroundColor: '#e8f5e9',
              color: '#2e7d32',
              padding: 8,
              borderRadius: 4,
              fontSize: 13,
              marginBottom: 12,
            }}
          >
            {msg}
          </div>
        )}

        <div className='actions' style={{ marginTop: 16, flexWrap: 'wrap' }}>
          <button
            type='button'
            className='btn-action confirm'
            onClick={handleSave}
            disabled={busy || !formData.token}
            style={{ flex: 1, minWidth: 140 }}
          >
            {busy ? '⏳ Сохранение…' : '💾 Сохранить'}
          </button>
          <button
            type='button'
            className='btn-action'
            onClick={checkToken}
            disabled={busy || checking}
            style={{ flex: 1, minWidth: 140 }}
          >
            {checking ? '⏳ Проверка…' : '✓ Проверить токен'}
          </button>
          <button
            type='button'
            className='btn-action reject'
            onClick={onClose}
            disabled={busy || checking}
            style={{ flex: '0 0 80px' }}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ChannelsPage({ orgId }) {
  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');
  const [bots, setBots] = useState([]);
  const [showEditModal, setShowEditModal] = useState(null); // null | 'add' | bot_id
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadBots();
  }, [orgId]);

  async function loadBots() {
    try {
      setStep('loading');
      const data = await adminApi.getBots(orgId);
      setBots(data.bots || []);
      setStep('ready');
    } catch (e) {
      setError(e.message);
      setStep('error');
    }
  }

  async function handleSaveBot(formData) {
    setBusy(true);
    setError('');
    try {
      if (showEditModal === 'add') {
        // Добавить новый бот
        const payload = {
          platform: formData.platform,
          token: formData.token.trim(),
          group_id: formData.group_id.trim() || undefined,
          title: formData.title.trim() || undefined,
        };
        await adminApi.addBot(orgId, payload);
      } else {
        // Обновить существующий бот
        const botId = showEditModal;
        const payload = {
          title: formData.title,
          token: formData.token,
          group_id: formData.group_id,
          confirmation_code: formData.confirmation_code,
        };
        await adminApi.updateBot(orgId, botId, payload);
      }
      await loadBots();
      setShowEditModal(null);
      setError('✅ Бот сохранён успешно!');
      setTimeout(() => setError(''), 3000);
    } catch (e) {
      setError('❌ Ошибка: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleBotStatus(botId, currentEnabled) {
    try {
      await adminApi.updateBot(orgId, botId, { enabled: !currentEnabled });
      await loadBots();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDeleteBot(botId) {
    if (!confirm('Вы уверены? Это нельзя отменить.')) return;
    try {
      await adminApi.deleteBot(orgId, botId);
      await loadBots();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleRegisterCallback(botId) {
    setBusy(true);
    setError('');
    try {
      const data = await adminApi.registerCallback(orgId, botId);
      setError('✅ ' + (data.message || 'Callback зарегистрирован'));
      await loadBots();
      setTimeout(() => setError(''), 5000);
    } catch (e) {
      setError('❌ ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  if (step === 'loading') {
    return <div style={{ padding: 16 }}>⏳ Загрузка каналов…</div>;
  }

  if (step === 'error') {
    return <div style={{ padding: 16, color: '#d32f2f' }}>❌ Ошибка: {error}</div>;
  }

  const maxBots = bots.filter((b) => b.platform === 'max');
  const vkBots = bots.filter((b) => b.platform === 'vk');

  return (
    <div>
      <div className='card'>
        <h2 className='card-title'>🤖 Каналы связи</h2>
        <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 16 }}>
          Здесь вы управляете ботами — одним для MAX и несколькими для VK.
          Каждому боту нужен свой токен. Клиенты получают уведомления через подключенные каналы.
        </div>

        {/* MAX BOTS */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>📱 MAX</h3>
          {maxBots.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {maxBots.map((bot) => (
                <div
                  key={bot.id}
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: 8,
                    padding: 12,
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    rowGap: 8,
                  }}
                >
                  <div style={{ flex: '1 1 100%', minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{bot.title || bot.slug}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      ID: {bot.id} | org_id: {bot.org_id}
                    </div>
                  </div>
                  <label className='checkbox-row' style={{ margin: 0 }}>
                    <input
                      type='checkbox'
                      checked={bot.enabled}
                      onChange={() => handleToggleBotStatus(bot.id, bot.enabled)}
                    />
                    <span>{bot.enabled ? '✅' : '⬜'}</span>
                  </label>
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                color: 'var(--text-muted)',
                fontSize: 13,
                padding: 12,
                backgroundColor: 'var(--bg-muted)',
                borderRadius: 4,
              }}
            >
              Нет активных ботов MAX. MAX Bot настраивается автоматически при создании организации.
            </div>
          )}
        </div>

        {/* VK BOTS */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>🎵 VK (Вконтакте)</h3>
          {vkBots.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {vkBots.map((bot) => (
                <div
                  key={bot.id}
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: 8,
                    padding: 12,
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    rowGap: 8,
                  }}
                >
                  <div style={{ flex: '1 1 100%', minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{bot.title || bot.slug}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      ID: {bot.id} | Сообщество: {bot.group_id || '—'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                      Статус: {bot.enabled ? '✅ активен' : '⬜ отключен'}
                    </div>
                    {bot.token ? (
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                        ✓ Токен: {bot.token.substring(0, 10)}…
                      </div>
                    ) : (
                      <div style={{ fontSize: 12, color: '#d32f2f', marginTop: 2 }}>
                        ⚠️ Токен не установлен
                      </div>
                    )}
                  </div>
                  <div className='upcoming-item-actions'>
                    <button
                      className='dir-btn'
                      onClick={() => handleRegisterCallback(bot.id)}
                      title='Зарегистрировать Callback в VK'
                    >
                      🔌
                    </button>
                    <button
                      className='dir-btn'
                      onClick={() => setShowEditModal(bot.id)}
                      title='Редактировать'
                    >
                      ✏️
                    </button>
                    <button
                      className='dir-btn'
                      onClick={() => handleToggleBotStatus(bot.id, bot.enabled)}
                      title={bot.enabled ? 'Отключить' : 'Включить'}
                    >
                      {bot.enabled ? '🔴' : '🟢'}
                    </button>
                    <button
                      className='dir-btn danger'
                      onClick={() => handleDeleteBot(bot.id)}
                      title='Удалить'
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                color: 'var(--text-muted)',
                fontSize: 13,
                padding: 12,
                backgroundColor: 'var(--bg-muted)',
                borderRadius: 4,
              }}
            >
              Нет подключённых ботов VK.
            </div>
          )}
          <button
            className='btn-generate'
            onClick={() => setShowEditModal('add')}
            style={{ marginTop: 12 }}
          >
            ➕ Добавить VK-бот
          </button>
        </div>
      </div>

      {/* EDIT MODAL */}
      {showEditModal !== null && (
        <BotEditModal
          bot={showEditModal === 'add' ? null : bots.find((b) => b.id === showEditModal)}
          orgId={orgId}
          onClose={() => setShowEditModal(null)}
          onSave={handleSaveBot}
          busy={busy}
        />
      )}
    </div>
  );
}
