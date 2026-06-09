# Smile WC 2026

Hệ thống quản lý kèo nội bộ cho FIFA World Cup 2026. Runtime OpenClaw đọc và ghi trực tiếp trên Google Sheets. Toàn bộ thời gian hiển thị và timestamp vận hành dùng giờ Việt Nam: `Asia/Ho_Chi_Minh` (GMT+7).

Trong vận hành live:

- Google Sheets là nguồn dữ liệu chính.
- CSV local chỉ dùng cho test, export, backup, hoặc script offline.
- Workbook public chỉ dùng cho view theo từng trận.

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc](#kiến-trúc)
- [Yêu cầu môi trường](#yêu-cầu-môi-trường)
- [Runtime Google Sheets](#runtime-google-sheets)
- [Quy tắc dữ liệu](#quy-tắc-dữ-liệu)
- [Workbook public](#workbook-public)
- [Lệnh hỗ trợ](#lệnh-hỗ-trợ)
- [Chạy test](#chạy-test)
- [Script dữ liệu](#script-dữ-liệu)
- [Quy trình vận hành](#quy-trình-vận-hành)
- [Bảo mật](#bảo-mật)

## Tổng quan

Project này xử lý các nghiệp vụ chính:

- quản lý member và số dư point
- đặt kèo WDL
- đặt kèo tỷ số
- chuyển point giữa member
- settle trận và cộng point
- đồng bộ workbook public theo từng trận
- audit hậu kiểm sau action

Nguyên tắc triển khai hiện tại:

- giờ Việt Nam áp dụng cho toàn bộ runtime và thao tác mới
- sheet public không chứa dữ liệu nội bộ như `members`, `point_ledger`, `admin_actions`
- mọi thay đổi live phải đi qua pipeline: ghi dữ liệu, sync public, audit lại

## Kiến trúc

### Mã nguồn chính

- `src/betting_service.py`: nghiệp vụ betting, settlement, transfer, ledger, sync và audit hook
- `src/command_router.py`: parse lệnh từ Google Chat event và gọi service
- `src/google_chat_context.py`: ánh xạ actor hoặc mention Google Chat sang member
- `src/csv_store.py`: chọn backend store
- `src/google_sheets_store.py`: đọc, append, replace row trên Google Sheets

### Script chính

- `scripts/run_tests.sh`: chạy toàn bộ test và mô phỏng
- `scripts/import_openfootball_wc2026.py`: import lịch và đội từ openfootball
- `scripts/upload_wc2026_csv_to_drive.py`: upload CSV thành Google Sheets
- `scripts/sync_public_match_workbook.py`: sync workbook public theo từng trận
- `scripts/audit_openclaw_state.py`: audit hậu kiểm trạng thái sheet
- `scripts/export_match_bet_sheets.py`: dựng dữ liệu tab public theo từng trận

### Dữ liệu local

- `data/wc2026_betting/`: artifact local cho test, export, backup, offline workflow

## Yêu cầu môi trường

- Python `3.10+`
- Không cần cài package bên ngoài để chạy logic core và test local
- Cần package Google nếu chạy script thao tác live với Google Sheets hoặc Drive

Cài dependencies Google khi cần:

```bash
python3 -m pip install -r scripts/requirements-google.txt
```

## Runtime Google Sheets

OpenClaw nên chạy ở chế độ Google Sheets-only.

### Biến môi trường tối thiểu

```bash
export SMILE_BET_STORE=sheets
export SMILE_BET_SPREADSHEET_ID=<GOOGLE_SHEETS_SPREADSHEET_ID>
export SMILE_BET_GOOGLE_SERVICE_ACCOUNT=.secret/googlechat-service-account.json
```

### Map file -> tab mặc định

- `members.csv` -> `members`
- `matches.csv` -> `matches`
- `point_ledger.csv` -> `point_ledger`
- `win_draw_loss_bets.csv` -> `win_draw_loss_bets`
- `score_bets.csv` -> `score_bets`
- `admin_actions.csv` -> `admin_actions`
- `match_settlements.csv` -> `match_settlements`
- `final_jackpot.csv` -> `final_jackpot`
- `match_sheet_links.csv` -> `match_sheet_links`

Nếu tên tab khác, set `SMILE_BET_SHEET_MAP`:

```bash
export SMILE_BET_SHEET_MAP="members.csv=Members,matches.csv=Matches,point_ledger.csv=Ledger,win_draw_loss_bets.csv=WDL Bets,score_bets.csv=Score Bets,admin_actions.csv=Admin Actions,match_settlements.csv=Settlements,final_jackpot.csv=Final Jackpot,match_sheet_links.csv=Match Sheet Links"
```

### Đồng bộ workbook public và audit

```bash
export SMILE_BET_PUBLIC_WORKBOOK_ID=1wAT0jpXw3_920kHYfemqFMUXWFgzFpv85mc8GNk_lNY
export SMILE_BET_SYNC_PUBLIC_WORKBOOK=true
export SMILE_BET_AUDIT_AFTER_ACTION=true
```

Pipeline chuẩn sau mỗi action có thay đổi dữ liệu:

1. ghi row append-only và cache field liên quan vào internal sheets
2. sync workbook public nếu action đụng tới match view
3. chạy `scripts/audit_openclaw_state.py`
4. chỉ báo thành công khi audit pass

## Quy tắc dữ liệu

### Giờ vận hành

- runtime và timestamp mới phải dùng `Asia/Ho_Chi_Minh`
- dữ liệu nguồn có thể còn `kickoff_at_utc`
- dữ liệu hiển thị nên ưu tiên `kickoff_at_local`

### Quy tắc số dư

- mọi thay đổi số dư phải có row trong `point_ledger`
- không chỉnh `members.current_balance` trực tiếp trong vận hành thường
- `members.current_balance` phải khớp với ledger cho member bị tác động

### Quy tắc settle WDL

- chỉ cho đặt `HOME` hoặc `AWAY`
- nếu có cả hai phía, pool WDL được chia theo rule thắng thua hiện hành
- nếu trận hòa, áp fallback chia pool cho hai phía đang có vé
- nếu WDL chỉ có một phía có vé, không payout WDL; toàn bộ pool WDL chuyển jackpot

### Quy tắc settle tỷ số

- nếu có người đoán đúng, pool score được chia cho người thắng
- nếu không ai đoán đúng, pool score chuyển jackpot
- nếu đã settle, mỗi row score vẫn phải được giữ lại trên public tab
- payout của score phải gắn đúng từng row thắng, không cộng dồn sai theo member

### Quy tắc jackpot

`final_jackpot.csv` dùng cho:

- carryover của kèo tỷ số
- carryover từ WDL single-sided pool

## Workbook public

Workbook public là nguồn chính cho view theo từng trận, không phải nguồn cho dữ liệu nội bộ.

### Mỗi tab trận phải có

- thông tin trận
- tổng pool WDL
- tổng pool tỷ số
- danh sách cược WDL
- danh sách cược tỷ số
- nếu đã settle: kết quả trận, trạng thái settle, payout theo từng row cược

### Format bảng public

Các row cược phải tách cột rõ ràng:

- `selection`
- `status`
- `payout_points`
- `net_points`

Không nhét chuỗi kiểu `SETTLED | payout=... | net=...` vào chung một ô.

## Lệnh hỗ trợ

Bot parse các mẫu lệnh chính sau.

### Xem điểm

```text
xem điểm
điểm
balance
```

### Đặt kèo WDL

```text
đặt 2 vé đội chủ nhà thắng trận WC2026-0001
đặt đội khách trận WC2026-0001
đặt draw trận WC2026-0001
```

Lưu ý: runtime hiện tại không nhận bet `DRAW`. Nếu trận hòa, hệ thống xử lý theo fallback WDL hoặc jackpot rule hiện hành.

### Đặt kèo tỷ số

```text
đặt tỷ số 2-1 trận WC2026-0001
đặt tỷ số 0:0 trận WC2026-0001
```

### Chuyển point

```text
chuyển 50 point cho M0002
cho 20 point cho user@example.com
tặng 10 point cho Nguyen Van A
```

### Settle trận

Chỉ manager hoặc admin được chạy:

```text
settle WC2026-0001
chốt kết quả trận WC2026-0001
chot ket qua WC2026-FINAL
```

## Chạy test

Chạy toàn bộ suite:

```bash
./scripts/run_tests.sh
```

Nội dung chính của suite:

- context mapping và quyền Google Chat
- betting flow và router flow
- export public rows
- audit hook
- mô phỏng settlement và reconcile

## Script dữ liệu

### Import lịch World Cup 2026

```bash
python3 scripts/import_openfootball_wc2026.py
```

Script này import dữ liệu từ `openfootball/worldcup.json` và ghi lại `teams.csv`, `matches.csv` cho workflow offline.

### Upload CSV lên Google Drive

Dùng service account:

```bash
python3 scripts/upload_wc2026_csv_to_drive.py \
  --service-account .secret/googlechat-service-account.json \
  --folder-id <GOOGLE_DRIVE_FOLDER_ID>
```

Hoặc dùng biến môi trường:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=.secret/googlechat-service-account.json
python3 scripts/upload_wc2026_csv_to_drive.py --folder-id <GOOGLE_DRIVE_FOLDER_ID>
```

### Sync workbook public

```bash
python3 scripts/sync_public_match_workbook.py \
  --service-account .secret/googlechat-service-account.json \
  --public-workbook-id 1wAT0jpXw3_920kHYfemqFMUXWFgzFpv85mc8GNk_lNY
```

### Audit trạng thái live

Theo trận:

```bash
python3 scripts/audit_openclaw_state.py --match-id WC2026-0001
```

Theo member:

```bash
python3 scripts/audit_openclaw_state.py --member-id M0001 --member-id M0002
```

## Quy trình vận hành

1. cập nhật member seed và lịch trận
2. chạy test khi đổi logic
3. nhận lệnh từ Google Chat hoặc integration layer
4. ghi cược hoặc settlement vào internal sheets
5. sync workbook public
6. chạy audit hậu kiểm
7. chỉ coi action là xong khi audit pass

## Bảo mật

- không commit file trong `.secret/`
- không commit OAuth token, service account JSON, hoặc dữ liệu nhạy cảm
- kiểm tra kỹ nội dung `googlechat_members.json` trước khi chia sẻ
