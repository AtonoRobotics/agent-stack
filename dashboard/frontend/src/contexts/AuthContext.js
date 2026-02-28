import { createContext } from 'react'

var AuthContext = createContext({ user: null, token: null, logout: function() {} });

export { AuthContext }
