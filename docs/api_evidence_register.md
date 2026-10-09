# API Evidence Register

Verification status values: `unverified`, `verified`, `blocked`. This register intentionally contains no contract claims until official evidence is reviewed.

## DataForSEO Authentication

- Official documentation URL:
- Checked date:
- Endpoint:
- HTTP method:
- Required request fields:
- Optional request fields:
- Response-envelope fields:
- Supported platform/model:
- Pricing evidence:
- Fixture availability:
- Verification status: unverified
- Notes:

## Google Organic SERP

- Official documentation URL: https://docs.dataforseo.com/v3/serp/google/organic/task_post/
- Checked date: 2026-09-25
- Endpoint: https://api.dataforseo.com/v3/serp/google/organic/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: device, os, depth
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model:
- Pricing evidence: https://dataforseo.com/pricing/serp/google-organic-serp-api
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow only; task post is followed by `GET https://api.dataforseo.com/v3/serp/google/organic/task_get/advanced/{id}`. The task ID is a provider UUID. Retrieval is free for 30 days after posting. The live endpoint is intentionally not used.

## Bing Organic SERP

- Official documentation URL: https://docs.dataforseo.com/v3/serp/bing/organic/task_post/
- Checked date: 2026-09-27
- Endpoint: https://api.dataforseo.com/v3/serp/bing/organic/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: device, os, depth
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model:
- Pricing evidence: https://dataforseo.com/pricing/serp/bing-serp-api
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow is task_post, then `GET https://api.dataforseo.com/v3/serp/bing/organic/tasks_ready`, then `GET https://api.dataforseo.com/v3/serp/bing/organic/task_get/advanced/{id}`. Live endpoints are intentionally not used.

## Yahoo Organic SERP

- Official documentation URL: https://docs.dataforseo.com/v3/serp/yahoo/organic/task_post/
- Checked date: 2026-09-27
- Endpoint: https://api.dataforseo.com/v3/serp/yahoo/organic/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: device, os, depth
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model:
- Pricing evidence: https://dataforseo.com/pricing/serp/yahoo-serp-api
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow is task_post, then `GET https://api.dataforseo.com/v3/serp/yahoo/organic/tasks_ready`, then `GET https://api.dataforseo.com/v3/serp/yahoo/organic/task_get/advanced/{id}`. Live endpoints are intentionally not used.

## Baidu Organic SERP

- Official documentation URL: https://docs.dataforseo.com/v3/serp/baidu/organic/task_post/
- Checked date: 2026-09-27
- Endpoint: https://api.dataforseo.com/v3/serp/baidu/organic/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: device, os, depth
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model:
- Pricing evidence: https://dataforseo.com/pricing/serp/baidu-serp-api
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow is task_post, then `GET https://api.dataforseo.com/v3/serp/baidu/organic/tasks_ready`, then `GET https://api.dataforseo.com/v3/serp/baidu/organic/task_get/advanced/{id}`. The task-post example requires the Baidu language code `zh_CN`, which the adapter derives from registry value `zh-CN`.

## DataForSEO Standard SERP

- Official documentation URL: See the verified Google, Bing, Yahoo, and Baidu Organic SERP sections above.
- Checked date: 2026-09-27
- Endpoint: Engine-specific Standard task-post endpoint.
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: device, os, depth
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model: google, bing, yahoo, baidu organic
- Pricing evidence: See engine-specific SERP pricing evidence above.
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Collection dispatches only to a verified engine adapter selected by `search_engine` in the target registry.

## DataForSEO LLM Scraper

- Official documentation URL: https://docs.dataforseo.com/v3/ai_optimization/chat_gpt/llm_scraper/task_post/
- Checked date: 2026-09-25
- Endpoint: https://api.dataforseo.com/v3/ai_optimization/chat_gpt/llm_scraper/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields: force_web_search
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model: chat_gpt and gemini; provider-reported model is retained in raw response
- Pricing evidence: https://dataforseo.com/pricing/ai-optimization/llm-scraper
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow is task_post, then tasks_ready, then task_get/advanced/{id}. Collection submits once; retrieval only obtains locally recorded task IDs returned by tasks_ready. ChatGPT may use force_web_search; Gemini uses keyword, location_code, and language_code only. Exact price is not copied here; real mode requires an explicit estimated cost no greater than the user-supplied cap, and actual provider cost is captured in Bronze evidence.

## ChatGPT Target

- Official documentation URL:
- Checked date:
- Endpoint:
- HTTP method:
- Required request fields:
- Optional request fields:
- Response-envelope fields:
- Supported platform/model:
- Pricing evidence:
- Fixture availability:
- Verification status: blocked
- Notes: Target identifier and support require official evidence.

## Gemini Target

- Official documentation URL: https://docs.dataforseo.com/v3/ai_optimization/gemini/llm_scraper/task_post/
- Checked date: 2026-09-27
- Endpoint: https://api.dataforseo.com/v3/ai_optimization/gemini/llm_scraper/task_post
- HTTP method: POST
- Required request fields: keyword, location_code, language_code
- Optional request fields:
- Response-envelope fields: tasks array; task id, status_code, status_message, cost, data, result
- Supported platform/model: gemini; provider-reported model is retained in raw response
- Pricing evidence: https://dataforseo.com/pricing/ai-optimization/llm-scraper
- Fixture availability: yes, HTTP mock contract test
- Verification status: verified
- Notes: Standard workflow is task_post, then `GET https://api.dataforseo.com/v3/ai_optimization/gemini/llm_scraper/tasks_ready`, then `GET https://api.dataforseo.com/v3/ai_optimization/gemini/llm_scraper/task_get/advanced/{id}`.

## Locations And Languages

- Official documentation URL:
- Checked date:
- Endpoint:
- HTTP method:
- Required request fields:
- Optional request fields:
- Response-envelope fields:
- Supported platform/model:
- Pricing evidence:
- Fixture availability:
- Verification status: unverified
- Notes:

## Pricing Evidence

- Official documentation URL:
- Checked date:
- Endpoint:
- HTTP method:
- Required request fields:
- Optional request fields:
- Response-envelope fields:
- Supported platform/model:
- Pricing evidence:
- Fixture availability:
- Verification status: unverified
- Notes:

## Status/Error Handling

- Official documentation URL:
- Checked date:
- Endpoint:
- HTTP method:
- Required request fields:
- Optional request fields:
- Response-envelope fields:
- Supported platform/model:
- Pricing evidence:
- Fixture availability:
- Verification status: unverified
- Notes: