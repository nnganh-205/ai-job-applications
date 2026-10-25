# Matching — evidence-v3

Phiên bản hiện tại bổ sung label/dimension/source_field, is_core và counted_in_score
trong từng assessment để Dashboard hiển thị chính xác các nhóm. Nhóm OR có một
assessment tổng hợp được chấm; các thành viên chỉ để đối chiếu, không tính hai lần.
Công thức và trọng số dưới đây giữ nguyên. Các ghi chú evidence-v2 mô tả bước sửa
one-of trước đó, không phải phiên bản cache hiện tại.

Đây là mức phù hợp với bằng chứng trong hồ sơ được xác nhận, không phải xác suất
được tuyển dụng. Các hằng số sau là giả thuyết kỹ thuật v1, chưa phải trọng số được
hiệu chỉnh bằng nghiên cứu thực nghiệm.

## Bổ sung sau phản hồi về “một trong những nội dung”

`requirement_type` và `operator` là hai trục riêng. “Có kiến thức và kỹ năng về một
trong những nội dung…” được giữ thành một nhóm ANY. Nếu không ghi rõ bắt buộc/ưu
tiên thì các options thuộc `unspecified_skills`, không tự chuyển thành required
hoặc preferred. Tiêu đề chung “Yêu cầu công việc” không đủ để nâng từng option của
nhóm này thành bắt buộc.

“Bắt buộc biết một trong…” hoặc nằm dưới “Required skills/Yêu cầu bắt buộc” giữ
mandatory ở cấp nhóm; chỉ cần đáp ứng một lựa chọn. “Ưu tiên biết một trong…” giữ
preferred. Hỗ trợ danh sách dấu phẩy, dấu chấm phẩy và bullets nhiều dòng; ngăn
scope lan sang yêu cầu độc lập kế tiếp.

Những options chưa xác định mức yêu cầu không tham gia điểm/core/gaps bắt buộc.
Algorithm version tăng lên evidence-v2 để không dùng lại score cache v1. Các trọng
số giữ nguyên. Frontend gom options thành một bullet ở đúng loại yêu cầu, không
hiện từng option dưới “bắt buộc”. Evidence vẫn được giữ trong dữ liệu để kiểm tra,
không hiển thị trên UI theo lựa chọn của người dùng.

JD đã lưu không bị rewrite; cần phân tích lại nguồn JD để cập nhật kết quả hiển thị.

## Evidence và yêu cầu

- JD có stable requirement IDs. Tên và evidence phải xuất hiện trong nguồn; yêu
  cầu không có evidence hợp lệ bị loại khỏi tính điểm và có warning.
- Profile dùng dữ liệu đã xác nhận. Các refs là JSON paths vào đúng profile snapshot;
  content hashes và algorithm_version được lưu để truy vết. Không dùng contact làm skill.
- Chỉ dùng alias nhỏ có nghĩa tương đương (Torch/PyTorch, ML/Machine Learning...);
  có word boundaries để Java không khớp JavaScript, SQL không khớp NoSQL.
- Evidence trong experience/project/involvement cho q=1, chỉ khai báo ở skills cho
  q=0.65, chỉ có trong education/coursework cho q=0.35. Đây là mức độ bằng chứng,
  không phải đo năng lực thật. Tên project đơn độc không chứng minh skill thực hành.
- Không có evidence: unknown, q=0. Chỉ ghi not_met khi có phủ định rõ, hoặc số tháng/
  bậc học xác định từ hồ sơ không đạt yêu cầu rõ ràng. Thiếu thông tin không đồng
  nghĩa ứng viên không có kỹ năng.
- Nhóm OR dùng max(q), đóng góp một lần. Các yêu cầu độc lập mặc định AND; all group
  không cộng thêm điểm vì đã tính các thành viên. Nhóm mơ hồ/chồng lấn có warning.
- Preferred experience/education được gom vào dimension ưu tiên; không trở thành
  yêu cầu bắt buộc. Technical requirement trùng skill không được tính hai lần.

## Công thức

| Dimension | Trọng số ban đầu |
|---|---:|
| Role/domain | 0.20 |
| Required skills | 0.35 |
| Preferred requirements | 0.05 |
| Experience | 0.15 |
| Practical evidence (project hoặc work) | 0.10 |
| Education | 0.10 |
| Other explicit requirements | 0.05 |

