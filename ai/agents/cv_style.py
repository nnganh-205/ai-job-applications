"""Genre guidance changes presentation, never the applicant's facts."""

def field_guidance(field):
    if field=='summary':
        return ('Viết đoạn tóm tắt hồ sơ ngắn gọn từ đúng nguồn: tình trạng hiện tại, phần việc/năng lực đã nêu, định hướng nếu người dùng đã cung cấp. '
                'Không ép mở đầu bằng động từ như bullet. Không tự thêm số năm, trình độ, chức danh, tính cách hoặc mục tiêu nghề nghiệp. '
                'Không biến sinh viên hay người đang học thành người đã tốt nghiệp.')
    if field=='role':
        return ('Chuẩn hóa vai trò thành cụm từ rõ ràng, trung tính. Không tự đặt chức danh hoặc cấp bậc. '
                'Tự làm toàn bộ dự án không tự động có nghĩa là trưởng nhóm, full-stack developer hoặc chuyên gia.')
    if field in {'achievements','outcomes'}:
        return ('Giữ ranh giới giữa phần việc, đầu ra, kết quả đã đo và mục đích. Không biến mục đích thành kết quả đã đạt; '
                'không biến chưa đo thành đã cải thiện. Chỉ đưa số liệu/thành tích có trong nguồn.')
    return ('Văn phong CV: động từ mô tả phần việc, đối tượng, cách làm/công cụ, đầu ra nếu đã có. '
            'Dùng đúng thuật ngữ của lĩnh vực trong nguồn; không tự chèn thuật ngữ công nghệ vào công việc ngành khác. '
            'Ưu tiên rõ ràng hơn sáo ngữ; không cố viết khác khi câu gốc đã rõ.')
