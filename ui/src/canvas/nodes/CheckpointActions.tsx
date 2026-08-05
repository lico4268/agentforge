import { useTransport } from '@/transport/TransportContext'

type CheckpointAction = 'approve' | 'revise' | 'reject'

const ACTION_STYLE: Record<CheckpointAction, { background: string; color: string }> = {
  approve: { background: '#4edea333', color: '#4edea3' },
  revise: { background: '#ffd18033', color: '#ffd180' },
  reject: { background: '#ff8a8033', color: '#ff8a80' },
}

type CheckpointActionsProps = {
  nodeId: string
  runId: string
  actions?: readonly CheckpointAction[]
  className?: string
}

/** Shared resume controls for a paused Human Checkpoint. */
export function CheckpointActions({
  nodeId,
  runId,
  actions = ['approve', 'revise', 'reject'],
  className = '',
}: CheckpointActionsProps) {
  const transport = useTransport()

  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      {actions.map((action) => (
        <button
          key={action}
          type="button"
          onClick={() =>
            transport.send({
              kind: 'resume',
              runId,
              nodeId,
              decision: { action },
            })
          }
          className="flex-1 rounded px-2 py-1 text-[10px] font-semibold uppercase tracking-wide transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#dde4dd]"
          style={ACTION_STYLE[action]}
          aria-label={`${action} checkpoint`}
        >
          {action}
        </button>
      ))}
    </div>
  )
}
