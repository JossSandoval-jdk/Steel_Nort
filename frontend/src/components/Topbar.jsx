import { useCallback, useEffect, useState } from 'react'
import avatar from '../assets/icons/avatar_default.png'
import cerrarIcon from '../assets/icons/cerrar_icon.png'
import ModalNotificaciones from './ModalNotificaciones.jsx'
import { useAuth } from '../hooks/useAuth.js'
import '../css/Topbar.css'

/*
 * Topbar: Barra superior de la aplicación.
 * Muestra el perfil del usuario actual (nombre y cargo), la campanita de
 * notificaciones con contador de no leídas, y el botón de cerrar sesión.
 */
function Topbar({ nombre = 'Nombre Usuario', cargo = 'Cargo' }) {
  const { accessToken } = useAuth()
  const [modalAbierto, setModalAbierto] = useState(false)
  const [noLeidas, setNoLeidas] = useState(0)

  // Cuenta las no leídas. Se usa al abrir la app, cada 60 s y cada vez que el
  // modal marca algo como leído (para que el badge no quede desfasado).
  const contar = useCallback(async () => {
    if (!accessToken) return
    try {
      const r = await fetch('/api/v2/notificaciones/contador', {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (!r.ok) return
      const data = await r.json()
      setNoLeidas(data.no_leidas || 0)
    } catch {
      // Silencioso: si falla el polling, no rompemos la UI.
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken) return undefined
    // `consultar` local: el linter solo acepta el setState si la llamada
    // nace dentro del efecto (igual que el sondeo del contador).
    const consultar = async () => { await contar() }
    consultar()
    const id = setInterval(consultar, 60_000)
    return () => clearInterval(id)
  }, [accessToken, contar])

  return (
    <>
      <header className="topbar">
        <div className="topbar-user">
          <img className="topbar-avatar" src={avatar} alt="Avatar" />
          <div className="topbar-info">
            <span className="topbar-nombre">{nombre}</span>
            <span className="topbar-cargo">{cargo}</span>
          </div>
        </div>

        <div className="topbar-acciones">
          <button
            type="button"
            className="topbar-campanita"
            aria-label="Notificaciones"
            title="Notificaciones"
            onClick={() => setModalAbierto(true)}
          >
            🔔
            {noLeidas > 0 && (
              <span className="topbar-badge">{noLeidas > 99 ? '99+' : noLeidas}</span>
            )}
          </button>

          <button
            type="button"
            className="topbar-cerrar"
            aria-label="Cerrar sesión"
          >
            <img src={cerrarIcon} alt="" />
          </button>
        </div>
      </header>

      <ModalNotificaciones
        abierto={modalAbierto}
        onCerrar={() => setModalAbierto(false)}
        onLeidas={contar}
      />
    </>
  )
}

export default Topbar