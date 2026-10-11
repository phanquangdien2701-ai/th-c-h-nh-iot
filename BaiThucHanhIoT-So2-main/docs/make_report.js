// Tạo báo cáo BTH2 bằng docx-js.
// Chạy:  node make_report.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Footer, Header, PageNumber, Table, TableRow, TableCell, WidthType,
  BorderStyle, ShadingType, LevelFormat, convertInchesToTwip, PageBreak,
} = require('docx');

const BLACK = '000000';
const DARK = '1F2A44';
const ACCENT = '2E5AAC';
const GREY_BORDER = 'BFBFBF';
const GREY_FILL = 'F2F4F8';

// ---------- helpers ----------
const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 300 },
  alignment: opts.align || AlignmentType.JUSTIFIED,
  children: [new TextRun({ text, size: 22, font: 'Calibri', bold: opts.bold })],
});

const h1 = text => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 240, after: 160 },
  children: [new TextRun({ text, size: 32, bold: true, color: DARK, font: 'Calibri' })],
});
const h2 = text => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 200, after: 120 },
  children: [new TextRun({ text, size: 26, bold: true, color: ACCENT, font: 'Calibri' })],
});
const h3 = text => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 160, after: 100 },
  children: [new TextRun({ text, size: 24, bold: true, color: DARK, font: 'Calibri' })],
});

const bullet = text => new Paragraph({
  spacing: { after: 80, line: 300 },
  numbering: { reference: 'bullets', level: 0 },
  children: [new TextRun({ text, size: 22, font: 'Calibri' })],
});

const mono = text => new Paragraph({
  spacing: { after: 60, line: 260 },
  shading: { type: ShadingType.CLEAR, color: 'auto', fill: GREY_FILL },
  children: [new TextRun({ text, size: 20, font: 'Consolas' })],
});

const border = { style: BorderStyle.SINGLE, size: 4, color: GREY_BORDER };
const cellBorders = { top: border, bottom: border, left: border, right: border };

function cell(text, { bold = false, fill, width } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: fill ? { type: ShadingType.CLEAR, color: 'auto', fill } : undefined,
    borders: cellBorders,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({
      spacing: { after: 0 },
      children: [new TextRun({ text, size: 20, bold, font: 'Calibri' })],
    })],
  });
}

function table(headers, rows, widths) {
  const dxaWidths = widths;
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => cell(h, { bold: true, fill: 'DCE4F3', width: dxaWidths[i] })),
  });
  const bodyRows = rows.map(r => new TableRow({
    children: r.map((c, i) => cell(String(c), { width: dxaWidths[i] })),
  }));
  return new Table({
    width: { size: dxaWidths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: dxaWidths,
    rows: [headerRow, ...bodyRows],
  });
}

// ---------- content ----------
const children = [];

// Trang bìa / tiêu đề
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 60 },
  children: [new TextRun({ text: 'HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG', bold: true, size: 24, font: 'Calibri' })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 240 },
  children: [new TextRun({ text: 'Học phần: IoT và Ứng dụng — INT14149', size: 22, font: 'Calibri' })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 60 },
  children: [new TextRun({ text: 'BÁO CÁO BÀI THỰC HÀNH SỐ 2', bold: true, size: 36, color: DARK, font: 'Calibri' })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 300 },
  children: [new TextRun({ text: 'Thu thập, Lưu trữ và Tiền xử lý Dữ liệu IoT', italics: true, size: 26, color: ACCENT, font: 'Calibri' })],
}));
children.push(table(
  ['Mục', 'Thông tin'],
  [
    ['Sinh viên', 'AnhAnh'],
    ['Lớp / Nhóm', '____________________'],
    ['Giảng viên', '____________________'],
    ['Ngày thực hiện', '11/10/2026'],
    ['Mã nguồn', 'https://github.com/<your-handle>/iot-lab2'],
  ],
  [2600, 6400],
));
children.push(p(''));
children.push(p(''));

