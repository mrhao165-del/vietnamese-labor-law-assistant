# Real demo recording guide (historical reference)

> This guide is retained as a historical planning reference only. The project owner intentionally
> omitted a demo video from v1.0.0, so do not record, publish, or link a video for this release. Use
> `ui_screenshot_checklist.md` for the active manual media task.

Use the verified CPU-only runtime and a clean browser profile. Show the address bar and `/ready` so
the recording is visibly tied to a real deployment. Never expose `.env`, provider keys, prompts,
local personal conversations, or Docker logs containing private input.

Suggested narration:

1. **Problem and scope (0:00–0:25):** explain hallucination risk, source grounding, and the
   legal-information-only disclaimer.
2. **Runtime (0:25–0:40):** show the React frontend and open `/ready`; mention Nginx, FastAPI, SQLite,
   and CPU-only Docker.
3. **Article 35 retrieval (0:40–1:15):** ask `Điều 35 quy định những trường hợp nào người lao động
   không cần báo trước?`; open citation cards.
4. **Trace and verification (1:15–1:35):** show the stdio MCP tool trace and supported verification.
5. **Calculator (1:35–1:55):** ask `Tôi làm việc theo hợp đồng không xác định thời hạn thì cần báo
   trước bao lâu?`.
6. **Combined route (1:55–2:20):** ask `Hợp đồng của tôi có thời hạn 24 tháng, nếu nghỉ việc thì thời
   hạn báo trước và căn cứ pháp lý là gì?`.
7. **Out of scope (2:20–2:35):** ask `Tôi bị xử phạt giao thông thì phải làm gì?` and show safe refusal.
8. **Feedback/persistence (2:35–3:00):** click up/down, reload, and reopen the persisted conversation.
9. **Architecture and benchmark (3:00–3:30):** show the two README images and explain that V4 is a
   contract suite, not a fourth retriever.
10. **Clone-to-run (3:30–4:10):** show documented external env-file handling and Compose commands
    without opening the secret file.
11. **Limitations (4:10–4:30):** corpus snapshot, Article 20/35 calculator scope, no auth, provider
    dependency, CPU-only evidence, and not legal advice.

If any live question fails, keep the failure as evidence, investigate it, and rerun the release gate;
do not splice in a fabricated success.
