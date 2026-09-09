// Contexto de autenticacion del frontend (estado global de sesion).
//
// Estrategia de seguridad del token:
//   - access_token (JWT): se mantiene SOLO en memoria (no en
//     localStorage) para minimizar superficie de exposicion. Al
//     recargar la pagina se pierde y hay que volver a autenticarse.
//   - csrf_token: se guarda en localStorage (clave 'steelnort_csrf');
//     no es secreto de sesion por si solo, se usa para la validacion
//     de doble coincidencia en requests de escritura.
//
// Provee a toda la aplicacion: usuario autenticado, estado de carga,
// y funciones login()/logout(). Escalable: aqui se conectan los demas
// modulos que necesiten conocer al usuario actual.
import { createContext, useCallback, useContext, useState } from 'react'
import api from '../services/api.js'
import { STORAGE_KEYS } from '../config.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // usuario: objeto devuelto por el backend o null si no hay sesion.
  const [user, setUser] = useState(null)
  // accessToken se almacena SOLO en memoria.
  const [accessToken, setAccessToken] = useState(null)
  // Estado de carga para saber si el login esta en curso.
  const [loading, setLoading] = useState(false)

  // Inicia sesion llamando al backend y persistiendo los tokens.
  const login = useCallback(async ({ email, password }) => {
    setLoading(true)
    try {
      const data = await api.post('/auth/login', { email, password })
      // Guarda el access token en memoria.
      setAccessToken(data.access_token)
      // Guarda el csrf token en localStorage.
      localStorage.setItem(STORAGE_KEYS.csrf, data.csrf_token)
      setUser(data.usuario)
      return data.usuario
    } finally {
      setLoading(false)
    }
  }, [])

  // Cierra sesion notificando al backend y limpiando el estado local.
  const logout = useCallback(async () => {
    try {
      const csrf = api.getCsrfToken()
      await api.post('/auth/logout', {}, { token: accessToken, csrf })
    } catch {
      // Si falla el servidor, igual limpiamos el estado local.
    } finally {
      setAccessToken(null)
      setUser(null)
      localStorage.removeItem(STORAGE_KEYS.csrf)
    }
  }, [accessToken])

  const value = {
    user,
    accessToken,
    loading,
    login,
    logout,
    isAuthenticated: Boolean(accessToken && user),
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Hook de acceso comodo al contexto.
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return ctx
}