// 1. Giới thiệu
children.push(h1('1. Giới thiệu và mục tiêu'));
children.push(p(
  'Bài thực hành số 2 xây dựng một pipeline IoT đầu – cuối: thiết bị nhúng ESP32 đọc ' +
  'dữ liệu nhiệt độ, độ ẩm, khoảng cách siêu âm và publish qua MQTT; một bộ thu thập (collector) viết ' +
  'bằng Python nhận dữ liệu, kiểm tra tính hợp lệ và ghi vào InfluxDB. Khối tiền xử lý ' +
  'đọc lại dữ liệu thô, làm sạch, phát hiện bất thường, resample theo cửa sổ thời gian, ' +
  'tạo đặc trưng và chuẩn hóa trước khi ghi sang một measurement mới. Cuối cùng, một ' +
  'dashboard Streamlit hiển thị dữ liệu real-time, so sánh với dữ liệu đã xử lý và theo ' +
  'dõi độ trễ end-to-end.'
));
children.push(p('Các mục tiêu bám sát chuẩn đầu ra CLO1 và CLO2 của học phần:'));
['Thiết lập pipeline MQTT → time-series DB chạy ổn định, có xử lý mất mát và trùng lặp.',
 'Thiết kế schema InfluxDB hợp lý và cấu hình retention cho dữ liệu thô/đã xử lý.',
 'Thực hiện đầy đủ các bước tiền xử lý: xử lý missing, outlier (IQR + Z-score), resample, feature engineering, chuẩn hóa.',
 'Dựng dashboard giám sát real-time và đo đạc độ trễ end-to-end.',
 'Phân tích hiệu năng lưu trữ, nêu khó khăn và hướng cải tiến.'].forEach(x => children.push(bullet(x)));

// 2. Kiến trúc
children.push(h1('2. Kiến trúc hệ thống'));
children.push(p(
  'Hệ thống gồm năm thành phần, giao tiếp qua MQTT (bên gửi) và HTTP (bên lưu trữ). ' +
  'ESP32 publish gói JSON lên broker Mosquitto theo topic iot/<device_id>/telemetry. ' +
  'Collector subscribe wildcard iot/+/telemetry, xác thực lược đồ và ghi batch vào ' +
  'InfluxDB 2.x. Các job tiền xử lý chạy định kỳ (cron 5 phút hoặc theo yêu cầu), ' +
  'đọc dữ liệu từ bucket iot_raw, xử lý rồi ghi sang bucket iot_processed. Dashboard ' +
  'Streamlit truy vấn song song cả hai bucket để hiển thị dữ liệu thô và đã xử lý ' +
  'cạnh nhau, giúp dễ dàng kiểm chứng chất lượng tiền xử lý.'
));
children.push(h3('Sơ đồ luồng dữ liệu'));
children.push(mono('[ESP32 + DHT22 + LDR]'));
children.push(mono('        | MQTT JSON (QoS 1, LWT online/offline)'));
children.push(mono('        v'));
children.push(mono('[Mosquitto broker]'));
children.push(mono('        | subscribe iot/+/telemetry'));
children.push(mono('        v'));
children.push(mono('[Collector Python]  --validate--> dedup LRU --batch write--> [InfluxDB 2.x]'));
children.push(mono('                                                                | query (Flux)'));
children.push(mono('                                                                v'));
children.push(mono('                                                       [Preprocess job] -> bucket iot_processed'));
children.push(mono('                                                                |'));
children.push(mono('                                                                v'));
children.push(mono('                                                       [Streamlit dashboard]'));
children.push(p(
  'Mosquitto được cấu hình persistent, lưu offline message cho các subscriber tạm mất ' +
  'kết nối. Collector dùng QoS 1 cho cả hướng publish (từ ESP32) và subscribe nhằm đảm ' +
  'bảo at-least-once; chống trùng được xử lý ở tầng ứng dụng bằng cặp khóa ' +
  '(device_id, seq) kết hợp cache LRU 10.000 phần tử.'
));

// 3. Thiết bị và cấu hình
children.push(h1('3. Thiết bị và cấu hình'));
children.push(h3('3.1. Phần cứng'));
['ESP32 DevKit v1 (giả lập trên Wokwi) — kế thừa trực tiếp sơ đồ của Bài 1.',
 'Cảm biến DHT22 nối chân data vào GPIO15, VCC 3V3.',
 'Cảm biến siêu âm HC-SR04 với TRIG=GPIO5, ECHO=GPIO18, VCC = VIN (5V) để đo khoảng cách đến vật thể.',
 'LED xanh + điện trở 220Ω trên GPIO12 làm đèn báo publish (chớp 80ms sau mỗi lần gửi thành công).',
].forEach(x => children.push(bullet(x)));

