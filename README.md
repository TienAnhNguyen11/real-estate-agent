## Real Estate Agent (Vietnam)

Backend Python agent tự động crawl 3 trang BĐS (batdongsan.com.vn, nhatot.com, alonhadat.com.vn), lọc theo tiêu chí cá nhân và gửi thông báo qua Telegram Bot.

### Cách chạy nhanh

```bash
cd backend
pip install -r requirements.txt
python -m backend.main
```

Trước khi chạy, sửa `backend/config.yaml` để điền `telegram.bot_token` và `telegram.admin_chat_id`.

