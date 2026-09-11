import { useEffect, useState } from 'react'
import api from '../services/api'
import '../css/Modal.css'

function ModalUsuario({ isOpen, onClose, onSave, accessToken }) {
  const [roles, setRoles] = useState([])

  useEffect(() => {
    async function loadRoles() {
      if (!isOpen || !accessToken) return
      try {
        const data = await api.get('/roles', { token: accessToken })
        setRoles(data.filter((r) => r.rol_act))
      } catch (err) {
        console.error("Error al cargar roles:", err)
      }
    }
    loadRoles()
  }, [isOpen, accessToken])

  if (!isOpen) return null

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
            <label className="form-label">Contraseña</label>
            <input name="password" type="password" className="form-input" minLength={8} required />
          </div>
          <div className="form-group">
            <label className="form-label">Iniciales</label>
            <input name="usu_ini" className="form-input" maxLength={4} required />
          </div>
          <div className="form-group">
            <label className="form-label">Rol</label>
            <select name="usu_rol" className="form-input" required>
              {roles.length === 0 && <option value="">Cargando roles...</option>}
              {roles.map((rol) => (
                <option key={rol.rol_cod} value={rol.rol_nom}>{rol.rol_nom}</option>
              ))}
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