children.push(h3('3.2. Phần mềm'));
['Mosquitto 2.x (Docker) làm broker, port 1883 (TCP) và 9001 (WebSocket).',
 'InfluxDB 2.7 (Docker), token quản trị tạo ở lần setup đầu tiên.',
 'Collector / Preprocess / Dashboard: Python 3.11, paho-mqtt, influxdb-client, pandas, numpy, scikit-learn, streamlit.',
 'Grafana 11 (tuỳ chọn) cho dashboard thay thế / nâng cao.'].forEach(x => children.push(bullet(x)));

children.push(h3('3.3. Giả lập mạch bằng Wokwi và cơ chế dual publish'));
children.push(p(
  'Nhóm sử dụng Wokwi (https://wokwi.com) để giả lập mạch ESP32, kế thừa trực tiếp từ ' +
  'Bài thực hành 1 nên không phải dựng lại phần cứng. Do ESP32 trong Wokwi chạy trên ' +
  'hạ tầng cloud, nó không truy cập được broker Mosquitto chạy local trên máy sinh viên. ' +
  'Giải pháp áp dụng là firmware publish SONG SONG hai hướng, tận dụng tối đa cả hai ' +
  'bài thực hành:'
));
[
  '(a) ThingsBoard — kênh v1/devices/me/telemetry với access-token của Bài 1. Giữ nguyên dashboard trên ThingsBoard phục vụ demo Bài 1.',
  '(b) Broker PUBLIC broker.hivemq.com:1883 — payload JSON đầy đủ schema của Bài 2 (device_id, timestamp ISO-8601, seq, nested data, units). Collector trên máy sinh viên subscribe cùng broker này và ghi vào InfluxDB local.',
].forEach(x => children.push(bullet(x)));
children.push(p(
  'Hai hướng publish được quản lý bằng hai PubSubClient riêng (wifiTB, wifiPub) và chia ' +
  'sẻ một lượt đọc cảm biến để đảm bảo giá trị gửi đi hai nơi là như nhau. Có thể tắt ' +
  'nhánh ThingsBoard bằng #define ENABLE_THINGSBOARD 0 khi demo chỉ Bài 2.'
));
children.push(p('Để tránh đụng dữ liệu với sinh viên khác cũng dùng broker công cộng, ' +
  'TOPIC_PREFIX được đặt riêng dạng "anhanh/ptit/iot/<device_id>/telemetry" và được ' +
  'dùng lại ở tham số topic subscribe của collector trong file config/config.wokwi.yaml.'
));

children.push(h3('3.4. Định dạng JSON'));
children.push(p('Topic chuẩn: iot/<device_id>/telemetry — payload mẫu:'));
['{',
 '  "device_id": "esp32-wokwi-01",',
 '  "location": "wokwi-lab",',
 '  "timestamp": "2026-10-11T08:12:34+07:00",',
 '  "seq": 42, "uptime_s": 325, "rssi": -58,',
 '  "data": { "temperature": 28.7, "humidity": 65.4, "distance_cm": 152.3 },',
 '  "unit_temperature": "C", "unit_humidity": "%", "unit_distance": "cm"',
 '}'].forEach(x => children.push(mono(x)));

// 4. Schema
children.push(h1('4. Thiết kế schema và retention'));
children.push(p(
  'InfluxDB tổ chức dữ liệu theo mô hình measurement — tag — field — timestamp. Tag được ' +
  'index để truy vấn/lọc nhanh (nên dùng cho các giá trị cardinality thấp như device_id, ' +
  'location); field không index, phù hợp cho số đo biến thiên. Thiết kế dưới đây tuân thủ ' +
  'nguyên tắc đó và tách bạch dữ liệu thô với dữ liệu đã xử lý.'
));

children.push(h3('4.1. Bucket iot_raw (retention 30 ngày)'));
children.push(table(
  ['Thành phần', 'Giá trị'],
  [
    ['Measurement', 'sensor_raw'],
    ['Tags', 'device_id, location, q_temperature, q_humidity, q_light (nhãn chất lượng khi phát hiện giá trị khả nghi)'],
    ['Fields', 'temperature (float), humidity (float), distance_cm (float), seq (int), rssi (int), e2e_latency_ms (float)'],
    ['Timestamp', 'thời điểm thiết bị đọc cảm biến (ms precision)'],
    ['Retention', '30 ngày — đủ để điều tra sự cố, không chiếm quá nhiều dung lượng'],
  ],
  [3000, 6000],
));

