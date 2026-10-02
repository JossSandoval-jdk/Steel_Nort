// Contexto de autenticacion del frontend (estado global de sesion).
//
// Como funciona en la v2:
//   - access_token (JWT): vive SOLO en memoria, en este archivo. Al recargar
//     la pagina se pierde y hay que volver a iniciar sesion. No se guarda en
//     localStorage ni en sessionStorage.
//   - el backend devuelve ademas "rol" y "permisos" (lista de "modulo:accion").
//     Esos permisos son los que decide que pantallas y que botones ve cada
//     uno; se guardan aqui para no tener que pedirlos en cada pantalla.
//   - la v2 no usa token CSRF: el JWT va en la cabecera "Authorization", que el
//     navegador no envia solo, asi que no hace falta la doble coincidencia.
//
// Provee: user, accessToken, rol, permisos, loading, login(), logout(),
// isAuthenticated y tiene(permiso).
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import api from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // Usuario devuelto por el backend, o null si no hay sesion.
  const [user, setUser] = useState(null)
  // JWT: solo en memoria.
  const [accessToken, setAccessToken] = useState(null)
  // Rol y permisos que decide que ve cada uno.
  const [rol, setRol] = useState('')
  const [permisos, setPermisos] = useState([])
  // Estado de carga del login.
  const [loading, setLoading] = useState(false)

  // Inicia sesion. El backend espera { usuario, clave } (usuario = usu_log,
  // no el correo) y devuelve el token con los datos del usuario y sus
  // permisos.
  const login = useCallback(async ({ usuario, clave }) => {
    setLoading(true)
    try {
      const data = await api.post('/auth/login', { usuario, clave })
      setAccessToken(data.access_token)
      setUser(data.usuario)
      setRol(data.rol)
      // El Administrador trae ["*:*"] porque puede hacer todo.
      setPermisos(data.permisos || [])
      return data.usuario
    } finally {
      setLoading(false)
    }
  }, [])

  // Cierra sesion en el backend y limpia el estado local.
  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout', {}, { token: accessToken })
    } catch {
      // Si el servidor no responde, igual se limpia el estado local.
    } finally {
      setAccessToken(null)
      setUser(null)
      setRol('')
      setPermisos([])
    }
  }, [accessToken])

  // Comprueba si el usuario actual tiene un permiso ("modulo:accion").
  // El Administrador lo tiene todo, por eso el "*:*".
  const tiene = useCallback(
    (permiso) => permisos.includes('*:*') || permisos.includes(permiso),
    [permisos],
  )

  const value = useMemo(
    () => ({
      user,
      accessToken,
      rol,
      permisos,
      loading,
      login,
      logout,
      tiene,
      esAdmin: permisos.includes('*:*'),
      isAuthenticated: Boolean(accessToken && user),
    }),
    [user, accessToken, rol, permisos, loading, login, logout, tiene],
  )

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
