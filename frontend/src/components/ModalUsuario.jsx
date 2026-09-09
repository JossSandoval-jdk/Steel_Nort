import '../css/Modal.css';

function ModalUsuario({ isOpen, onClose, onSave }) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-head">
          <h3 className="modal-title">Crear nuevo usuario</h3>
        </div>
        <form onSubmit={(e) => {
          e.preventDefault();
          const formData = new FormData(e.target);
          onSave(Object.fromEntries(formData));
        }}>
          <div className="form-group">
            <label className="form-label">Nombre</label>
            <input name="usu_nom" className="form-input" required />
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input name="usu_ema" type="email" className="form-input" required />
          </div>
          <div className="form-group">
            <label className="form-label">Rol</label>
            <select name="usu_rol" className="form-input">
              <option value="Usuario">Usuario</option>
              <option value="Administrador">Administrador</option>
            </select>
          </div>
          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn btn-outline">Cancelar</button>
            <button type="submit" className="btn btn-primary">Guardar</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ModalUsuario;

