# Một RTX 3090, hai model để so sánh

Giữ một instance GPU. Lưu hai model trên ổ đĩa và nạp lần lượt từng model vào VRAM.
Không cần gọi Cloudflare/Groq cho các bước cài đặt, tải hoặc tạo model này.

## 1. Chọn máy trên Vast.ai

Nếu Instances đã có RTX 3090, dùng instance đó; không thuê thêm máy thứ hai.
Nếu chưa có: chọn template PyTorch Ubuntu có SSH, 1 RTX 3090 24 GB, ưu tiên RAM32GB trở lên, 80GB disk và On-demand. Kiểm tra giá GPU, disk, bandwidth và tốc độ tải mạng trước Rent. Thêm SSH public key trong Keys trước khi tạo instance.

Trong Instances, copy lệnh SSH/Connect. Các chỗ HOST và PORT bên dưới phải thay bằng thông tin SSH thực tế mà Vast.ai cung cấp. Có thể dùng địa chỉ proxy SSH của Vast; không tự thay bằng IP khác.

## 2. Trên server: kiểm tra GPU và cài Ollama

```bash
nvidia-smi
curl -fsSL https://ollama.com/install.sh | sh
mkdir -p /workspace/kltn-deploy
```

## 3. Trên máy Mac: chuyển script, Modelfile và trọng số fine-tune

Thay PORT và HOST bằng đúng thông tin kết nối. SCP dùng -P viết hoa.

```bash
scp -i /Users/nguyenngocanh/.ssh/vast_ai -P PORT "/Users/nguyenngocanh/Downloads/Documents/KLTN/output/deploy/vast-ollama/serve.sh" "/Users/nguyenngocanh/Downloads/Documents/KLTN/output/deploy/vast-ollama/Modelfile.finetuned" root@HOST:/workspace/kltn-deploy/
```

```bash
scp -i /Users/nguyenngocanh/.ssh/vast_ai -P PORT "/Users/nguyenngocanh/Downloads/Documents/KLTN/ai/models/cv-writer-8b-unsloth/writer-merged.gguf" root@HOST:/workspace/kltn-deploy/
```

Trọng số hiện tại khoảng6,7GB; file gốc trên Mac vẫn được giữ nguyên. Modelfile.finetuned chỉ đổi FROM thành đường dẫn tương đối; giữ nguyên template/tham số/few-shot của model đã triển khai.

## 4. Trên server: chạy Ollama và đăng ký cả hai model

Nếu đã có Ollama đang nghe cổng11434, không khởi động thêm bản thứ hai; cần dừng service cũ trước khi dùng cấu hình serve.sh.

```bash
nohup bash /workspace/kltn-deploy/serve.sh > /workspace/ollama-server.log 2>&1 &
```

```bash
curl -fsS http://127.0.0.1:11434/api/tags
```

```bash
cd /workspace/kltn-deploy
ollama create kltn-writer-8b-unsloth:latest -f Modelfile.finetuned
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
ollama list
```

Hai tên model:

- Fine-tune: kltn-writer-8b-unsloth:latest, trọng số nguồn khoảng6,7GB.
- Model lớn để thử: qwen3:30b-a3b-instruct-2507-q4_K_M, trọng số khoảng19GB theo Ollama.

serve.sh bật Flash Attention/KV q8_0, tối đa một model và một yêu cầu song song. Context mặc định server4K; yêu cầu API có thể ghi đè. File GGUF fine-tune đã merged nên không cần tải riêng base model hay train lại.

## 5. Trên Mac: tạo đường kết nối đến Ollama server

Mở một cửa sổ Terminal riêng và giữ lệnh này chạy:

```bash
ssh -i /Users/nguyenngocanh/.ssh/vast_ai -p PORT -N -L 11435:127.0.0.1:11434 root@HOST
```

Một Terminal khác kiểm tra danh sách model, không sinh câu trả lời AI:

```bash
curl -fsS http://127.0.0.1:11435/api/tags
```

Cổng11435 trên Mac khác cổng11434 của Ollama cục bộ. Không cần mở public cổng11434 của server.

## 6. Chọn model cho project

Chỉ chỉnh .env sau khi tunnel hoạt động và /api/tags có model tương ứng. Giữ nguyên thông tin Cloudflare/Groq.

Dùng fine-tune:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11435
WRITER_MODEL=kltn-writer-8b-unsloth:latest
REFINE_MODEL=kltn-writer-8b-unsloth:latest
LLM_CONTEXT_LENGTH=8192
```

Thử model lớn:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11435
WRITER_MODEL=qwen3:30b-a3b-instruct-2507-q4_K_M
REFINE_MODEL=qwen3:30b-a3b-instruct-2507-q4_K_M
LLM_CONTEXT_LENGTH=8192
```

Phải đổi cả WRITER_MODEL và REFINE_MODEL, rồi khởi động lại backend để áp dụng. Đây là lựa chọn lần lượt để so sánh; không đổi model fine-tune thành model khác và không ghi đè trọng số fine-tune. Dùng cùng một nội dung nguồn và tiêu chí khi thử, chỉ áp dụng đề xuất sau khi kiểm tra.

Trên server dùng ollama ps để kiểm tra model đã nạp và PROCESSOR. Khi chuyển model, có thể chủ động giải phóng model cũ bằng ollama stop TEN_MODEL trước khi gọi model mới. Bắt đầu với một người dùng, không nạp hai model cùng lúc trên3090. Khi nghỉ, dừng cả backend/tunnel hoặc đổi lại endpoint cục bộ để tránh gọi server đã tắt.

## 7. Kết thúc buổi thuê

Stop dừng tiền GPU nhưng vẫn giữ phí disk. Sao lưu kết quả cần giữ trước Destroy/Delete; Destroy xóa dữ liệu trên instance. Bản fine-tune gốc trên Mac không bị ảnh hưởng.

Tài liệu tham chiếu:

- https://docs.vast.ai/guides/get-started/quickstart
- https://docs.vast.ai/guides/instances/connect/ssh
- https://docs.ollama.com/linux
- https://docs.ollama.com/faq
- https://ollama.com/library/qwen3:30b-a3b-instruct-2507-q4_K_M
