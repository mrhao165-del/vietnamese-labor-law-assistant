# Week 8 Legal Rule Matrix

Nguồn duy nhất là snapshot `labor_law` trong repository: `data/raw/labor_law.docx`,
`data/processed/labor_law_clauses.jsonl`, snapshot date `2026-07-10`. Mỗi citation được validator
đối chiếu với chunk ID, Điều, Khoản và Điểm trong JSONL canonical.

| rule_id | tool | contract type | special case | result | value/unit | basis | chunk | status | external dependency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NOTICE_ART35_1_A_INDEFINITE | notice | INDEFINITE | NONE | notice | 45 calendar days | 35.1.a | `ll_6af59ba448952c1c927978713d34d984` | SUPPORTED | none |
| NOTICE_ART35_1_B_FIXED_12_TO_36 | notice | FIXED_TERM_12_TO_36_MONTHS | NONE | notice | 30 calendar days | 35.1.b | same | SUPPORTED | none |
| NOTICE_ART35_1_C_FIXED_UNDER_12 | notice | FIXED_TERM_UNDER_12_MONTHS | NONE | notice | 3 working days | 35.1.c | same | SUPPORTED | no holiday calendar |
| NOTICE_ART35_1_D_SPECIAL_OCCUPATION_EXTERNAL | notice | any | SPECIAL_OCCUPATION_EXTERNAL_REGULATION | unknown duration | null | 35.1.d | same | EXTERNAL_REGULATION_REQUIRED | Government regulation absent from corpus |
| NOTICE_ART35_2_A_NO_AGREED_WORK | notice | any | WORK_OR_LOCATION_NOT_AS_AGREED | no notice | 0/no_notice | 35.2.a | `ll_610e9077fc973dabc980978eb3f3da54` | SUPPORTED | Article 29 exception remains factual scope |
| NOTICE_ART35_2_B_UNPAID_OR_LATE_WAGES | notice | any | UNPAID_OR_LATE_WAGES | no notice | 0/no_notice | 35.2.b | same | SUPPORTED | Article 97.4 exception remains factual scope |
| NOTICE_ART35_2_C_MISTREATMENT_OR_FORCED_LABOR | notice | any | MISTREATMENT_OR_FORCED_LABOR | no notice | 0/no_notice | 35.2.c | same | SUPPORTED | none |
| NOTICE_ART35_2_D_WORKPLACE_SEXUAL_HARASSMENT | notice | any | WORKPLACE_SEXUAL_HARASSMENT | no notice | 0/no_notice | 35.2.d | same | SUPPORTED | none |
| NOTICE_ART35_2_DD_PREGNANT_MEDICAL | notice | any | PREGNANT_WORKER_MEDICAL_CERTIFICATION | no notice | 0/no_notice | 35.2.đ | same | SUPPORTED | Article 138.1 factual certification is caller responsibility |
| NOTICE_ART35_2_E_RETIREMENT_AGE | notice | any | RETIREMENT_AGE_MET | no notice | 0/no_notice | 35.2.e | same | SUPPORTED | Article 169 factual age assessment is caller responsibility |
| NOTICE_ART35_2_G_DISHONEST_INFORMATION | notice | any | EMPLOYER_DISHONEST_INFORMATION | no notice | 0/no_notice | 35.2.g | same | SUPPORTED | Article 16.1 factual assessment is caller responsibility |
| CONTRACT_ART20_1_A_INDEFINITE | duration | INDEFINITE | n/a | no statutory maximum | null | 20.1.a | `ll_d0c5f537983c0aad635529f412e426f5` | SUPPORTED | none |
| CONTRACT_ART20_1_B_FIXED_MAX_36_MONTHS | duration | FIXED_TERM | n/a | maximum boundary | 36 calendar months | 20.1.b | same | SUPPORTED | none |

Đã đối chiếu Điều 16.1, 20.1(a,b), 29.1–2, 35.1(a–d), 35.2(a,b,c,d,đ,e,g), 97.4, 138.1 và
169.1–5. Calculator không tự xác định sự kiện thực tế của các điều khoản dẫn chiếu; caller chọn
enum có kiểm soát. Kết quả là hỗ trợ tra cứu, không phải tư vấn pháp lý.
