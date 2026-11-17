const common = {
  full_name: ["Tên đầy đủ sẽ hiển thị ở đầu CV.", "Ví dụ: Nguyễn Minh An"],
  email: [
    "Dùng email bạn thường kiểm tra để nhận liên hệ tuyển dụng.",
    "ten.cua.ban@example.com",
  ],
  phone: [
    "Số điện thoại nhà tuyển dụng có thể liên lạc với bạn.",
    "Nhập số điện thoại của bạn",
  ],
  location: [
    "Chỉ cần thành phố hoặc khu vực làm việc, không cần địa chỉ nhà chi tiết.",
    "Ví dụ: Hà Nội",
  ],
  linkedin: [
    "Đường dẫn trang LinkedIn cá nhân của bạn, có thể bỏ trống.",
    "https://www.linkedin.com/in/…",
  ],
  github: [
    "Đường dẫn GitHub có dự án bạn muốn giới thiệu.",
    "https://github.com/…",
  ],
  website: ["Website cá nhân, nếu có.", "https://…"],
  portfolio_url: [
    "Bộ sưu tập sản phẩm, bài viết hoặc thiết kế do bạn thực hiện.",
    "https://…",
  ],
  start_date: [
    "Tháng/năm bạn bắt đầu học, làm việc hoặc thực hiện dự án.",
    "Ví dụ: 09/2024",
  ],
  end_date: [
    "Tháng/năm kết thúc; để trống nếu vẫn đang tiếp tục.",
    "Ví dụ: 06/2026",
  ],
  job_title: [
    "Chức danh thực tế của bạn tại đơn vị này.",
    "Ví dụ: Thực tập sinh Frontend",
  ],
  company: ["Tên công ty hoặc đơn vị bạn từng làm việc.", "Nhập tên đơn vị"],
  is_current: ["Đánh dấu nếu bạn vẫn làm việc ở đây.", ""],
  achievements: [
    "Kết quả hoặc thành tựu thật. Chỉ nêu số liệu khi bạn có căn cứ; có thể bỏ trống.",
    "Mỗi dòng một kết quả bạn thực sự đạt được",
  ],
  technologies_used: [
    "Công cụ, ngôn ngữ hoặc phần mềm bạn trực tiếp sử dụng. Mỗi dòng một mục.",
    "Ví dụ:\nReact\nJavaScript",
  ],
  institution: [
    "Tên trường, học viện hoặc cơ sở đào tạo bạn đã theo học.",
    "Nhập tên trường / cơ sở đào tạo",
  ],
  degree: ["Tên bằng cấp hoặc chương trình đào tạo.", "Ví dụ: Cử nhân"],
  major: ["Ngành hoặc chuyên ngành học của bạn.", "Ví dụ: Công nghệ thông tin"],
  gpa: [
    "Tùy chọn. Ghi điểm kèm thang điểm để tránh hiểu nhầm.",
    "Ví dụ: 3.4/4.0, nếu đúng với kết quả của bạn",
  ],
  details: [
    "Môn học, đồ án hoặc kiến thức liên quan đến vị trí ứng tuyển. Mỗi dòng một ý.",
    "Bạn đã học và thực hành những nội dung nào?",
  ],
  project_name: [
    "Tên dự án học tập, cá nhân hoặc công việc của bạn.",
    "Ví dụ: Ứng dụng quản lý công việc",
  ],
  role: [
    "Vai trò và phần việc thực tế của bạn, đặc biệt khi làm theo nhóm.",
    "Ví dụ: Thành viên phát triển giao diện",
  ],
  technologies: [
    "Chỉ liệt kê công nghệ bạn đã dùng trong dự án, mỗi dòng một công nghệ.",
    "Ví dụ:\nReact\nPostgreSQL",
  ],
  contributions: [
    "Bạn trực tiếp làm gì? Viết bằng động từ hành động và giữ đúng mức độ đóng góp.",
    "Ví dụ: Hỗ trợ xây dựng giao diện danh sách công việc.",
  ],
  outcomes: [
    "Dự án đã hoàn thành hoặc tạo ra kết quả gì? Không bắt buộc có số liệu.",
    "Nêu sản phẩm, tính năng hoặc kết quả đã kiểm chứng",
  ],
  project_url: [
    "Link demo, mã nguồn hoặc trang giới thiệu dự án, nếu có.",
    "https://…",
  ],
  group: [
    "Đặt tên nhóm để nhà tuyển dụng dễ đọc kỹ năng của bạn.",
    "Ví dụ: Kỹ năng kỹ thuật / Kỹ năng mềm",
  ],
  items: [
    "Mỗi dòng một kỹ năng bạn thực sự có. Ưu tiên những kỹ năng liên quan công việc.",
    "Ví dụ:\nJavaScript\nLàm việc nhóm",
  ],
  activity_name: [
    "Tên hoạt động, câu lạc bộ hoặc chương trình bạn tham gia.",
    "Nhập tên hoạt động",
  ],
  organization: [
    "Đơn vị hoặc tổ chức đứng sau hoạt động.",
    "Nhập tên tổ chức / câu lạc bộ",
  ],
  period: [
    "Khoảng thời gian bạn tham gia hoạt động.",
    "Ví dụ: 09/2024 – 06/2025",
  ],
  summary: [
    "Viết 2–4 câu về nền tảng, điểm mạnh và định hướng nghề nghiệp. Có thể để trống để bổ sung sau.",
    "Bạn đang học/làm gì? Có kinh nghiệm hoặc kỹ năng nào nổi bật? Bạn mong muốn vị trí nào?",
  ],
};
const descriptions = {
  experience: [
    "Nêu công việc bạn thực hiện, cách làm và phạm vi đóng góp. Mỗi dòng một ý.",
    "Ví dụ: Hỗ trợ kiểm thử các chức năng đăng nhập và quản lý công việc.",
  ],
  project: [
    "Giải thích ngắn gọn dự án giải quyết vấn đề gì và gồm những chức năng nào.",
    "Ví dụ: Ứng dụng giúp nhóm tạo, theo dõi và cập nhật công việc.",
  ],
  involvement: [
    "Nêu phần việc và đóng góp của bạn trong hoạt động. Mỗi dòng một ý.",
    "Ví dụ: Hỗ trợ chuẩn bị tài liệu cho các buổi sinh hoạt câu lạc bộ.",
  ],
};
export function resumeFieldHint(section, key) {
  return key === "description"
    ? descriptions[section] || ["", ""]
    : common[key] || ["", ""];
}
