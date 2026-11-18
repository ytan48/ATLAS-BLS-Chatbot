# Input validation audit and test report

> Historical baseline: the original audit below records the previous 4,000-character / 64 KiB behavior. See the second-round update at the end for current behavior and results.

Date: 2026-11-18. All student details are synthetic. No live inference was performed.

## Executive summary

The existing server accepts questions up to 4,000 Python characters; the synthetic 500-word outline fits, but the 1,000-word essay and longer examples do not. All three chat endpoints enforce the same server checks. Tests confirm rejection happens before the mocked inference function. The browser interfaces do not show the server's specific validation errors. Current limits and security controls were not changed.

## Existing restrictions and observed behavior

| Restriction | Existing behavior and location | Rationale / caveat |
| --- | --- | --- |
| Frontend | No `maxlength` or explicit character cap in `frontend/index.html`, `frontend/widget.html`, or `frontend/embed-nextjs/components/EmbedChatWidget.tsx`. Each trims outer whitespace before sending; empty input is not sent. | No documented numerical frontend limit. The browser may impose its own practical constraints. |
| Question | `app.py` rejects empty, whitespace-only, non-string, or more than 4,000 Python Unicode code points, before model invocation, on `/api/ask`, `/api/chat`, and `/api/stream`. | Security limit documented in README; a more specific sizing rationale is not documented. Python code points differ from UTF-8 bytes and JavaScript UTF-16 units. |
| Previous answer | `app.py` accepts a string of at most 16,000 code points in `last_response`, even when the model is configured to ignore it. | A validation/security bound; specific sizing rationale undocumented. A longer model answer can prevent the next request. |
| HTTP body | `MAX_CONTENT_LENGTH` is 65,536 bytes in `app.py`, including JSON syntax, escaping, and all fields. | Request-size protection; specific sizing rationale undocumented. Proxy limits may differ. |
| History | HTML clients send only their latest assistant response; Next.js sends none. `atlas_chat.py` sends that response only when `ATLAS_USE_LAST_RESPONSE=true` (default false), and never sends earlier user turns or a full transcript. | Single-completion workflow; not a conversation-history length cap. A visible long chat does not imply the model retains it. |
| Model context / tokens | `atlas_chat.py` sends system instructions plus knowledge base and current question, optionally one answer. It sets no context-window, input-token, or output-token limit in the payload. | Server/model context, tokenizer, output defaults, and upstream truncation are unverified. Do not infer GPU configuration. |
| Truncation | API forwards accepted query unchanged to `ask_atlas`; `ask_atlas` and `build_payload` strip outer whitespace, preserving internal formatting. No local length-based truncation found. | Upstream behavior is unverified. Frontends also trim outer whitespace. |
| Other protection | Shared Flask-Limiter default 10 requests/minute and configured CORS in `app.py`; Marked and DOMPurify remain in the HTML clients. | Limit can yield 429 independently of size; no controls changed. |

API validation messages are `No query provided`, `Question must be 4,000 characters or fewer.`, `Invalid previous response.`, `A JSON object is required.`, and for 413 `Request is too large.` The first and previous-answer messages could be more descriptive. The full-page and widget clients treat non-OK responses as connection failures; the Next.js client displays a generic processing failure. Thus these API messages are not presented to users. The HTML clients clear the input before the response, adding friction after rejection. Streaming failures after headers are emitted are SSE error events with HTTP 200, distinct from validation failures before streaming.

## Methodology

`tests/input_dataset.py` generates deterministic, exact-word-count fictional examples using repeated academic-background paragraphs and admissions-feedback prompts. Counts are whitespace-separated words, Python code points, and UTF-8 bytes; JSON body sizes include escaped line breaks and overhead. Token counts are not estimated: no model tokenizer is configured, and a character-based guess would be unreliable, especially for Unicode. Tests use Flask's test client and mock `app.ask_atlas`, block network access, consume streaming responses, and reset the limiter to isolate input validation. The mock verifies the entire accepted input and prior answer received at the inference boundary; payload tests separately verify stripping and history shape. This does not establish model quality, rendering in a browser, or upstream retention.

Run: `python -m unittest discover -s tests -p "test_input_validation.py" -v`. The live script requires an explicit authorized endpoint and flag, and sends exactly one request, e.g. `python scripts/evaluate_live_input.py --url http://localhost:5001/api/chat --scenario outline --authorized`. It prints elapsed time and response for human review of relevance, completeness, the final detail, and BLS boundaries. It does not automatically grade model quality. Larger scenarios are expected to be rejected under current limits. Obtain authorization before targeting a shared service.

## Results

All seven input test methods passed for every chat route. In the table, PASS means the observed status matched the existing contract, not that the limit meets user needs. Counts are for the query, not the request body. All examples are ASCII, so characters equal UTF-8 bytes.

| Synthetic scenario | Words | Characters / UTF-8 bytes | HTTP | Outcome |
| --- | ---: | ---: | ---: | --- |
| Basic question | 20 | 122 | 200 | PASS: accepted |
| Detailed background | 300 | 1,972 | 200 | PASS: accepted |
| Essay outline | 500 | 3,279 | 200 | PASS: accepted |
| Full essay | 1,000 | 6,556 | 400 | PASS: rejected at question limit |
| Multiple drafts | 2,000 | 13,109 | 400 | PASS: rejected at question limit |
| Academic history | 3,000 | 19,672 | 400 | PASS: rejected at question limit |
| Program documentation | 5,000 | 32,791 | 400 | PASS: rejected at question limit |
| Extremely large input | 20,000 | 131,199 | 413 | PASS: request body too large |

