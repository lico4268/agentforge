import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LogPanel } from '@/panels/LogPanel'

// 스모크 테스트: 스토어에 이벤트가 없으면 빈 상태 안내를 렌더한다.
describe('LogPanel', () => {
  it('이벤트가 없으면 안내 문구를 보여준다', () => {
    render(<LogPanel />)
    expect(screen.getByText(/No events yet/i)).toBeInTheDocument()
    expect(screen.getByText(/Execution Log/i)).toBeInTheDocument()
  })
})
