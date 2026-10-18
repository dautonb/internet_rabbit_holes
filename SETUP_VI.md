# Hướng dẫn cài Internet Rabbit Hole (Windows + GitHub Actions)

## Kết quả mong muốn

Mỗi ngày lúc 08:00 giờ Việt Nam, workflow sẽ chọn một chủ đề trong `topics.txt`, gọi một endpoint search qua Orthogonal, lưu một bài Markdown vào `journal/rabbit-holes/`, cập nhật `journal/index.md` và `data/history.json`, rồi commit các thay đổi về repo.

Bản MVP chỉ gọi một endpoint search mỗi lần chạy; nó dùng CLI chính thức của Orthogonal để tránh tự dựng request gateway sai schema. Nó lưu nguồn và đoạn trích, chưa tự viết một bài luận bằng LLM.

## 1. Chuẩn bị

- Một tài khoản GitHub.
- Một tài khoản Orthogonal và API key hợp lệ.
- Git for Windows: https://git-scm.com/download/win
- Tải ZIP của dự án và giải nén vào một thư mục dễ tìm, ví dụ `C:\Projects\internet-rabbit-hole`.

Không đăng API key vào chat, Issue, file Python, YAML hoặc commit.

## 2. Tạo repo GitHub

1. Vào https://github.com/new.
2. Đặt tên `internet-rabbit-hole`.
3. Chọn Public hoặc Private. Chọn Private nếu không muốn các bài journal được công khai.
4. Không khởi tạo README, `.gitignore` hoặc license (vì dự án đã có các file này).
5. Nhấn **Create repository** và giữ lại URL repo, ví dụ `https://github.com/USERNAME/internet-rabbit-hole.git`.

## 3. Push source từ máy Windows

1. Mở thư mục vừa giải nén trong File Explorer.
2. Bấm thanh địa chỉ, gõ `powershell`, nhấn Enter (hoặc chọn **Open in Terminal**).
3. Chạy lần lượt các lệnh sau. Thay URL ở lệnh cuối bằng URL repo thật:

```powershell
git init
git add .
git commit -m "feat: bootstrap Internet Rabbit Hole"
git branch -M main
git remote add origin https://github.com/USERNAME/internet-rabbit-hole.git
git push -u origin main
```

Nếu Git hỏi danh tính, cấu hình tên và email cho Git trên máy:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Sau đó chạy lại `git commit` và `git push` nếu cần. Email có thể là địa chỉ noreply của GitHub nếu muốn tránh công khai email thật.

## 4. Thêm Orthogonal secret

1. Đăng nhập Orthogonal và tạo/lấy API key trong dashboard.
2. Mở repo GitHub → **Settings** → **Secrets and variables** → **Actions**.
3. Chọn **New repository secret**.
4. Tên secret phải chính xác là `ORTHOGONAL_API_KEY`.
5. Dán key vào Value và lưu.

Không cần tạo `GITHUB_TOKEN` thủ công. GitHub Actions tự cấp token cho workflow; file workflow đã khai báo `permissions: contents: write` để commit bài viết.

## 5. Cấu hình Telegram để nhận tin nhắn tự động

Mỗi lần tìm kiếm xong, agent sẽ gửi một tin nhắn Telegram gồm chủ đề trong ngày, truy vấn tìm kiếm, tối đa 3 nguồn có link bấm được và 3 hướng đào sâu tiếp. Telegram Bot API không tốn Orthogonal credit. Nếu chưa cấu hình hai secret Telegram, bot vẫn tạo và commit journal như bình thường.

### 5.1. Tạo bot Telegram

1. Mở Telegram và tìm tài khoản chính thức **@BotFather**.
2. Gửi lệnh `/newbot`.
3. Nhập tên hiển thị, ví dụ `Internet Rabbit Hole`.
4. Nhập username chưa có ai dùng và thường kết thúc bằng `bot`, ví dụ `my_rabbit_hole_bot`.
5. BotFather trả về **HTTP API token**. Giữ token bí mật; ai có token có thể điều khiển bot.
6. Mở liên kết của bot mà BotFather cung cấp, nhấn **Start** và gửi `/start`. Bot cần được người dùng mở/bắt đầu chat trước khi có thể chủ động gửi tin nhắn riêng.