Với mỗi dimension có yêu cầu hợp lệ, lấy trung bình q của các yêu cầu, sau khi gom
OR. Dimension không có yêu cầu không tham gia mẫu số. Không loại một dimension
chỉ vì ứng viên không có evidence: dimension đó vẫn có điểm 0.

`S_base = 100 × sum(w_d × D_d) / sum(w_d đang áp dụng)`.

Practical evidence là tỷ lệ các required units có evidence dương trong project
hoặc experience. Role/domain dùng các core skills được nêu trong JD; nếu không có
core, dùng required-skills coverage.

Core gồm skill được JD nhấn mạnh rõ hoặc các required domain skills phù hợp với
vai trò (ví dụ Machine Learning đã có trong yêu cầu AI Engineer). Không tạo thêm
yêu cầu từ job title. Mapping domain nhỏ hiện hỗ trợ AI/backend/data.

`C = mean(q_core)`; khi có core: `S = min(S_base, 50 + 50 × C)`.

Vì vậy hồ sơ chỉ có Python/SQL nhưng không có evidence ML không thể vượt 50 cho
JD AI có core ML. Đổi trọng số/cap phải tăng algorithm_version và đánh giá lại.
Nếu không có yêu cầu chấm được, score=null thay vì tạo điểm mặc định.

Experience dùng hợp nhất các tháng làm việc liên quan, không cộng trùng; hỗ trợ
MM/YYYY, YYYY-MM, English month/year. Chỉ có năm hoặc thiếu ngày kết thúc thì không
tự điền tháng. Present tính tới as_of. Mức yêu cầu năm kinh nghiệm phải từ evidence;
2–3+ years lấy lower bound 2; tối đa 2 năm không phải minimum 2 năm.

Education dùng bậc học và một tập alias ngành nhỏ. Ngành tương đương chưa xác định
trả partially_met/unknown để review, không suy luận từ tên trường.

`evidence_coverage` là tỷ lệ requirement units khác unknown, không phải accuracy.
`core_coverage` là C. Điểm dimension trả về trên thang 100; applied_weights có tổng 1.

## API và lưu trữ

```json
POST /api/matches
{"profile_id": "id_đã_xác_nhận", "job_id": "id_đã_phân_tích"}
```

Chưa xác nhận profile hoặc không có JD: 404; ID sai: 422. Lưu kết quả immutable
dưới backend/storage/matches (đã gitignore), không sửa profile/JD. Gọi lại cùng
snapshot, IDs, ngày và algorithm trả cùng result_id; đọc bằng GET /api/matches/{id}.
GET /api/jobs/{id} và source saved_job_id tái sử dụng JD đã lưu mà không gọi model.
JSON JD cũ được đọc với defaults mới; không rewrite hàng loạt dữ liệu cũ.

## URL fetching

HTTP(S), cổng 80/443; chặn credentials, private/loopback/link-local/shared IP, mixed
public/private DNS, IPv4-mapped private và IPv6 tunneling. Resolve một lần và ghim
IP kết nối, giữ Host và TLS SNI, không tắt xác minh chứng chỉ. Cách giữ SNI theo
[HTTPcore extension chính thức](https://www.encode.io/httpcore/extensions/#sni_hostname).
Không dùng proxy môi trường. Kiểm tra từng redirect, tối đa 3 redirects, 2 MB sau
decompression, giới hạn pha IO 10s và kiểm tra tổng deadline 30s giữa các IO/chunks.
OS DNS resolver vẫn có timeout riêng; deadline không ngắt được một lời gọi DNS
đang chờ. Chưa xây worker/cancellation trong ngày 2.

Ưu tiên JobPosting JSON-LD, fallback HTML giữ paragraph/list/heading và inline text.
Không vượt CAPTCHA, không chạy JavaScript, không auto apply. Fetch thất bại: dán JD.

## Giới hạn nghiên cứu

Chưa dùng embeddings, taxonomy toàn ngành hoặc đánh giá chuyên gia. Không hiểu mọi
phủ định, quan hệ kỹ năng, equivalent qualification, nhóm OR lồng nhau hoặc số năm
theo từng công nghệ trong một câu dài. Cảnh báo và evidence cần được người dùng
review. Bộ tests kiểm tra tính chất/ranking mong đợi; không báo accuracy AI từ mock.
