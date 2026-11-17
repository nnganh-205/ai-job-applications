export const faqItems = [
  [
    "Chưa có CV, tôi có thể bắt đầu từ đâu?",
    "Bạn có thể điền thông tin học vấn, kinh nghiệm, dự án và kỹ năng vào hồ sơ. Sau khi kiểm tra thông tin, hãy chọn mẫu và tạo CV của mình.",
  ],
  [
    "Tôi đã có CV, có cần nhập lại toàn bộ không?",
    "Bạn có thể tải CV dạng PDF hoặc DOCX có văn bản lên. Ứng dụng hỗ trợ bóc tách thông tin để bạn kiểm tra, sửa và xác nhận trước khi sử dụng.",
  ],
  [
    "AI có tự thêm kinh nghiệm hay kỹ năng không?",
    "Luồng chỉnh câu từ form sử dụng thông tin bạn đã nhập và các đề xuất được kiểm tra. Bạn vẫn cần đọc lại nội dung trước khi lưu hoặc tải CV.",
  ],
  [
    "Điểm phù hợp với việc làm có ý nghĩa gì?",
    "Điểm thể hiện mức đáp ứng yêu cầu công việc theo thông tin trong hồ sơ hoặc CV bạn chọn. Đây không phải xác suất trúng tuyển hay quyết định của nhà tuyển dụng.",
  ],
  [
    "Có thể đổi mẫu sau khi tạo CV không?",
    "Có. Bạn có thể thay bố cục, màu sắc và kiểu chữ trong trình chỉnh sửa. Đổi mẫu không làm thay đổi thông tin đã nhập.",
  ],
  [
    "Tôi có thể tải CV và tự ứng tuyển không?",
    "Bạn có thể xem trước và xuất PDF. Ứng dụng dẫn bạn tới nguồn tuyển dụng; bạn chủ động kiểm tra và thực hiện việc ứng tuyển.",
  ],
];

export const chatExamples = [
  {
    label: "Chỉnh câu CV",
    question: "Giúp mình viết kinh nghiệm này gọn hơn nhé.",
    answer:
      "Mình có thể đề xuất cách diễn đạt rõ và ngắn hơn từ nội dung bạn đã cung cấp. Bạn kiểm tra rồi chọn thay đổi phù hợp.",
    before: "Có hỗ trợ kiểm tra 25 bản ghi bằng SQL.",
    after: "Hỗ trợ kiểm tra 25 bản ghi bằng SQL.",
  },
  {
    label: "Đối chiếu việc làm",
    question: "Mình nên xem gì trước khi ứng tuyển vị trí này?",
    answer:
      "Hãy chọn CV và công việc bạn quan tâm. Mình sẽ giúp đối chiếu yêu cầu, chỉ ra bằng chứng đang có và những phần chưa đủ thông tin.",
    before: "Yêu cầu: có kinh nghiệm sử dụng SQL.",
    after: "Bằng chứng trong CV: kiểm tra 25 bản ghi bằng SQL.",
  },
  {
    label: "Chuẩn bị phỏng vấn",
    question: "Mình muốn tập giới thiệu về dự án đã làm.",
    answer:
      "Bạn có thể bắt đầu từ mục tiêu dự án, phần việc bạn đảm nhận và kết quả thực tế. Sau đó mở phần phỏng vấn để luyện câu trả lời.",
    before: "Dự án: bảng theo dõi tồn kho.",
    after: "Gợi ý trình bày: mục tiêu → phần việc → kết quả thực tế.",
  },
];
