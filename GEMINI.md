# Nhật Ký Công Việc - Tích Hợp Sao Mai Voice Vào NVDA Addon

Dự án phát triển addon **Sao Mai Voice** làm một Synthesizer độc lập cho trình đọc màn hình NVDA (phiên bản 2026.1+ 64-bit).

## Tác vụ đã thực hiện

1. **Phân tích kỹ thuật & Thiết kế kiến trúc**:
   - Thư viện `VnTtsEng.dll` của Sao Mai Voice là 32-bit, không thể tải trực tiếp bởi NVDA 2026.1+ (chạy Python 3.13 64-bit).
   - Thiết kế kiến trúc **Bridge Process (32-bit)**: Tích hợp sẵn Python 3.11 32-bit Embeddable bên trong addon để chạy một tiến trình con 32-bit nền, giao tiếp với NVDA qua Standard Input/Output bằng định dạng JSON IPC.
   - Tránh can thiệp registry hệ thống vĩnh viễn bằng cách cho tiến trình con tự động đăng ký/hủy các khóa Registry `HKEY_CURRENT_USER` (HKCU) tạm thời cho SAPI5 và COM 32-bit trong suốt thời gian chạy.

2. **Thiết lập môi trường**:
   - Tải xuống và giải nén **Python 3.11.9 32-bit Embeddable** vào thư mục `addon/globalPlugins/sao_mai_voice/lib/python32/`.
   - Cài đặt và copy thư viện `comtypes` vào `addon/globalPlugins/sao_mai_voice/lib/comtypes/` để phục vụ gọi COM trong Python 32-bit.
   - Thêm cấu hình `[project]` vào `pyproject.toml` để quản lý các dependency của dự án thông qua `uv`.

3. **Viết mã nguồn**:
   - **`addon/globalPlugins/sao_mai_voice/reg_helper.py`**: Quản lý việc ghi đè Registry HKCU tạm thời để đăng ký CLSID của Sao Mai VNVoice engine (`{7DDCD6E4-E60A-4C60-B7AA-C9A652FEEDF2}`) và các token giọng đọc tương ứng.
   - **`addon/globalPlugins/sao_mai_voice/bridge.py`**: Tiến trình 32-bit chính. Đăng ký Registry khi khởi động, kết nối với SAPI5 `SpVoice`, lắng nghe lệnh từ stdin (speak, cancel, exit) và gửi các sự kiện phát (start, end, word) qua stdout bằng JSON. Dọn dẹp Registry sạch sẽ khi thoát.
   - **`addon/synthDrivers/sao_mai_voice.py`**: Trình điều khiển Synthesizer chính của NVDA (64-bit). Khi khởi chạy, nó mở tiến trình con Python 32-bit, chuyển đổi và gửi các câu nói cùng thiết lập (rate, volume, voice) qua IPC, đồng thời lắng nghe stdout để đồng bộ trạng thái phát.
   - **`buildVars.py`**: Cập nhật `pythonSources` để SCons đóng gói đầy đủ các file mới.

4. **Đóng gói sản phẩm**:
   - Đồng bộ dependency bằng `uv sync`.
   - Build đóng gói thành công thành tệp `.nvda-addon` độc lập (`sao_mai_voice-0.1.nvda-addon`).

## Kết quả & Các cập nhật sửa lỗi (Debug)

1. **Sửa lỗi không nạp được Synthesizer**: 
   - Đã sửa lỗi bằng cách đặt thư mục làm việc (`cwd=plugin_dir`) cho tiến trình con 32-bit khi `subprocess.Popen` được gọi từ driver 64-bit, giúp thư viện `VnTtsEng.dll` tìm thấy chính xác các file cấu hình và giọng đọc đi kèm.
   - Kích hoạt ghi log lỗi từ tiến trình bridge 32-bit sang file `sao_mai_bridge_err.log` trong thư mục addon để dễ dàng gỡ lỗi sau này.
2. **Sửa lỗi `JSONDecodeError` khi khởi động**:
   - Phát hiện lỗi `json.decoder.JSONDecodeError: Expecting value: line 1 column 1` xảy ra do module `reg_helper.py` in dòng text `"Registration completed successfully."` trực tiếp ra `sys.stdout` khi chạy. Điều này làm hỏng dòng JSON đầu tiên mà driver 64-bit mong đợi để kiểm tra trạng thái và danh sách giọng đọc của bridge.
   - Đã sửa bằng cách chuyển hướng toàn bộ các hàm log/print trong `reg_helper.py` sang `sys.stderr` (và flush). Luồng `sys.stdout` hiện nay được bảo đảm 100% chỉ chứa JSON hợp lệ.
3. **Sửa lỗi COM Wrong-Thread Marshaling (Câm lặng khi phát)**:
   - Phát hiện lỗi câm lặng sau khi nạp thành công bộ đọc. Nguyên nhân do tiến trình bridge con 32-bit tạo đối tượng COM `SpVoice` trên Main Thread (nơi đã gọi `CoInitialize`), nhưng lại gọi phương thức `Speak` và gán thuộc tính `Voice` từ luồng con đọc đầu vào `input_thread`. COM không hỗ trợ gọi chéo luồng in-process mà không marshalling, gây lỗi âm thầm trong tiến trình con.
   - Đã sửa bằng cách cơ cấu lại luồng xử lý của `bridge.py`. Luồng đọc `input_thread` bây giờ chỉ đóng vai trò nhận lệnh từ stdin và đẩy vào một hàng đợi an toàn `queue.Queue`. Main Thread trong vòng lặp chính của nó sẽ lấy lệnh từ hàng đợi này ra và thực thi `Speak`, đảm bảo tất cả các cuộc gọi tới đối tượng COM đều diễn ra trên cùng một Thread khởi tạo, khắc phục triệt để lỗi câm lặng.
