HƯỚNG DẪN CHẠY

1. Cài Python 3.
2. Mở CMD trong thư mục này.
3. Chạy:
   pip install -r requirements.txt
4. Chạy:
   python app.py
5. Mở trình duyệt:
   http://127.0.0.1:5000

Ứng dụng dùng SQLite (app.db) để lưu tài khoản và tiến độ.
Tawk.to đã được gắn bằng mã widget bạn cung cấp.

Lưu ý: Đây là hệ thống điểm/nhiệm vụ, không xử lý nạp tiền, ngân hàng hay rút tiền thật.


GIAO DIỆN RESPONSIVE
- Cùng một website dùng được trên điện thoại, tablet và máy tính.
- Điện thoại: nút và ô nhập lớn, bố cục tự co.
- Máy tính: nội dung rộng và thoáng hơn.
- Khi đưa lên hosting, chỉ cần gửi cùng một URL cho mọi thiết bị.


CẬP NHẬT LUỒNG
- Sau khi người dùng chọn gói điểm, hệ thống chuyển ngay sang trang Chăm sóc khách hàng.
- Trang CSKH hiển thị rõ gói điểm và điểm thưởng đã chọn.
- Khi mở Tawk.to, website gắn thông tin gói điểm/điểm thưởng vào phiên chat bằng visitor attributes (nếu Tawk.to cho phép trong cấu hình hiện tại).
- Người dùng nhận mã từ CSKH rồi nhập mã để tiếp tục nhiệm vụ.


XÁC THỰC MÃ CSKH
- Mã không còn nhập tùy ý.
- CSKH vào: http://127.0.0.1:5000/cskh
- Mật khẩu mặc định khi chạy thử: 2509
- Trước khi đưa lên hosting, bắt buộc đổi ADMIN_PASSWORD.
- CSKH chọn đúng gói điểm rồi tạo mã.
- Mỗi mã chỉ dùng được 1 lần.
- Mã chỉ hợp lệ với đúng gói điểm đã chọn.
- Mã đã dùng sẽ bị từ chối.
- Khi mã hợp lệ, người dùng mới được mở phần nhiệm vụ.

Ví dụ đặt mật khẩu trên Windows CMD:
set ADMIN_PASSWORD=MatKhauManhCuaBan
python app.py


KHÓA GÓI THEO TỪNG KHÁCH
- Khách chọn gói nào thì gói đó được lưu vào tài khoản.
- Trang /cskh hiển thị tên, số điện thoại và đúng gói khách đã chọn.
- CSKH KHÔNG có danh sách để tự đổi sang gói khác.
- Nút cấp mã ghi rõ đúng gói của khách.
- Mã được gắn với chính tài khoản khách và đúng gói đó.
- Mã của khách A không dùng được cho khách B.
- Nếu khách đổi gói sau khi mã đã được cấp, mã cũ không mở được nhiệm vụ vì gói không còn khớp.


BẢN CHỐT: TAWK.TO + CHAT THẲNG + KHÓA GÓI
- Khách chọn gói nào, hệ thống lưu đúng gói đó vào tài khoản.
- Trang CSKH đọc gói trực tiếp từ tài khoản, không cho CSKH tự chọn gói khác.
- Nút "Nhắn chăm sóc khách hàng":
  + Nếu widget Tawk.to đã tải: mở ngay khung chat.
  + Nếu widget chưa tải: mở thẳng Direct Chat Link của Tawk.to.
- Khi widget hoạt động, website gắn thuộc tính:
  + goi-diem
  + diem-thuong
  vào phiên hỗ trợ để CSKH dễ đối chiếu.
- Mã do CSKH cấp được khóa theo đúng tài khoản + đúng gói + dùng 1 lần.


BẢN CRISP
- Đã thay Tawk.to bằng Crisp.
- Crisp Website ID: ea2b7ad7-0a85-484e-a27d-ab34143d0663
- Nút "Nhắn chăm sóc khách hàng" mở trực tiếp hộp chat Crisp.
- Khi khách mở chat, website gửi dữ liệu phiên:
  + goi_diem = gói khách đã chọn
  + diem_thuong = điểm thưởng tương ứng
- Hệ thống mã vẫn khóa theo đúng tài khoản + đúng gói + dùng 1 lần.
- CSKH cấp mã từ trang /cskh như bản trước.


XÁC THỰC MÃ THẬT
- Mã được lưu trong database SQLite.
- Mã phải tồn tại trong database.
- Mỗi mã gắn với đúng tài khoản khách.
- Mỗi mã gắn với đúng gói khách đã chọn.
- Mỗi mã chỉ dùng được 1 lần.
- Mã sai / sai tài khoản / sai gói / đã dùng đều bị từ chối.
- Chỉ sau khi mã hợp lệ, server mới mở phần nhiệm vụ.


LƯU TỪNG NHIỆM VỤ
- Mỗi nhiệm vụ có task_id riêng từ 1 đến 10.
- Khi Like, server ghi riêng user_id + task_id vào SQLite.
- Một tài khoản không thể cộng lại cùng một nhiệm vụ lần hai.
- Tải lại trang vẫn hiển thị đúng nhiệm vụ nào đã Like.
- Đăng nhập lại trên thiết bị khác vẫn lấy trạng thái từ database server.
- Tổng 10/10 được tính từ các bản ghi nhiệm vụ thực tế, không tin vào số đếm phía trình duyệt.
- Đủ 10 nhiệm vụ mới sinh mã kết quả KQ-XXXXXX.
