import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { useGraphStore, type RFNode } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { RadialNodePorts } from '@/canvas/nodes/RadialNodePorts'

const connectionInProgress = vi.hoisted(() => ({ value: false }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useConnection: (selector: (c: { inProgress: boolean }) => unknown) =>
      selector({ inProgress: connectionInProgress.value }),
  }
})

beforeEach(() => {
  connectionInProgress.value = false
})

function renderPorts() {
  return render(
    <ReactFlowProvider>
      <RadialNodePorts
        nodeId="n1"
        inputs={[{ id: 'task', label: 'Task', dataType: 'text' }]}
        outputs={[{ id: 'plan', label: 'Plan', dataType: 'plan' }]}
      />
    </ReactFlowProvider>,
  )
}

describe('RadialNodePorts — local hover reveal', () => {
  beforeEach(() => {
    useGraphStore.setState({ nodes: [], edges: [], radialCenterId: null })
    useUiStore.setState({ showConnectionPorts: true })
  })

  it('hides unconnected port handles until the node is hovered', () => {
    const { container } = renderPorts()
    const input = container.querySelector('[aria-label="Input port: Task"]')!
    expect(input).toHaveStyle({ opacity: '0', pointerEvents: 'none' })
  })

  it('reveals unconnected port handles on hover, hides them again on leave', () => {
    const { container } = renderPorts()
    const hoverZone = container.querySelector('[aria-hidden="true"]')!

    fireEvent.mouseEnter(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '1',
      pointerEvents: 'auto',
    })

    fireEvent.mouseLeave(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '0',
      pointerEvents: 'none',
    })
  })

  it('never reveals when connection edit mode is off, even while hovered', () => {
    useUiStore.setState({ showConnectionPorts: false })
    const { container } = renderPorts()
    const hoverZone = container.querySelector('[aria-hidden="true"]')!

    fireEvent.mouseEnter(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({ opacity: '0' })
  })

  it('shows the port label text only while revealed', () => {
    const { container, queryByText, getByText } = renderPorts()
    expect(queryByText('Task')).not.toBeInTheDocument()
    expect(queryByText('Plan')).not.toBeInTheDocument()

    const hoverZone = container.querySelector('[aria-hidden="true"]')!
    fireEvent.mouseEnter(hoverZone)
    expect(getByText('Task')).toBeInTheDocument()
    expect(getByText('Plan')).toBeInTheDocument()

    fireEvent.mouseLeave(hoverZone)
    expect(queryByText('Task')).not.toBeInTheDocument()
  })
})

describe('RadialNodePorts — reveal while another connection is in progress', () => {
  beforeEach(() => {
    useGraphStore.setState({ nodes: [], edges: [], radialCenterId: null })
    useUiStore.setState({ showConnectionPorts: true })
    connectionInProgress.value = false
  })

  it('reveals unconnected ports even without local hover, while a connection is in progress', () => {
    connectionInProgress.value = true
    const { container } = renderPorts()

    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '1',
      pointerEvents: 'auto',
    })
  })

  it('stays hidden when no connection is in progress and the node is not hovered', () => {
    const { container } = renderPorts()

    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({ opacity: '0' })
  })
})

describe('RadialNodePorts — connected ports', () => {
  beforeEach(() => {
    useUiStore.setState({ showConnectionPorts: true })
  })

  function renderConnectedPorts(radialCenterId: string | null) {
    const nodes: RFNode[] = [
      { id: 'n1', position: { x: 0, y: 0 }, data: { manifestType: 'x', config: {} } },
      { id: 'n2', position: { x: 200, y: 0 }, data: { manifestType: 'x', config: {} } },
    ]
    useGraphStore.setState({
      nodes,
      edges: [{ id: 'e1', source: 'n1', sourceHandle: 'plan', target: 'n2', targetHandle: 'task' }],
      radialCenterId,
    })
    return render(
      <ReactFlowProvider>
        <RadialNodePorts nodeId="n1" inputs={[]} outputs={[{ id: 'plan', label: 'Plan', dataType: 'plan' }]} />
      </ReactFlowProvider>,
    )
  }

  it('keeps a connected port invisible even while hovered, with no radial center set', () => {
    const { container, queryByText } = renderConnectedPorts(null)
    const hoverZone = container.querySelector('[aria-hidden="true"]')!
    fireEvent.mouseEnter(hoverZone)

    expect(container.querySelector('[aria-label="Output port: Plan"]')).toHaveStyle({
      opacity: '0',
      pointerEvents: 'none',
    })
    expect(queryByText('Plan')).not.toBeInTheDocument()
  })

  it('keeps a connected port invisible even while hovered, when this node is itself the radial center', () => {
    const { container } = renderConnectedPorts('n1')
    const hoverZone = container.querySelector('[aria-hidden="true"]')!
    fireEvent.mouseEnter(hoverZone)

    expect(container.querySelector('[aria-label="Output port: Plan"]')).toHaveStyle({
      opacity: '0',
      pointerEvents: 'none',
    })
  })
})
