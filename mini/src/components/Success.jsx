export default function Success({ result, onReset }) {
  return (
    <div className="card">
      <div className="success">
        <div className="success-icon">✓</div>
        <h2>Заявка принята</h2>
        <p>
          Номер заявки: <strong>#{result.id}</strong>
          <br />
          Администратор свяжется с вами для подтверждения.
        </p>
        <div style={{ marginTop: 24 }}>
          <button className="btn btn-link" onClick={onReset}>
            Записаться ещё раз
          </button>
        </div>
      </div>
    </div>
  );
}