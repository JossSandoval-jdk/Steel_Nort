import { usePushSubscription } from '../hooks/usePushSubscription.js'
import { useAuth } from '../context/AuthContext.jsx'
import '../css/ModalNotificaciones.css'

export default function ModalNotificaciones({ abierto, onCerrar }) {
  const { accessToken } = useAuth()
  const { soportado, permiso, suscrito, cargando, error, suscribir, desuscribir } = usePushSubscription()

  if (!abierto) return null

  const activar = async () => {
    const sub = await suscribir(accessToken)
    if (sub) onCerrar()
  }

  const desactivar = async () => {
    await desuscribir(accessToken)
  }

  return (
    <div className="modal-notif-fondo" onClick={onCerrar}>
      <div className="modal-notif-caja" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-notif-titulo">🔔 Notificaciones de escritorio</h2>

        {!soportado && (
          <p className="modal-notif-mensaje error">
            Este navegador no soporta notificaciones push. Prueba con Chrome, Edge o Firefox actualizado.
          </p>
        )}

        {soportado && !suscrito && (
          <>
            <p className="modal-notif-mensaje">
              Activa las notificaciones para recibir alertas al instante,
              incluso cuando esta pestaña esté cerrada.
            </p>
            <p className="modal-notif-detalle">
              Te avisaremos de anomalías críticas (severidad <strong>C</strong> o <strong>A</strong>) con:
            </p>
            <ul className="modal-notif-lista">
              <li>🔴 Notificación de escritorio nativa</li>
              <li>📱 Funciona en PC y móvil</li>
              <li>🔒 Puedes desactivarlo cuando quieras</li>
            </ul>
          </>
        )}

        {soportado && suscrito && (
          <p className="modal-notif-mensaje exito">
            ✅ Ya estás suscrito. Recibirás las alertas en este dispositivo.
          </p>
        )}

        {error && <p className="modal-notif-mensaje error">{error}</p>}

        {permiso === 'denied' && (
          <p className="modal-notif-mensaje error">
            Has denegado las notificaciones antes. Para activarlas, ve a la configuración del navegador → Privacidad → Notificaciones → Permitir para este sitio.
          </p>
        )}

        <div className="modal-notif-acciones">
          {!suscrito && soportado && (
            <>
              <button type="button" className="modal-notif-btn secundario" onClick={onCerrar}>
                Ahora no
              </button>
              <button
                type="button"
                className="modal-notif-btn primario"
                onClick={activar}
                disabled={cargando || permiso === 'denied'}
              >
                {cargando ? 'Activando…' : 'Activar notificaciones'}
              </button>
            </>
          )}
          {suscrito && (
            <>
              <button type="button" className="modal-notif-btn secundario" onClick={onCerrar}>
                Cerrar
              </button>
              <button
                type="button"
                className="modal-notif-btn peligro"
                onClick={desactivar}
                disabled={cargando}
              >
                {cargando ? 'Desactivando…' : 'Desactivar'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}