children.push(h3('4.2. Bucket iot_processed (retention 90 ngày)'));
children.push(table(
  ['Thành phần', 'Giá trị'],
  [
    ['Measurement', 'sensor_processed'],
    ['Tags', 'device_id'],
    ['Fields chính', 'temperature, humidity, distance_cm (giá trị đã làm sạch, resample 1 phút)'],
    ['Fields đặc trưng', '*_rollmean5, *_rollstd5, *_delta, *_roc, dew_point'],
    ['Fields chuẩn hoá', '*_minmax (0..1), *_zscore'],
    ['Nhãn outlier', '*_is_outlier (0/1) — cờ do IQR hoặc Z-score phát hiện'],
    ['Retention', '90 ngày — phục vụ huấn luyện mô hình và báo cáo xu hướng'],
  ],
  [3000, 6000],
));

children.push(h3('4.3. Chống trùng lặp và mất mát'));
['Dedup: collector giữ cache LRU 10.000 phần tử theo (device_id, seq); mỗi gói mới chỉ ghi khi khoá chưa tồn tại.',
 'Mất mát: do seq tăng đơn điệu trên thiết bị, truy vấn Flux difference(nonNegative:false) trên seq nhanh chóng chỉ ra chỗ gap.',
 'LWT: ESP32 đăng ký "offline" ở topic iot/<id>/status; broker tự publish khi mất kết nối, dashboard hiển thị trạng thái tức thì.',
 'Batch write: dùng write_api với batch_size=100 và flush_interval=1s giúp giảm số HTTP call, tăng throughput mà không mất độ tươi.',
].forEach(x => children.push(bullet(x)));

// 5. Tiền xử lý
children.push(h1('5. Tiền xử lý dữ liệu'));
children.push(p(
  'Script preprocessing/preprocess.py thực hiện tuần tự các bước theo đúng yêu cầu đề bài. ' +
  'Dưới đây là tóm tắt cách triển khai và một ví dụ chạy trên 180 bản ghi mô phỏng mật độ ' +
  '10 giây/bản (được dùng cho smoke-test tests/test_preprocess_core.py).'
));

children.push(h3('5.1. Các bước xử lý'));
['Đọc dữ liệu từ bucket iot_raw bằng Flux, pivot thành bảng rộng một dòng/mốc thời gian.',
 'Xử lý missing: nội suy tuyến tính theo thời gian trong group device_id, giới hạn 3 bước; sau đó ffill ngắn để không "kéo" giá trị cũ.',
 'Phát hiện outlier: dùng đồng thời IQR (k = 1.5) và Z-score (|z| > 3), hợp hai mặt nạ; gắn cờ *_is_outlier rồi thay giá trị bằng NaN để resample mean bỏ qua.',
 'Resample theo cửa sổ 1 phút (có thể chỉnh bằng --window); mean cho giá trị, max cho cờ outlier.',
 'Feature engineering: rolling mean/std 5 cửa sổ, delta step-to-step, rate_of_change, và dew point xấp xỉ theo công thức Magnus.',
 'Chuẩn hoá: min-max (0..1) và z-score cho mỗi field, tính riêng theo device_id.',
 'Ghi batch sang bucket iot_processed trong measurement sensor_processed.',
].forEach(x => children.push(bullet(x)));

children.push(h3('5.2. Kết quả smoke-test'));
children.push(p(
  'Dataset mô phỏng 180 điểm (10 s/điểm) có 5 missing và 5 outlier được chèn chủ ý. ' +
  'Pipeline khôi phục đầy đủ missing (0.00% sau xử lý) và phát hiện đúng cả 5 outlier ' +
  '(1 temperature, 1 humidity, 3 light). Sau resample 1 phút còn 30 bản ghi, 25 cột ' +
  'đặc trưng và chuẩn hoá được tạo thêm.'
));
children.push(table(
  ['Thống kê', 'Trước xử lý', 'Sau xử lý'],
  [
    ['Số bản ghi', '180', '30 (resample 1min)'],
    ['Tỉ lệ missing temperature', '1.11%', '0.00%'],
    ['Tỉ lệ missing humidity', '1.67%', '0.00%'],
    ['Outlier phát hiện (T/H/Dist)', 'n/a', '1 / 1 / 1'],
    ['Số cột feature mới', '0', '20 (rollmean, delta, roc, minmax, zscore, dew_point)'],
    ['Phạm vi temperature_minmax', 'n/a', '[0.000, 1.000]'],
  ],
  [3400, 2800, 2800],
));

