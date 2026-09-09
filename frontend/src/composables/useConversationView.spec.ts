import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useConversationView } from './useConversationView'

/**
 * These cover the thing that cannot be seen by looking at the screen: an
 * answer that finishes streaming into a conversation the reader has already
 * left. The symptom of getting it wrong in one direction is somebody else's
 * answer appearing in your thread; in the other direction it is an answer
 * vanishing, which looks like the app is broken.
 */
describe('useConversationView', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('abandons the in-flight answer when the reader leaves', () => {
    const view = useConversationView()
    const signal = view.begin()
    view.streamingContent.value = 'half an answer'
    view.liveSteps.value = [{ label: 'Generating…', startMs: 0, serverTs: 0, durationMs: null }]

    view.leave()

    expect(signal.aborted).toBe(true)
    expect(view.isStreaming.value).toBe(false)
    expect(view.streamingContent.value).toBe('')
    expect(view.liveSteps.value).toEqual([])
  })

  it('invalidates a token taken before the reader left', () => {
    const view = useConversationView()
    const token = view.current()
    expect(view.isCurrent(token)).toBe(true)

    view.leave()

    expect(view.isCurrent(token)).toBe(false)
  })

  it('lets only the newest of two quick switches count', () => {
    const view = useConversationView()

    // two switches in a row; the first load is still in flight when the
    // second starts, and used to win by being slower to come back
    const first = view.leave()
    const second = view.leave()

    expect(view.isCurrent(first)).toBe(false)
    expect(view.isCurrent(second)).toBe(true)
  })

  it('does not treat the Stop button as leaving', () => {
    const view = useConversationView()
    const token = view.current()
    const signal = view.begin()
    view.streamingContent.value = 'half an answer'

    view.stop()

    // the fetch is cancelled, but this is still the conversation on screen, so
    // the caller may finish writing the partial answer into it
    expect(signal.aborted).toBe(true)
    expect(view.isCurrent(token)).toBe(true)
    expect(view.streamingContent.value).toBe('half an answer')
  })

  it('stops the step timer on both exits', () => {
    for (const exit of ['finish', 'leave'] as const) {
      const view = useConversationView()
      view.begin()
      const started = view.liveNow.value

      vi.advanceTimersByTime(500)
      expect(view.liveNow.value).toBeGreaterThan(started)

      view[exit]()
      const stopped = view.liveNow.value
      vi.advanceTimersByTime(5000)

      expect(view.liveNow.value).toBe(stopped)
    }
  })

  it('keeps the conversation current across a normal finish', () => {
    const view = useConversationView()
    const token = view.current()
    view.begin()

    view.finish()

    expect(view.isCurrent(token)).toBe(true)
    expect(view.isStreaming.value).toBe(false)
  })
})
