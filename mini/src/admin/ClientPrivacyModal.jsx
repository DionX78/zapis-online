import { useState } from 'react';
import { adminApi } from './adminApi.js';

export default function ClientPrivacyModal({ orgId, userId, clientName, onClose, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState('main');

  async function handleDelete() {
    setBusy(true);
    setError('');
    try {
      const r = await adminApi.deleteClient(orgId, userId);
      if (onDeleted) onDeleted(r);
      onClose();
    } catch (e) {
      setError('Ошибка удаления: ' + e.message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()} style={{ zIndex: 200 }}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
        <h2 className="card-title">🔒 Удаление данных (152-ФЗ)</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
          {clientName || userId}
        </p>

        {step === 'main' && (
          <>
            <div style={{ fontSize: 14, lineHeight: 1.5, marginBottom: 16 }}>
              По закону 152-ФЗ клиент имеет право потребовать удаления своих
              персональных данных. Эта операция необратима.
            </div>

            <div
              style={{
                padding: '10px 12px',
                background: 'var(--primary-soft)',
                borderRadius: 8,
                fontSize: 13,
                color: 'var(--primary)',
                lineHeight: 1.5,
                marginBottom: 16,
              }}
            >
              📄 Нужна копия данных для клиента? Отправьте её через
              «📥 Экспорт» → «📨 Клиенту» → PDF или XLSX.
            </div>

            <div className="actions" style={{ flexDirection: 'column', gap: 8 }}>
              <button type="button" className="btn-action reject" onClick={() => setStep('confirm_delete')} disabled={!!busy}>
                🗑 Удалить данные клиента
              </button>
              <button type="button" className="btn-action" onClick={onClose} disabled={!!busy}>
                Отмена
              </button>
            </div>

            {error && <div className="form-error" style={{ marginTop: 12 }}>{error}</div>}
          </>
        )}

        {step === 'confirm_delete' && (
          <>
            <div className="create-req-notify-hint create-req-notify-err" style={{ marginBottom: 16, lineHeight: 1.5 }}>
              <b>Будут удалены безвозвратно:</b>
              <ul style={{ marginTop: 6, paddingLeft: 20 }}>
                <li>ФИО, телефон, пол, дата рождения</li>
                <li>Согласие на обработку ПД и метка маркетинговой подписки</li>
                <li>Любимый специалист</li>
                <li>История взаимодействий с ботом</li>
              </ul>

              <b style={{ display: 'block', marginTop: 12 }}>Что произойдёт с записями:</b>
              <ul style={{ marginTop: 6, paddingLeft: 20 }}>
                <li>Активные записи (ожидают / подтверждены) — <b>отменяются</b>,
                    слоты освобождаются.</li>
                <li>Прошедшие записи — <b>остаются в истории</b>, но
                    без ФИО и телефона (обезличиваются).</li>
              </ul>

              <b style={{ display: 'block', marginTop: 12 }}>Что НЕ пострадает:</b>
              <ul style={{ marginTop: 6, paddingLeft: 20 }}>
                <li>Общая выручка клиники</li>
                <li>Количество приёмов и статистика по услугам</li>
                <li>Финансовая отчётность за прошлые периоды</li>
              </ul>

              <div style={{ marginTop: 12, fontSize: 12, opacity: 0.85 }}>
                В карточке бывшей заявки ФИО и телефон станут пустыми — это
                ожидаемо. Сумма визита, услуга, дата и статус сохранятся.
              </div>
            </div>

            <div className="actions" style={{ flexDirection: 'column', gap: 8 }}>
              <button type="button" className="btn-action reject" onClick={handleDelete} disabled={!!busy}>
                {busy ? 'Удаление…' : '🗑 Да, удалить навсегда'}
              </button>
              <button type="button" className="btn-action" onClick={() => setStep('main')} disabled={!!busy}>
                ← Назад
              </button>
            </div>

            {error && <div className="form-error" style={{ marginTop: 12 }}>{error}</div>}
          </>
        )}
      </div>
    </div>
  );
}