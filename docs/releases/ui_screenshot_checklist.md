# v1.0.0 manual UI screenshot checklist

Status: COMPLETE (verified 2026-08-08).

The project owner intentionally omitted a demo video from v1.0.0. Capture only genuine screenshots
or an optional short GIF from the running application. Do not create a video, placeholder URL, mock
UI image, or generated image that appears to be a real product run.

All three required PNGs below are present in `docs/images/` and were manually inspected. No optional
GIF is required or claimed.

## Start the verified runtime

1. Keep the provider credential in a private .env file or an external APP_ENV_FILE. Never commit it.
2. From the repository root, validate and start the CPU Compose path:

~~~powershell
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build --wait
~~~

3. Open http://localhost:8080/ and confirm http://localhost:8080/ready reports ready before
   capturing any image.

Use a clean browser profile where possible. Recommended desktop viewport is 1440 x 1000. Recommended
mobile viewport is 390 x 844. Do not show the .env file, API keys, browser extensions, local file
paths, private conversations, devtools, request headers, or provider billing/account information.

## Required files and real scenarios

| File to save | Viewport | Exact scenario | What must be visible |
| --- | --- | --- | --- |
| docs/images/ui-chat-citation.png | Desktop | Ask: Điều 135 quy định gì? | Assistant answer, at least one citation, and the evidence/citation panel. |
| docs/images/ui-calculator-trace.png | Desktop | Ask: Tôi làm việc theo hợp đồng không xác định thời hạn và muốn đơn phương chấm dứt. Tôi phải báo trước bao lâu? | Calculator result, Article 35 legal basis, and visible verification or tool-trace evidence. |
| docs/images/ui-guardrail-or-clarification.png | Desktop | Ask: Điều 999 quy định gì? | Safe insufficient-context or clarification result, without fabricated citation. |

Optional:

| File to save | Viewport | Exact scenario | What must be visible |
| --- | --- | --- | --- |
| docs/images/ui-mobile-evidence.png | Mobile | Use the Article 35 scenario above, then open the evidence control. | Mobile evidence sheet with the citation. |

After saving the approved PNG files, keep them unedited apart from normal lossless cropping that does
not change the visible application state. Return to Codex with the files in docs/images so their
existence, format, and README references can be checked.
