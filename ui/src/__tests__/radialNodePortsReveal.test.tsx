import { beforeEach, describe, expect, it } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { RadialNodePorts } from '@/canvas/nodes/RadialNodePorts'

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
