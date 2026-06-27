import { createContext, useContext } from 'react'
import { NodeRegistry } from './NodeRegistry'

const RegistryContext = createContext<NodeRegistry | null>(null)

export const RegistryProvider = RegistryContext.Provider

export function useRegistry(): NodeRegistry {
  const reg = useContext(RegistryContext)
  if (!reg) throw new Error('useRegistry must be used within RegistryProvider')
  return reg
}