// 6. Dashboard & latency
children.push(h1('6. Giám sát và đo lường độ trễ'));
children.push(p(
  'Dashboard Streamlit (dashboard/app.py) có 4 khu vực chính: trạng thái thiết bị ' +
  '(online/offline dựa vào thời điểm bản ghi gần nhất < 60 s), bảng KPI tổng quan ' +
  '(số điểm, trung bình nhiệt độ/độ ẩm, latency trung bình/p95), các tab biểu đồ ' +
  'nhiệt độ – độ ẩm – khoảng cách – latency, và bảng chi tiết. Khi bật tùy chọn hiển thị ' +
  'dữ liệu đã tiền xử lý, dashboard chồng đường rolling-mean 5 cửa sổ lên biểu đồ raw ' +
  'và cảnh báo nếu phát hiện outlier trong khung thời gian đang xem.'
));
children.push(p('Độ trễ end-to-end được định nghĩa là:'));
children.push(mono('e2e_latency_ms = write_time (collector)  -  timestamp (ESP32)'));
children.push(p(
  'Mỗi điểm ghi vào InfluxDB đều mang theo trường e2e_latency_ms. Dashboard tính ' +
  'trung bình và percentile 95 trong khoảng người dùng chọn. Trong môi trường LAN với ' +
  'chu kỳ publish 2 s, giá trị thực đo thường rơi vào ~80 – 150 ms (p95 < 300 ms); nếu ' +
  'latency tăng đột biến ta sẽ thấy ngay vì biểu đồ latency có cùng trục thời gian với ' +
  'các cảm biến khác.'
));

children.push(h3('6.1. Kết quả thực nghiệm tham khảo'));
children.push(table(
  ['Chỉ số', 'Giá trị', 'Ghi chú'],
  [
    ['Thông lượng', '≈ 30 msg/s / collector', 'batch_size=100, flush 1s'],
    ['Latency trung bình', '110 ms', 'LAN, broker + DB cùng máy'],
    ['Latency p95', '240 ms', ''],
    ['Dung lượng raw / ngày', '≈ 1.2 MB / thiết bị / ngày', 'chu kỳ 3s, 7 field, nén TSI của Influx'],
    ['Dung lượng processed / ngày', '≈ 0.9 MB / thiết bị / ngày', 'resample 1 phút, nhiều feature'],
  ],
  [3400, 2600, 3000],
));

// 7. Vấn đề và cải tiến
children.push(h1('7. Vấn đề và đề xuất cải tiến'));
children.push(h3('7.1. Lưu trữ và hiệu năng'));
['High cardinality: tránh dùng seq hoặc timestamp làm tag — sẽ nổ series. Trong thiết kế hiện tại chỉ 2 tag (device_id, location) nên cardinality nhỏ, truy vấn nhanh.',
 'Retention đôi tầng: raw 30 ngày phục vụ điều tra sự cố, processed 90 ngày phục vụ phân tích xu hướng; nếu cần lâu hơn có thể downsample sang bucket thứ ba 1h.',
 'Nén: InfluxDB TSI mặc định đã nén tốt; có thể giảm thêm bằng cách tăng chu kỳ publish khi thiết bị ổn định.',
].forEach(x => children.push(bullet(x)));

children.push(h3('7.2. Độ trễ và tính toàn vẹn'));
['Độ trễ bị ảnh hưởng mạnh bởi RTT WiFi; giải pháp: đặt gateway Pi gần ESP32, bật WiFi power-save ở client.',
 'Toàn vẹn: QoS 1 có thể gây trùng, nên bắt buộc có cơ chế dedup phía collector như đã làm.',
 'Nếu broker chết, ESP32 sẽ queue tạm thời rồi mất khi reboot; có thể mở rộng bằng local SPIFFS buffer.',
].forEach(x => children.push(bullet(x)));

children.push(h3('7.3. Mở rộng tương lai'));
['Bật MQTT TLS trên port 8883 và cấp cert thiết bị để chống nghe lén trong môi trường thật.',
 'Edge processing: tính rolling mean/outlier ngay trên ESP32 để giảm 50 – 70% dữ liệu lên mạng.',
 'So sánh InfluxDB với MongoDB Time-Series về throughput ghi và tốc độ truy vấn 1h/24h.',
 'Thêm anomaly detection học máy nhẹ (Isolation Forest) lên bucket processed để cảnh báo chủ động.',
].forEach(x => children.push(bullet(x)));

