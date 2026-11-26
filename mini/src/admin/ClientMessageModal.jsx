import { useRef, useState } from 'react';
import { adminApi } from './adminApi.js';

const IMAGE_MIMES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'];
const ALLOWED_MIMES = [
  'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
  'application/pdf', 'text/plain', 'text/csv',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
];

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export default function ClientMessageModal({ orgId, userId, clientName, onClose }) {
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(null);
  const fileInputRef = useRef(null);

  function handleFileChange(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setError('');
    if (!ALLOWED_MIMES.includes(f.type)) {
      setError(`Формат ${f.type || 'unknown'} не поддерживается`);
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError('Файл больше 10 МБ');
      return;
    }
    setFile(f);
    if (IMAGE_MIMES.includes(f.type)) {
      setPreview(URL.createObjectURL(f));
    } else {
      setPreview(null);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function clearFile() {
    setFile(null);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
  }

  async function handleSend() {
    if (!text.trim() && !file) return;
    setBusy(true);
    setError('');
    try {
      const r = await adminApi.sendClientMessageWithFile(orgId, userId, text, file);
      setSuccess(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (success) {
    const st = success.status;
    let title = '✅ Отправлено';
    let desc = `Сообщение доставлено клиенту ${clientName || userId}.`;
    if (st === 'no_max') {
      title = '⚠️ У клиента нет MAX';
      desc = 'У клиента нет профиля в MAX. Свяжитесь по телефону.';
    } else if (st === 'blocked') {
      title = '⚠️ Клиент заблокировал бота';
      desc = 'Сообщение не доставлено. Сообщение не доставлено: клиент закрыл личные сообщения (MAX) или сообщения сообщества (VK).';
    } else if (st === 'error' && success.full_url) {
      title = '⚠️ Не удалось отправить в чат';
      desc = 'Файл сохранён на сервере. Ссылка для скачивания ниже.';
    } else if (st === 'error') {
      title = '❌ Ошибка отправки';
      desc = success.error || 'Неизвестная ошибка.';
    }

    return (
      <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 200 }}>
        <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 500 }}>
          <h2 className="card-title">{title}</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>{desc}</p>

          {success.full_url && (
            <div style={{
              background: 'var(--bg)', padding: 12, borderRadius: 8,
              fontSize: 13, wordBreak: 'break-all', marginBottom: 12,
            }}>
              <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>Ссылка:</div>
              <a href={success.full_url} target="_blank" rel="noopener noreferrer"
                 style={{ color: 'var(--primary)' }}>
                {success.full_url}
              </a>
            </div>
          )}

          <div className="actions" style={{ marginTop: 16 }}>
            <button className="btn-action confirm" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()} style={{ zIndex: 200 }}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
        <h2 className="card-title">✉️ Написать клиенту</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0, marginBottom: 12 }}>
          {clientName || userId}
        </p>

        <div className="form-group">
          <label className="form-label">Текст (поддерживает markdown)</label>
          <textarea
            className="form-input"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Добрый день! Направляем вам документы..."
            disabled={busy}
            maxLength={4000}
          />
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            {text.length} / 4000
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Файл (опционально)</label>

          {!file && (
            <button
              type="button"
              className="btn-generate"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              📎 Прикрепить файл
            </button>
          )}

          <input
            ref={fileInputRef}
            type="file"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />

          {file && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: 10, background: 'var(--bg)', borderRadius: 8,
            }}>
              {preview && (
                <img
                  src={preview}
                  alt="preview"
                  style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 6 }}
                />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {file.name}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {humanSize(file.size)}
                  {IMAGE_MIMES.includes(file.type) && ' · сожмётся автоматически'}
                </div>
              </div>
              <button
                type="button"
                className="dir-btn danger"
                onClick={clearFile}
                disabled={busy}
                title="Убрать файл"
              >✕</button>
            </div>
          )}

          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
            Изображения, PDF, TXT, CSV, DOC/DOCX, XLS/XLSX. До 10 МБ.
          </div>
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn-action confirm" onClick={handleSend} disabled={busy || (!text.trim() && !file)}>
            {busy ? 'Отправка…' : '✉️ Отправить'}
          </button>
          <button className="btn-action reject" onClick={onClose} disabled={busy}>Отмена</button>
        </div>
      </div>
    </div>
  );
}