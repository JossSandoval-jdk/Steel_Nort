// frontend/src/components/UserRolesModal.jsx
import { useEffect, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import '../css/RolesPermisos.css';

/**
 * Modal that lets the admin assign / remove roles for a specific user.
 * Props:
 *   - isOpen (boolean)   : show/hide modal
 *   - onClose (func)     : callback to close modal
 *   - user (object)      : user object {usu_cod, usu_nom, ...}
 */
export default function UserRolesModal({ isOpen, onClose, user }) {
  const { accessToken } = useAuth();
  const [roles, setRoles] = useState([]); // all available roles
  const [userRoles, setUserRoles] = useState(new Set()); // role ids assigned to user
  const [mensaje, setMensaje] = useState(null);
  const [error, setError] = useState(null);

  // Load all roles and the roles for this user when modal opens
  useEffect(() => {
    if (!isOpen || !user) return;
    let mounted = true;
    async function load() {
      try {
        const allRoles = await api.get('/roles', { token: accessToken });
        const userRolesData = await api.get(`/usuarios/${user.usu_cod}/roles`, { token: accessToken });
        if (!mounted) return;
        setRoles(allRoles);
        setUserRoles(new Set(userRolesData.map(r => r.rol_cod)));
      } catch (err) {
        if (mounted) setError(`Error al cargar roles: ${err.message}`);
      }
    }
    load();
    return () => { mounted = false; };
  }, [isOpen, user, accessToken]);

  const toggleRole = async (rolId, checked) => {
    const newSet = new Set(userRoles);
    if (checked) newSet.add(rolId); else newSet.delete(rolId);
    setUserRoles(newSet);
    try {
      await api.post(`/usuarios/${user.usu_cod}/roles`, { rol_ids: Array.from(newSet) }, { token: accessToken });
      setMensaje('Roles actualizados');
      setError(null);
    } catch (err) {
      setError(`No se pudo actualizar roles: ${err.message}`);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>Asignar roles a {user?.usu_nom}</h3>
        {mensaje && <div className="rp-toast success">{mensaje}</div>}
        {error && <div className="rp-toast error">{error}</div>}
        <table className="roles-table">
          <thead>
            <tr>
              <th>Rol</th>
              <th>Descripción</th>
              <th style={{ textAlign: 'center' }}>Asignado</th>
            </tr>
          </thead>
          <tbody>
            {roles.map(r => (
              <tr key={r.rol_cod}>
                <td>{r.rol_nom}</td>
                <td>{r.rol_desc || '—'}</td>
                <td style={{ textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={userRoles.has(r.rol_cod)}
                    onChange={e => toggleRole(r.rol_cod, e.target.checked)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

