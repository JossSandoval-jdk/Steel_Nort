// frontend/src/components/UserRolesModal.jsx
import { useEffect, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import '../css/RolesPermisos.css';

/**
 * Modal para cambiar el rol de un usuario.
 *
 * En la v1 el usuario podia tener varios roles a la vez. La v2 no: la tabla
 * usuarios tiene una sola FK rol_cod, asi que el rol se elige de una lista y
 * se guarda con PATCH /acceso/usuarios/{cod} { rol_cod }. Por eso no hay
 * casillas sino un <select>, y no existe /usuarios/{cod}/roles.
 */
export default function UserRolesModal({ isOpen, onClose, user, onGuardado }) {
  const { accessToken } = useAuth();
  const [roles, setRoles] = useState([]);      // todos los roles activos
  const [rolElegido, setRolElegido] = useState(''); // rol_cod como texto
  const [mensaje, setMensaje] = useState(null);
  const [error, setError] = useState(null);
  const [guardando, setGuardando] = useState(false);

  // Carga los roles disponibles y preselecciona el que ya tiene el usuario.
  useEffect(() => {
    if (!isOpen || !user) return;
    let mounted = true;
    async function load() {
      try {
        const respuesta = await api.get('/acceso/roles?tamano=100&con_bajas=false', { token: accessToken });
        if (!mounted) return;
        setRoles(respuesta?.items || []);
        setRolElegido(user.rol_cod != null ? String(user.rol_cod) : '');
        setError(null);
      } catch (err) {
        if (mounted) setError(`Error al cargar roles: ${err.message}`);
      }
    }
    load();
    return () => { mounted = false; };
  }, [isOpen, user, accessToken]);

  async function guardar() {
    if (rolElegido === '') return;
    setGuardando(true);
    try {
      await api.patch(`/acceso/usuarios/${user.usu_cod}`, { rol_cod: Number(rolElegido) }, { token: accessToken });
      setMensaje('Rol actualizado');
      setError(null);
      if (onGuardado) onGuardado();
    } catch (err) {
      setError(`No se pudo actualizar el rol: ${err.message}`);
    } finally {
      setGuardando(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>Rol de {user?.usu_nom}</h3>
        {mensaje && <div className="rp-toast success">{mensaje}</div>}
        {error && <div className="rp-toast error">{error}</div>}

        <div className="field-stack">
          <label className="info-label" htmlFor="rol-usuario">Rol asignado</label>
          <select
            id="rol-usuario"
            className="text-input"
            value={rolElegido}
            onChange={e => setRolElegido(e.target.value)}
            disabled={guardando}
          >
            <option value="">— sin asignar —</option>
            {roles.map(r => (
              <option key={r.rol_cod} value={r.rol_cod}>{r.rol_nom}</option>
            ))}
          </select>
        </div>

        <div className="card-foot">
          <button
            type="button"
            className="btn btn-primary"
            onClick={guardar}
            disabled={guardando || rolElegido === ''}
          >
            {guardando ? 'Guardando…' : 'Guardar rol'}
          </button>
        </div>
      </div>
    </div>
  );
}