The 3,999/4,000/4,001 question, 15,999/16,000/16,001 previous-answer, and 65,535/65,536/65,537 byte body boundaries passed across all endpoints. Empty and whitespace inputs, malformed JSON/non-object bodies, multilingual text, emoji, repeated characters, paragraphs, Markdown and HTML passed their expected contract checks. A 15-turn simulation confirms only the supplied previous answer is forwarded per request, not that a model remembers earlier turns. Unicode examples passed to the mocked inference boundary intact; JSON escaping can make body size much larger than UTF-8 query size. Error strings were asserted; their usability was assessed by source inspection, not browser automation.

Regression results: 34 Python tests passed, including 7 new tests. The existing Markdown sanitization test passed with the locally installed jsdom. No live GPU or model-quality results are claimed.

## Limitations and recommendations

The dataset is illustrative, not a statistical sample of student writing; word counts cannot guarantee acceptance. The current cap can block legitimate essays, while the generic browser error misidentifies the cause. First improve client error handling, preserve draft text, and display an accessible character count and actionable limits. Consider a higher question cap or an explicit chunking workflow after stakeholders review actual needs, model token budget, throughput, and abuse protections; do not select a production number from these examples alone. Clarify the previous-answer error and consider how an oversized model answer affects the next turn. Evaluate whether the product needs explicit conversation history, respecting the single-call architecture and privacy requirements.

## Deployment considerations

Confirm actual model context window, tokenizer, output reservation, upstream truncation, proxy body limits, timeout, and deployed environment settings with operators. Assess combined system prompt, previous answer, query, and output budget together before any change. Test authorized, low-volume representative cases with the optional script and manual BLS-boundary review; local acceptance alone does not prove relevance or end-of-input retention. Review rate-limit ownership with the GPU team; Flask-Limiter remains in place. Check accessibility, client error display, logging/privacy, CORS, and production storage before rollout.


## Second-round update - 2026-11-18

### Current behavior and comparison

| Area | Before | After |
| --- | --- | --- |
| Question | 4,000 code points | 16,000 by default; `CHAT_MAX_QUESTION_CHARS` accepts 1-32,000 and fails startup on invalid configuration. Same check for all three routes. |
| Body | 65,536 bytes | 1,048,576 bytes. At the configured maximum, a 32,000-code-point question plus a 16,000-code-point previous answer fits even if every supplementary Unicode character uses a 12-byte JSON escape. Arbitrary extra fields remain subject to the total cap. |
| Student draft | Cleared before response; generic error | Counter uses JavaScript code-point iteration, warns at 90%, and disables sending over the configured limit without cutting pasted text. Clients retain the draft on failures and append a conversation entry only after success, avoiding retry duplicates. Status-specific safe messages cover invalid input, size, rate limiting, connection failures, and server failures. |
| Forwarding | Outer whitespace stripped | Accepted questions including outer whitespace reach the inference payload intact. |
| Previous response | Validated even when disabled; oversized response rejected a follow-up | Disabled by default and ignored by the API when disabled. When enabled, HTML clients send only the previous assistant answer, omit it entirely if over 16,000 code points, and notify the student. The API also omits oversized previous answers and returns `X-BLS-Context-Omitted: previous-response-too-long`. Invalid non-string previous responses are rejected only when enabled. Next.js sends none. |

A request body over 1 MiB is rejected before its fields can be processed, including an oversized previous response. The header communicates omission to API clients; independently hosted clients must explicitly expose that header through their own CORS policy if they need to read it. The HTML client uses its locally known omission to notify the student. `/api/input-config` exposes the active question limit and context setting; if configuration cannot be loaded, clients do not submit with an assumed limit.

### Verification

The full offline Python suite passed: 36 test methods, including all three endpoints, 15,999/16,000/16,001 characters, 1 MiB byte boundaries, configured 32,000-character maximum, escaped supplementary Unicode with a 16,000-character previous answer, malformed requests, previous-response handling, and synthetic 500-, 1,000-, and 2,000-word inputs. Those three samples now fit and reach the mocked model intact. No rejected request reaches the mocked inference function. The HTML jsdom test passed counter, emoji, over-limit paste, safe rate-limit error, preserved draft and retry-without-duplicate checks for both HTML interfaces. The existing DOMPurify/partial-rendering regression passed. The Next.js component was updated but its build and browser interaction were not run because its dependencies are not installed locally; verify it in the deployed frontend environment. No GPU calls or load tests were run.

### Conversation design and deployment follow-up

The visible conversation remains different from model context. An essay submitted in one turn is absent when a student later says "clarify the second paragraph"; even enabling previous-answer context supplies only the assistant's last reply, not the essay. Students should repeat relevant excerpts. A future bounded approach could send a small, explicitly selected set of recent user/assistant turns within a verified token budget, reserve space for system instructions and output, and clearly indicate when older turns are omitted. Review privacy, consent, token accounting and cost before implementing it; retain a single inference call.

Confirm the real GPU model's context and output limits, tokenization, truncation, proxy limits, latency, and concurrency before deployment. The new application limit does not guarantee the model can process every accepted question together with the system prompt. Confirm GPU-side rate limiting and its scope against Flask-Limiter before changing either control. Check CORS for a separately hosted Next.js app, proxy body limits, accessible behavior in supported browsers, and the omitted-context header. Test representative authorized low-volume inputs separately; no model quality or end-of-input retention has been established here.