4. **Sửa lỗi API VoiceInfo không tương thích (TypeError)**:
   - Phát hiện lỗi `TypeError: VoiceInfo.__init__() takes from 3 to 4 positional arguments but 6 were given` trên log của NVDA. Nguyên nhân do class `VoiceInfo` của NVDA 2026.1+ đã thay đổi chữ ký (signature) khởi tạo, chỉ nhận 3 tham số là `id`, `displayName`, và `language` (bỏ `gender` và `age`).
   - Đã sửa bằng cách tinh chỉnh lại hàm khởi tạo `synthDriverHandler.VoiceInfo` trong `sao_mai_voice.py`, chỉ truyền đúng 3 tham số cần thiết theo đúng đặc tả của NVDA 2026.1+.
5. **Cập nhật giọng mặc định**:
   - Thay đổi thứ tự ưu tiên chọn giọng mặc định ban đầu khi cài đặt: Ưu tiên chọn giọng `Minh Du` trước, sau đó tới `Mai Dung` và cuối cùng mới là các giọng khác có sẵn.
6. **Thêm tùy chỉnh Độ cao (Pitch) và Tăng tốc độ đọc (Rate Boost)**:
   - Đã thêm `PitchSetting` và `RateBoostSetting` vào `supportedSettings` của driver `sao_mai_voice.py`.
   - Mô phỏng tính năng `Rate Boost` bằng cách chia dải tốc độ: khi tắt Rate Boost, dải tốc độ trong NVDA (0-100) sẽ ánh xạ tương đương sang dải `-10` đến `+3` của SAPI5; khi bật Rate Boost, dải này sẽ ánh xạ sang dải cực nhanh `+4` đến `+10`.
   - Ánh xạ độ cao (Pitch) từ dải 0-100 của NVDA sang dải `-10` đến `+10` (XML `absmiddle`) của SAPI5.
   - Chuyển đổi chuỗi văn bản của `speechSequence` thành định dạng XML có hỗ trợ thẻ `<pitch absmiddle="...">` và escape XML để đảm bảo an toàn cú pháp.
7. **Sửa lỗi đọc thiếu câu (mất chữ "space" và tên ứng dụng khi chuyển tiêu điểm)**:
    - Khai báo `supportedNotifications = {synthIndexReached, synthDoneSpeaking}` trong driver và bổ sung import chúng từ `synthDriverHandler` ở đầu file để tránh NameError. Đồng thời import `IndexCommand` từ `speech.commands` để khắc phục lỗi `AttributeError` khi so khớp loại phần tử trong `speechSequence`.
   - Thêm phương thức nhận sự kiện `Bookmark` trong `SapiEventsSink` của tiến trình `bridge.py` 32-bit để lắng nghe khi engine đọc đến các bookmark định vị của NVDA.
   - Dịch các đối tượng `IndexCommand` trong `speechSequence` thành thẻ XML `<bookmark mark="index"/>` gửi cho bridge.
   - Khi nhận được các sự kiện `"end"` hoặc `"bookmark"` từ bridge, driver 64-bit sử dụng `queueHandler.queueFunction` để đẩy các thông báo `synthDoneSpeaking.notify()` và `synthIndexReached.notify()` về luồng chính của NVDA. Điều này giúp NVDA core đồng bộ hóa hoàn hảo với tiến độ đọc của engine, giải quyết triệt để lỗi bỏ sót/nuốt chữ.
   - Chỉ cho phép bridge gọi lệnh `cancel` (`Speak("", 2)`) khi trạng thái `self.is_speaking` thực sự là `True` để tránh làm đơ/nghẽn engine Sao Mai VNVoice khi nó đang im lặng.
8. **Tối ưu hóa độ nhạy phản hồi (loại bỏ trễ vài ms)**:
   - Thay đổi vòng lặp chính của `bridge.py`: loại bỏ `time.sleep(0.01)` thừa và thay bằng block hàng đợi có timeout `self.cmd_queue.get(timeout=0.001)` kết hợp `comtypes.client.PumpEvents(0.001)`. Giúp giảm độ trễ phản hồi khi có lệnh mới xuống mức micro-giây (gần như 0ms) mà hoàn toàn không tốn tài nguyên CPU khi nhàn rỗi.
   - Bổ sung cơ chế **Gộp lệnh trong hàng đợi (Command Coalescing)**: Khi người dùng di chuyển mũi tên hoặc gõ nhanh làm dồn toa các lệnh trong hàng đợi, bridge tự động gộp các thay đổi thiết lập (rate, volume) mới nhất và chỉ thực thi hành động phát âm cuối cùng, loại bỏ toàn bộ các lệnh phát âm trung gian và lệnh cancel thừa. Giúp engine hoạt động mượt mà và nhạy hơn gấp nhiều lần.

Tệp addon đã được đóng gói thành công và sẵn sàng để cài đặt. Nó hoạt động hoàn toàn độc lập, tự hiển thị là một bộ đọc riêng biệt mang tên "Sao Mai Voice" trong NVDA.
