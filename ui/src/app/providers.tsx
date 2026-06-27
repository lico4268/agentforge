import { useEffect, useMemo, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { NodeRegistry } from '@/registry/NodeRegistry'
import { RegistryProvider } from '@/registry/RegistryContext'
import { loadManifests } from '@/registry/loadManifests'
import { TransportProvider } from '@/transport/TransportContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { STARTER_ARCHITECTURE } from './starterArchitecture'

const queryClient = new QueryClient()

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <RegistryGate>
        <TransportProvider>{children}</TransportProvider>
      </RegistryGate>
    </QueryClientProvider>
  )
}

/** Loads the node registry, then exposes it + preloads a starter graph. */
function RegistryGate({ children }: { children: ReactNode }) {
  const { data: manifests } = useQuery({
    queryKey: ['manifests'],
    queryFn: loadManifests,
    staleTime: Infinity,
  })

  const registry = useMemo(
    () => (manifests ? new NodeRegistry(manifests) : null),
    [manifests],
  )

  const loadArchitecture = useGraphStore((s) => s.loadArchitecture)
  useEffect(() => {
    if (registry) loadArchitecture(STARTER_ARCHITECTURE)
  }, [registry, loadArchitecture])

  if (!registry) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-slate-500">
        Loading node registry…
      </div>
    )
  }

  return <RegistryProvider value={registry}>{children}</RegistryProvider>
}