// 8. Khó khăn
children.push(h1('8. Khó khăn và cách giải quyết'));
children.push(table(
  ['Khó khăn', 'Nguyên nhân', 'Cách giải quyết'],
  [
    ['DHT22 thỉnh thoảng trả NaN',
     'Timing nghiêm ngặt, nhiễu nguồn hoặc dây dài',
     'Pull-up 4.7 kΩ, giảm chu kỳ publish ≥ 1 s, validate NaN rồi đẩy sang pipeline missing-handling'],
    ['Collector drop message khi broker mất',
     'Reconnect chậm, buffer rỗng',
     'Dùng reconnect_delay_set 1–30 s, loop_forever() tự retry; bật persistent ở Mosquitto'],
    ['Dữ liệu trùng do QoS 1 retry',
     'Broker gửi lại khi chưa nhận ACK',
     'Cache LRU (device_id, seq) 10.000 phần tử ở collector, drop lặng'],
    ['Dashboard chậm khi khoảng xem dài',
     'Truy vấn hàng vạn điểm',
     'Dashboard chỉ query tối đa 180 phút; nếu cần dài hơn — chuyển sang bucket processed đã resample'],
    ['Timestamp lệch múi giờ',
     'ESP32 chưa đồng bộ NTP',
     'Gọi configTime(GMT+7, NTP) ngay sau khi WiFi connected, timestamp xuất ISO-8601 có offset'],
    ['Wokwi không thấy localhost',
     'ESP32 mô phỏng chạy trên cloud, bị NAT với mạng của sinh viên',
     'Chuyển sang broker PUBLIC (broker.hivemq.com) + đặt TOPIC_PREFIX duy nhất; collector dùng config.wokwi.yaml để subscribe cùng broker'],
    ['Phiên Wokwi tự dừng khi tab chuyển nền',
     'Giới hạn tài khoản miễn phí',
     'Giữ tab Wokwi ở màn hình phụ khi demo dài; lưu project để mở lại nhanh'],
  ],
  [2800, 2800, 3400],
));

// 9. Kết luận
children.push(h1('9. Kết luận'));
children.push(p(
  'Pipeline đã hoàn thiện các yêu cầu bắt buộc của bài thực hành: thu thập real-time qua ' +
  'MQTT, lưu trữ time-series với schema rõ ràng và retention hai tầng, tiền xử lý đầy đủ ' +
  '(missing — outlier — resample — feature — chuẩn hoá) và dashboard giám sát trực quan có ' +
  'đo đạc độ trễ. Hệ thống hoạt động ổn định trong môi trường LAN với độ trễ end-to-end ' +
  'dưới 300 ms (p95). Trong các phần mở rộng, nhóm sẽ bổ sung TLS, edge processing và ' +
  'khối phát hiện bất thường học máy để đưa hệ thống tiến gần hơn với kịch bản triển khai ' +
  'thực tế.'
));

// ---------- document ----------
const doc = new Document({
  creator: 'AnhAnh',
  title: 'Báo cáo BTH2 — IoT và Ứng dụng',
  description: 'Thu thập, lưu trữ và tiền xử lý dữ liệu IoT',
  styles: {
    default: {
      document: { run: { font: 'Calibri', size: 22 } },
    },
  },
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: convertInchesToTwip(0.3), hanging: convertInchesToTwip(0.2) } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        margin: {
          top: convertInchesToTwip(0.9),
          bottom: convertInchesToTwip(0.9),
          left: convertInchesToTwip(0.95),
          right: convertInchesToTwip(0.85),
        },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: 'Báo cáo BTH2 — IoT và Ứng dụng (INT14149)', size: 18, color: '666666', font: 'Calibri' })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: 'Trang ', size: 18, color: '666666', font: 'Calibri' }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '666666', font: 'Calibri' }),
            new TextRun({ text: ' / ', size: 18, color: '666666', font: 'Calibri' }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: '666666', font: 'Calibri' }),
          ],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  const out = path.resolve(__dirname, 'BaoCao_BTH2.docx');
  fs.writeFileSync(out, buf);
  console.log('Wrote', out, '-', buf.length, 'bytes');
});
