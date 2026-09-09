import { ref } from 'vue'

export interface LiveStep {
  label: string
  startMs: number
  serverTs: number
  durationMs: number | null
}

/**
 * The state of the answer currently streaming into the view, and the one rule
 * that keeps it attached to the conversation it belongs to.
 *
 * A conversation can be left at any `await`: while the fetch is in flight,
 * between two events of one chunk, while the previous conversation's messages
 * are still loading. Whoever resumes after that await is holding state for a
 * conversation that is no longer on screen, and writing it anyway is how an
 * answer ends up in somebody else's thread — or, when two switches race, how
 * the slower load wins regardless of which the reader actually picked.
 *
 * So every departure invalidates a token, and every write that follows an
 * await checks the token it started with. `stop()` deliberately does not
 * invalidate: pressing Stop leaves the answer where it is, and the partial
 * response is kept.
 *
 * Lives outside the component because a guard that cannot be tested is a
 * guard nobody can show is complete — `<script setup>` exports nothing.
 */
export function useConversationView() {
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const liveSteps = ref<LiveStep[]>([])
  const liveNow = ref(Date.now())

  let abortController: AbortController | null = null
  let liveTimer: ReturnType<typeof setInterval> | null = null
  let token = 0

  function stopTimer(): void {
    if (liveTimer) {
      clearInterval(liveTimer)
      liveTimer = null
    }
  }

  function reset(): void {
    stopTimer()
    liveSteps.value = []
    isStreaming.value = false
    streamingContent.value = ''
  }

  /** Start streaming an answer. Returns the signal to hand to `fetch`. */
  function begin(): AbortSignal {
    abortController = new AbortController()
    isStreaming.value = true
    streamingContent.value = ''
    liveSteps.value = []
    liveNow.value = Date.now()
    liveTimer = setInterval(() => { liveNow.value = Date.now() }, 100)
    return abortController.signal
  }

  /** The Stop button. Aborts, but the conversation is still the current one. */
  function stop(): void {
    abortController?.abort()
  }

  /** The answer arrived, or failed, and the view is done with it. */
  function finish(): void {
    abortController = null
    reset()
  }

  /**
   * The reader has gone somewhere else. Abandons the in-flight answer and
   * invalidates every token handed out so far. Returns the new one.
   */
  function leave(): number {
    abortController?.abort()
    abortController = null
    reset()
    return ++token
  }

  /** The token to compare against after an await. */
  function current(): number {
    return token
  }

  /** Is the conversation this token was taken for still the one on screen? */
  function isCurrent(taken: number): boolean {
    return taken === token
  }

  return {
    isStreaming, streamingContent, liveSteps, liveNow,
    begin, stop, finish, leave, current, isCurrent,
  }
}
