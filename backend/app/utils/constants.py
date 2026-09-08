SSE_TOKEN = "token"
SSE_DONE = "done"
SSE_GUARDRAIL = "guardrail"

#: Which rail raised a `guardrail` event. The input rail stops the request, so
#: its message *is* the response; the output rail runs after the answer has
#: streamed, so its message is a note attached to an answer the user has
#: already read. Collapsing the two meant an output flag replaced the answer
#: everywhere downstream -- on screen and in the stored transcript -- and the
#: history then disagreed with what the user saw.
GUARDRAIL_INPUT = "input"
GUARDRAIL_OUTPUT = "output"
SSE_STATUS = "status"

DOC_STATUS_PROCESSING = "processing"
DOC_STATUS_READY = "ready"
DOC_STATUS_ERROR = "error"