### 5.2. Lấy chat ID của mày

Trên Windows, mở PowerShell và chạy khối lệnh này. Khi được hỏi, dán token vào terminal; đừng chụp/gửi màn hình có token. Lệnh chỉ gọi `getUpdates` và in ra thông tin chat.

```powershell
$secure = Read-Host "Paste Telegram bot token" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $env:TELEGRAM_BOT_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  $updates = Invoke-RestMethod -Uri "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/getUpdates"
  $updates.result | ForEach-Object {
    if ($_.message) {
      [PSCustomObject]@{ chat_id = $_.message.chat.id; type = $_.message.chat.type; username = $_.message.chat.username; title = $_.message.chat.title }
    }
  } | Format-Table -AutoSize
} finally {
  if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
  Remove-Item Env:\TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
}
```

Tìm dòng có `type` là `private` và username của mày; giá trị `chat_id` ở dòng đó chính là ID cần lưu. Nếu không có dòng nào, gửi `/start` cho bot rồi chạy lại. Chỉ cần lưu con số `chat_id`, không cần lưu output thừa.

Muốn gửi vào group: thêm bot vào group, gửi một tin nhắn/command trong group, rồi chạy `getUpdates` lại và dùng `message.chat.id` của group (thường là số âm). Muốn gửi vào channel: thêm bot làm admin có quyền đăng bài; có thể dùng `@channelusername` làm chat ID cho channel public.

### 5.3. Lưu hai Telegram secrets trên GitHub

Mở repo → **Settings → Secrets and variables → Actions → New repository secret**. Tạo hai secret đúng tên sau:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do @BotFather cấp |
| `TELEGRAM_CHAT_ID` | Chat ID ở bước 5.2; có thể là số hoặc `@channelusername` |

Không đặt token trực tiếp trong Python, workflow YAML hay `topics.txt`. Workflow đã truyền hai secret này cho chương trình Python. Sau khi lưu secrets, chạy workflow thủ công một lần để kiểm tra tin nhắn.

Nếu Telegram gửi lỗi tạm thời, log sẽ hiện cảnh báo nhưng bài journal vẫn được giữ và commit; bot không làm mất bài chỉ vì Telegram đang lỗi. Nếu không cấu hình Telegram, workflow bỏ qua gửi tin nhắn.

## 6. Kiểm tra endpoint trước lần chạy thật

Cài Node.js 18+ nếu chưa có: https://nodejs.org/. Trong PowerShell, có thể xem schema endpoint bằng CLI:

```powershell
npx @orth/cli api show tavily /search
```

Đọc phần tham số, HTTP method và giá. Nếu cần xác thực CLI để gọi endpoint, chỉ dùng biến môi trường cục bộ; không dán key trực tiếp vào file hoặc lệnh sẽ commit.

Lệnh ước tính giá (dry-run) theo cú pháp CLI hiện được tài liệu hóa; giữ cùng tham số `query` mà source sẽ sử dụng:

```powershell
npx @orth/cli run tavily /search --dry-run -q "query=why old websites survive"
```

Nếu schema trên dashboard khác với `tavily /search`, đừng chạy workflow ngay. Cần cập nhật `ORTHOGONAL_SEARCH_API`, `ORTHOGONAL_SEARCH_PATH` trong `.github/workflows/rabbit-hole.yml` và object `query` trong `scripts/rabbit_hole.py` sao cho trùng schema endpoint đã chọn.

## 7. Chạy thử bằng tay

1. Mở repo → tab **Actions**.
2. Chọn workflow **Internet Rabbit Hole** ở cột trái.
3. Nhấn **Run workflow**.
4. Có thể nhập topic bằng tiếng Anh, ví dụ `The strange history of the dancing baby meme`, hoặc để trống để agent tự chọn chủ đề.
5. Nhấn nút xanh **Run workflow** để bắt đầu.
6. Mở run vừa tạo và kiểm tra từng step. Nếu thất bại, bấm step đỏ để xem log.

