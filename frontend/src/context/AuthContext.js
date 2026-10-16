// Objeto del contexto de autenticacion.
//
// Vive en su propio modulo (solo contexto, sin componentes ni hooks) para que
// el provider y el hook useAuth puedan compartirlo sin romper el Fast Refresh.
import { createContext } from 'react'

export const AuthContext = createContext(null)
