import { createContext } from 'react'

var NavContext = createContext({ page: 'lab', params: {}, navigate: function() {} });

export { NavContext }