Khi thành công, repo sẽ có một file mới trong `journal/rabbit-holes/`, đồng thời cập nhật `journal/index.md` và `data/history.json`. Nếu đã cấu hình Telegram bên dưới, bot cũng gửi bản tóm tắt vào Telegram.

## 8. Lịch chạy tự động

Workflow có lịch:

```yaml
schedule:
  - cron: "0 1 * * *"
```

Đây là 01:00 UTC = 08:00 giờ Việt Nam (UTC+7). Scheduled workflow phải tồn tại trên default branch. GitHub có thể trì hoãn lịch khi hệ thống tải cao; lịch cron không đảm bảo chạy đúng từng phút.

## 9. Tùy biến

- Thêm/xóa chủ đề bằng cách sửa `topics.txt`, mỗi dòng một chủ đề.
- Đặt `MAX_RESULTS` trong workflow (mặc định 5; code giữ tối đa 3–8 kết quả trong bài. Bản này không truyền tham số `max_results` lên provider vì schema cần được xác nhận trước).
- Đặt `SEARCH_SUFFIX` để thay cụm từ phụ thêm vào truy vấn.
- Chọn một topic riêng cho mỗi lần chạy trong **Run workflow**.
- Nếu muốn bài journal không công khai, đặt repo ở chế độ Private.

## 10. Lỗi thường gặp

### `ORTHOGONAL_API_KEY is missing`
Kiểm tra Settings → Secrets and variables → Actions. Tên secret phải đúng chữ hoa/thường và không có khoảng trắng.

### HTTP 400: `Expected string, received number`
Orthogonal nhận các tham số trong object `query` dưới dạng query-string, vì vậy các giá trị cần là chuỗi. Trong bản đã sửa, `max_results` được gửi thành `"5"` thay vì số `5`. Nếu gặp lỗi này ở endpoint khác, kiểm tra mọi giá trị trong `query` và chuyển số/boolean thành chuỗi theo schema của endpoint.

### HTTP 400 / 404 / 422 khác
Bản hiện tại dùng lệnh CLI chính thức `npx @orth/cli run tavily /search -q query=... --raw`, thay vì tự dựng body cho REST gateway. Nếu lỗi tiếp diễn, chạy `npx @orth/cli api show tavily /search`, rồi thử trực tiếp `npx @orth/cli run tavily /search -q "query=why old websites survive" --raw`. Kiểm tra lỗi từ CLI, schema endpoint, API key và số dư Orthogonal. Workflow đã cài Node.js để chạy CLI; log cũng hiển thị lỗi CLI đã rút gọn mà không in API key.

### Request thành công nhưng không thấy search results
Response endpoint có thể có cấu trúc khác bộ chuẩn hóa hiện tại. Xem dữ liệu mẫu theo tài liệu/catalog, rồi cập nhật `normalize_results()` trong `scripts/rabbit_hole.py`. Đừng in ra API key hoặc header Authorization khi debug.

### Workflow tạo bài nhưng không push được
Kiểm tra repo Settings → Actions → General → Workflow permissions và chính sách của tổ chức. Workflow cần quyền `contents: write`.

### Workflow chưa chạy lúc 08:00
Chạy thủ công để kiểm tra trước. Scheduled workflow phải nằm trên default branch; lịch cũng có thể bị trễ khi GitHub Actions quá tải.

## 11. Cách xác nhận agent chạy ổn

- Một workflow run kết thúc trạng thái xanh.
- `journal/rabbit-holes/` có file Markdown mới.
- Bài có các URL nguồn hợp lệ và đoạn trích.
- `journal/index.md` liệt kê bài mới.
- `data/history.json` đã ghi ngày và chủ đề.
- Orthogonal dashboard/usage cho thấy request và chi phí tương ứng.

Nhớ rằng search snippet chỉ là manh mối. Mở các URL nguồn, kiểm tra ngày và ngữ cảnh trước khi coi nội dung là sự thật đã xác minh.
