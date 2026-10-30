GAME UI RESKIN — HƯỚNG DẪN SỬ DỤNG

ĐÂY LÀ GÌ?
Một bộ công cụ, hai phần phối hợp:
- Ứng dụng local đọc nguồn Unity và ghi reskin ra folder ngoài project.
- Plugin Figma nhập layer, lưu mapping và xuất sprite từ Assets gốc.
Không MCP. Không Play, build, reimport hoặc commit Unity. Không sửa file game.

CÀI VÀ CHẠY — MỘT PLUGIN GAME UI RESKIN
1. Copy toàn bộ folder công cụ ra nơi lâu dài ngoài project game.
   Khi chuyển máy khác, copy code, plugin, adapters, vendor và Start Local.cmd;
   không copy runtime hoặc connection.txt vì đây là dữ liệu riêng của máy/phiên nhập.
2. Cần Windows 64-bit và Python 3.12 có Tkinter. Thư viện trong vendor được đóng gói
   cho CPython 3.12 Windows 64-bit. Start Local sẽ kiểm tra trước khi mở ứng dụng.
3. Chạy Start Local.cmd, chọn project Unity và folder xuất ngoài project.
   Bấm Khởi động / Lưu nguồn rồi Copy mã kết nối.
   Không nhập folder prefab: công cụ tự lấy UI từ Addressables và UI phụ thuộc.
4. Trong Figma Desktop: Plugins → Development → Import plugin from manifest…
   Chọn plugin/manifest.json ĐÃ CÓ SẴN trong folder công cụ.
   KHÔNG New plugin, KHÔNG lấy ID, KHÔNG cấu hình manifest trên mỗi máy.
5. Chạy Game UI Reskin, dán mã local và bấm Kết nối.
   Nếu Figma hỏi quyền mạng local, cho phép localhost:43127.
6. Lần sau chỉ mở Start Local và chạy Game UI Reskin trong Figma.

DỌN CÁC MỤC DEVELOPMENT CŨ TRÊN MÁY HIỆN TẠI
- Giữ Game UI Reskin trỏ tới GameUIReskin/plugin/manifest.json.
- Ở danh sách Development, bấm dấu … cạnh Reskin UI và chọn Remove.
- Làm tương tự với Unity Battle Pass — original… nếu không còn dùng.
- Chỉ gỡ đăng ký plugin Development. Không xóa frame/asset trong file Figma.
- Nếu chuyển folder công cụ, gỡ đăng ký đường dẫn cũ rồi import manifest từ chỗ mới.

NHẬP MÀN
- Nguồn mặc định là Addressables đang dùng của project: settings → groups → entries.
- Entry là folder sẽ tự tìm prefab bên trong; lọc UI bằng root RectTransform, không dựa vào tên file.
- Tự lần theo prefab UI lồng, serialized prefab field, AssetReference GUID và config/ScriptableObject liên quan.
- Chặn vòng tham chiếu, loại trùng, dừng tại prefab ngoài UI; không duyệt tiếp cây gameplay.
- Chỉ index metadata GUID/path trên Assets để tra file, không đọc toàn bộ source hoặc asset ngoài UI.
- Danh sách mặc định hiện UI Addressable; bật Hiện UI phụ thuộc để xem prefab con.
- Mỗi mục có Addressables group/address và danh sách prefab UI liên quan.
- Nút Cập nhật danh sách sẽ đọc lại cấu hình/reference khi nguồn thay đổi.
- Phát hiện prefab thành phần không tự suy ra số item/trạng thái runtime; giới hạn runtime ở dưới vẫn áp dụng.
- Chọn màn trong danh sách, tùy chọn link Figma tham chiếu rồi Nhập vào Figma.
- Font gốc cần cài trên máy; thiếu font thì dừng và báo tên, không âm thầm dùng Inter.
- Mặc định tạo bản mới. Thay frame đã nhập chỉ xóa các frame màn tương ứng SAU KHI dựng bản mới thành công.
- Assets gốc cũ vẫn giữ để không làm mất reskin cũ. Mỗi lần nhập mới có thư viện asset theo session riêng.
- Import mới từ Unity không tự gộp các chỉnh sửa reskin từ session cũ.
- Bản xem trước và source mapping không phải bằng chứng visual đã khớp Unity/Figma.

RESKIN
1. Tab Reskin & xuất folder → Đi tới Assets gốc.
2. Mỗi file nguồn là một component đúng kích thước texture gốc, nền trong suốt.
   Thay ảnh hoặc thêm vector/layer BÊN TRONG component. Không đổi kích thước component.
   Một texture atlas là một asset gốc duy nhất; giữ nguyên vị trí các sprite trong atlas.
3. Chọn asset và bấm Cập nhật màn xem trước để local dựng lại các biến thể crop/nine-slice.
   Đây là thao tác chủ động, không tự cập nhật liên tục theo mỗi lần sửa.
4. Kiểm tra các màn, có thể Xuất PNG màn đang chọn và Tải mapping.
5. Bấm Xuất reskin ra folder. File PNG giữ đúng đường dẫn Assets/... và tên file trong game.
   Không tạo .meta. Không ghi trực tiếp vào Unity.
6. “Chỉ xuất asset đã thay đổi” so pixel PNG với baseline Figma tại lúc nhập.
   Thay đổi so với gốc vẫn tiếp tục được xuất ở các lần sau; không tự cập nhật baseline sau xuất.
   Nếu đăng ký baseline thất bại, bỏ chọn tùy chọn đó để xuất toàn bộ asset đã chọn.

SAU KHI TẮT MÁY / ĐÓNG PLUGIN
- Chạy lại Start Local.cmd từ ĐÚNG folder công cụ, giữ thư mục runtime.
- Các session local và mapping trên node được giữ; không cần nhập lại.
- Mở lại đúng trang Figma có thư viện Assets gốc.
- Khi có nhiều session trên trang, chọn frame màn hoặc thư viện Assets gốc muốn dùng TRƯỚC KHI chạy plugin.
- Không chạy đồng thời hai bản local trên cùng cổng.

PHẠM VI HIỆN TẠI — ĐỌC TRƯỚC KHI DÙNG
- Bộ đọc chung: RectTransform, hierarchy, prefab lồng nhau và override cơ bản,
  sprite riêng/sprite trong texture atlas, tint, text/font và layout ngang/dọc cơ bản.
- Battle Pass: có adapter đầu mùa chưa mua Crown Pass, level 1, 0/1, rows 1–4 của viewport đầu.
  Adapter dùng dữ liệu đã truy vết từ game, kiểm tra hash của logic/layout trước khi nhận runtimeReady.
  Countdown là số mẫu. Ba nhãn baked giữ nguyên theo yêu cầu. TMP outline là xấp xỉ; Spine là setup pose tĩnh.
- Các màn khác: CHƯA có dữ liệu runtime đã xác minh. Cần tick “Cho phép nhập cấu trúc prefab…”
  để nhập bản cơ sở; plugin đánh dấu rõ và không tuyên bố đã giống màn người chơi.
  Danh sách phần thưởng, Home/Shop lắp ghép lúc chạy, localization và trạng thái người chơi
  vẫn cần adapter/truy vết riêng trước khi tái tạo đầy đủ.
- Chưa hỗ trợ đầy đủ GridLayout, ContentSizeFitter/preferred sizing, Unity material shader,
  animation, Spine ngoài Battle Pass, mirror âm, rich text nhiều style và mọi loại prefab override.
- Link Figma tham chiếu hiện CHỈ LƯU LINK, KHÔNG tự đọc/copy layer từ file khác.
- Chỉ xuất reskin ảnh nguồn PNG. Text, vị trí/size và logic không được ghi ngược prefab/code.
- Nguồn JPG không xuất đè bằng PNG giả tên JPG; local báo rõ nguồn không hỗ trợ.

MAPPING VÀ LOG
- Node lưu guiSession, guiProject, guiKey; sprite có assetId/renderId và Unity source.
- Assets gốc lưu đường dẫn nguồn, kích thước và hash; wrapper màn lưu unityMapping.
- Export tạo reskin-export-report.json bên ngoài Assets trong folder xuất.
- Log local: runtime/local.log. Phiên nhập: runtime/session-*.json.
- Kết nối chỉ lắng nghe 127.0.0.1, kiểm tra mã ghép nối và Host. Không gọi server bên ngoài.
- Mã kết nối được giữ trong runtime/pairing.json, connection.txt và clientStorage Figma.
  Không gửi các file này cho người khác.

KIỂM THỬ ĐÃ CHẠY
- 12 test local: export thay đổi/không đổi, path/size, baseline, restore session,
  bảo vệ nguồn, PNG sai kích thước, chặn path traversal và output vào project.
- 5 test Addressables: folder entry/override entry riêng, UI lọc theo root, variant, vòng ref, config, AssetReference và refresh file mới.
- 5 test HTTP thật trên loopback: pairing, lỗi rõ ràng, CORS/preflight và status.
- Test mock Figma: 59 sprite/16 text/27 master, export/baseline, cập nhật theo mapping,
  mở lại, sai session, master đổi size, export lỗi, rollback khi import lỗi và thiếu font.
- Đã smoke test prefab thật: BattlePassModal, SettingModal, HomeSheet.
- Chưa chạy trực tiếp trong Figma Desktop. Cần import thật và kiểm tra visual trước khi dùng asset xuất.

TÀI LIỆU API THAM KHẢO
https://developers.figma.com/docs/plugins/working-with-images/
https://developers.figma.com/docs/plugins/manifest/
https://developers.figma.com/docs/plugins/plugin-quickstart-guide/

REFRESH NGUỒN VÀ NẠP LẠI CODE
- Trong plugin, Refresh nguồn Unity nằm ngay cạnh Kết nối.
  Đọc lại Addressables, GUID, prefab và cache nguồn, giữ nguyên lựa chọn còn tồn tại.
  Không tự thay/xóa frame hoặc Assets gốc đang reskin; nếu muốn dựng lại màn từ nguồn mới,
  chọn màn rồi Nhập vào Figma (mặc định Tạo bản mới).
- Sau khi sửa code local: bấm Khởi động lại local trong ứng dụng hỗ trợ.
  Giữ nguyên mã ghép nối, session và baseline đã lưu; không cần đóng cửa sổ.
- Khởi động lại chỉ điều khiển tiến trình do chính cửa sổ đó tạo, không kill tiến trình lạ.
- Sau khi sửa code.js/ui.html của plugin: vẫn phải đóng/chạy lại plugin Figma để nạp code mới.
- Lần đầu cập nhật có các nút này, cần mở lại app local và plugin một lần để nạp bản mới.

ASSET THEO MODAL VÀ COMPONENT LIÊN KẾT
- Mỗi modal có frame <Tên modal> — Assets đặt cạnh màn, chia thành thẻ theo lưới 3 cột.
- Component nguồn giữ nguyên kích thước pixel để xuất PNG. Không thu nhỏ component nguồn.
- Cùng một ảnh nguồn trong một phiên nhập chỉ có một component chính; các modal khác dùng instance dùng chung.
  Go to main component để tới nguồn; tránh detach hoặc override ảnh ở instance nếu muốn nhận cập nhật nguồn.
- Sprite thường, crop không xoay và nine-slice được dựng bằng instance có vùng clip; sửa component nguồn cập nhật trực tiếp.
- Tint màu RGB hoặc crop xoay vẫn dùng ảnh render; bấm Cập nhật sprite đặc biệt sau khi sửa nguồn.
- Khi thêm artwork mới trong component, đặt constraints phù hợp (Scale/Stretch) để nội dung co giãn theo instance.
- Mapping của từng sprite có masterNodeId và previewMode để truy ngược component nguồn và cơ chế cập nhật.
- Cần khởi động lại local, mở lại plugin và nhập bản mới để áp dụng. Frame cũ không tự chuyển thành instance.
- Đã kiểm thử mô phỏng và xuất PNG local; chưa xác nhận visual trong Figma Desktop.

AI RESKIN — CODEX LOCAL
- Tab AI Reskin trong Figma: chọn một sprite/component nguồn rồi bấm Lấy từ selection.
- Nhập prompt, chọn mức thay đổi (màu/chất liệu/thiết kế lại), 1–4 phương án, chi tiết cần giữ.
- Bảng màu tối đa 5 mã HEX, tham chiếu tối đa 3 ảnh (8MB/ảnh); link Figma chỉ là link, không tự đọc artwork.
- Codex CLI dùng tài khoản đang đăng nhập. Không cần API key trong plugin.
  Tool tìm codex.exe từ PATH hoặc thư mục cài Codex trên Windows. Phiên AI riêng, không resume chat đang mở.
- Prompt và ảnh đính kèm được xử lý bởi dịch vụ AI qua Codex, sử dụng hạn mức tài khoản hiện có.
- CLI được chạy ẩn, sandbox workspace-write trong runtime/ai/<job>, không đọc project Unity, không dùng MCP.
  Ảnh được đính kèm trực tiếp. Native image_gen lưu ảnh dưới CODEX_HOME/generated_images;
  local bridge chỉ đọc đầu ra trong thư mục ảnh này và sao chép vào runtime/ai/<job>.
- Ảnh tạo ra là PNG. Không tự vector hóa hay khôi phục layer thiết kế từ PNG.
- Chọn phương án -> Xem thử trong modal -> Áp dụng vào nguồn hoặc Hủy xem thử.
  Đóng plugin sẽ hủy bản xem thử chưa áp dụng. Hoàn tác lần áp dụng cuối khôi phục artwork trước đó.
  Artwork cũ giữ trong component ở trạng thái ẩn; không ghi đè file game.
- Instance cập nhật trực tiếp; sprite đặc biệt được đồng bộ qua local. Cần kết nối local khi xem thử.
- Đầu ra được đưa về kích thước nguồn. Kiểm tra hình, màu, alpha, viền nine-slice trước khi xuất về game.
  Mục giữ chi tiết là yêu cầu gửi model, không bảo đảm tuyệt đối về pixel.
- Có hủy yêu cầu, timeout 15 phút, lỗi rõ trong #error. Log và kết quả ở runtime/ai/<job>.
  Yêu cầu AI đang chạy không được khôi phục sau khi restart local. Chờ hoàn tất/hủy trước khi restart.
- Sau cập nhật: Khởi động lại local, đóng/chạy lại plugin; mở tab AI Reskin.
- Đã kiểm tra Codex CLI nhận ảnh trực tiếp và tạo PNG thật trên máy này; UI và preview/undo đã qua mock tests.
  Chưa thử trực tiếp tab mới trong Figma Desktop.

CẬP NHẬT PNG TRỞ LẠI UNITY — TÍNH NĂNG MỚI
- Thay đổi phạm vi so với bản trước chỉ đọc: tool có thể ghi PNG vào project SAU KHI duyệt và xác nhận.
- Tab Reskin & xuất folder -> Xuất reskin ra folder -> Cập nhật vào Unity — xem danh sách.
- Kiểm tra đúng project, danh sách PNG, kích thước và folder sao lưu -> Xác nhận thay N PNG trong Unity.
- Chỉ các PNG có mapping trong phiên nhập được thay. Không tạo/sửa .meta, GUID, prefab, C#, setting.
- Snapshot PNG trước/sau và bản sao .meta lưu ngoài project tại runtime/unity-imports/<id>/.
- PNG và .meta được kiểm tra hash trước khi ghi. Nguồn thay đổi thì dừng để tránh đè chỉnh sửa mới.
- Có nút Khôi phục PNG trước lần cập nhật này; dừng nếu PNG/.meta đã bị chỉnh tiếp sau lần cập nhật.
- Khi lỗi giữa chừng, tool cố khôi phục PNG đã ghi và báo rõ nếu cần khôi phục thủ công từ backup.
- Unity Editor tự nhận thay đổi khi quay lại; tool không mở Unity, chạy Play/build hay reimport toàn project.
- Bản xuất gần nhất là bản được duyệt; nếu sửa tiếp trên Figma, xuất lại trước khi cập nhật Unity.
- Cần khởi động lại local và đóng/mở plugin để nhận chức năng. Không cần tạo/import manifest mới.
- Đã kiểm thử ghi/khôi phục trên project giả; chưa áp dụng bất kỳ PNG nào vào project hole-blast.

CHỌN ASSET TỪ SELECTION VÀ PREVIEW TRONG LIST
- Tab Reskin & xuất folder -> Chọn asset từ selection.
  Chọn sprite/component, layer bên trong component, nhiều element hoặc cả modal/frame.
  Tool lần theo mapping, gộp asset trùng và chỉ tick các asset tương ứng.
  Không trộn selection thuộc nhiều phiên nhập vì các component nguồn có thể khác artwork.
- Danh sách asset có thumbnail từ component hiện tại của Figma, tên file, kích thước và đường dẫn.
  Có ô tìm kiếm; Làm mới preview để đọc lại ảnh sau khi chỉnh artwork. Thumbnail không đổi mapping hay kích thước nguồn.
- Chọn tất cả vẫn áp dụng toàn bộ asset của phiên, kể cả các dòng đang bị ẩn bởi tìm kiếm.
- Danh sách Nhập UI có preview dựng từ prefab, tải lần lượt khi cuộn tới dòng để tránh dựng toàn bộ cùng lúc.
  Chọn một UI sẽ có ảnh lớn hơn trong vùng chi tiết. Đây là ảnh nhận diện, không phải screenshot runtime.
  Text dùng font thay thế; layout có thể khác runtime; các item sinh bằng code có thể chưa hiện.
- Refresh nguồn Unity xóa cache preview. Cập nhật/khôi phục PNG Unity cũng làm mới cache.
- Sau cập nhật: Khởi động lại local, đóng/chạy lại plugin. Các màn và mapping đã nhập vẫn dùng được.
- Đã kiểm thử chọn lẻ/cả modal, loại trùng, preview assets, tìm kiếm và render 3 prefab thật; chưa thử UI trực tiếp trong Figma.

MAGIC RESKIN — MỘT NÚT, KHÔNG CẦN PROMPT
- Tab Magic Reskin dùng các asset đang tick trong tab Reskin & xuất folder, trong cùng phiên nhập.
  Có nút lấy theo selection hoặc chọn toàn bộ asset của phiên; tối đa 500 PNG mỗi bộ.
  Không tự khám phá/thay toàn bộ game hoặc trộn nguồn từ nhiều phiên nhập.
- Bấm Magic Reskin — tạo mẫu. Codex đọc contact sheet của toàn bộ asset, tự chọn chủ đề,
  bảng màu, chất liệu và phân loại vai trò. Không dùng preset ngẫu nhiên thay cho phân tích.
- Tạo 1–4 asset mẫu đại diện. Bấm xem thử để quan sát thay đổi trên modal (chưa phải cả modal đã reskin).
  Có thể Hủy xem thử rồi Thử phong cách khác; không cần viết prompt.
- Duyệt Áp dụng phong cách cho cả bộ mới chạy các asset còn lại, lần lượt, dùng cùng quy tắc và ảnh mẫu.
  Asset dùng chung chỉ tạo một lần. Asset được phân loại giữ nguyên không gọi tạo ảnh.
  Có tiến độ, ảnh trước/sau, lỗi từng asset, hủy và giữ các kết quả đã tạo.
- Alpha cuối cùng được giữ chính xác theo ảnh nguồn. Model được yêu cầu giữ bố cục, ký hiệu/chữ baked,
  atlas cells và nine-slice, cùng ý nghĩa màu trạng thái/độ hiếm; các chi tiết này vẫn cần artist kiểm tra.
- Chọn xem thử ảnh thành công -> Giữ N ảnh đã tạo trong Figma. Bộ gốc giữ bên trong component ở trạng thái ẩn.
  Có Hủy xem thử và Hoàn tác bộ vừa áp dụng. Chặn undo nếu artwork đã được sửa tiếp.
  Đóng plugin hủy các bản xem thử chưa giữ. Không tự ghi PNG vào Unity.
- Khi hài lòng: tab Reskin & xuất folder -> Xuất -> Duyệt cập nhật Unity như trước.
- Job và ảnh nằm trong runtime/magic/<id>; log tạo ảnh từng item ở runtime/ai/<childId>.
  Nút Lấy kết quả lần gần nhất đọc lại bộ của phiên hiện tại. Nếu local dừng giữa lượt,
  có thể tiếp tục sau khi đọc lại phong cách đã có; những lượt chưa xong có thể phải tạo lại.
- Dùng Codex CLI đang đăng nhập, không cần API key, không dùng MCP, không mở Unity/Play/build.
  Mỗi ảnh dùng hạn mức tài khoản và có thể mất vài phút; bộ lớn cần thời gian tương ứng.
- Sau cập nhật: Khởi động lại local và đóng/mở plugin để nạp tab mới.
- Đã kiểm tra phân tích phong cách bằng Codex thật trên 3 asset; hàng loạt, preview/undo,
  phục hồi và giữ alpha qua kiểm thử giả lập. Chưa chạy thử một bộ lớn thực tế trong Figma Desktop.

CONCEPT TÙY CHỌN TRONG MAGIC RESKIN
- Thêm ô Concept / prompt mong muốn ở đầu tab Magic, tối đa 2000 ký tự.
- Để trống vẫn tự chọn phong cách. Nếu nhập, Codex ưu tiên chủ đề/màu/chất liệu của concept.
- Concept lưu cùng job và được dùng cho phân tích, thử phong cách khác và tạo cả bộ.
- Chỉnh concept chỉ ảnh hưởng lượt tạo mẫu mới; duyệt bộ đã có vẫn dùng phong cách/concept của bộ đó.
  Dòng Concept của bộ này cho biết mô tả đã dùng. Lấy kết quả lần gần nhất nạp lại concept cũ.
- Cần khởi động lại local và đóng/mở plugin để nạp phần backend/UI mới.
- Đã kiểm tra UI gửi concept, backend truyền vào planner/batch, giới hạn đầu vào và khôi phục job.

XEM THỬ KHI ARTWORK NGUỒN ĐÃ ĐƯỢC CHỈNH
- AI đơn và Magic cho phép xem thử ảnh đã tạo ngay cả khi component nguồn được sửa/thêm element sau đó.
- Mỗi lần xem thử ghi nhận các child hiện tại cùng trạng thái ẩn/hiện rồi đặt ảnh AI làm overlay tạm.
  Hủy/hoàn tác/đóng plugin khôi phục những node đó, kể cả element artist mới thêm. Không xóa node nguồn.
- Nếu nguồn khác lúc tạo ảnh, UI hiện thông báo tham khảo, không chặn preview.
  Ảnh AI cũ không tự chứa hay tự ghép các chi tiết vừa thêm; chỉ được xem thử tạm cho đến khi giữ kết quả.
- Ảnh sai kích thước vẫn bị chặn trước khi thay bản xem thử hợp lệ đang có.
- Mapping, kích thước, phạm vi phiên nhập và bước duyệt cập nhật Unity giữ các kiểm tra hiện có.
- Chỉ cần đóng/mở plugin để nạp thay đổi UI/code. Với Magic, Lấy kết quả lần gần nhất để nạp lại bộ đã tạo.
- Kiểm thử mô phỏng đã bao phủ nguồn đổi, element mới, layer ẩn, hủy, undo, đóng plugin và batch Magic.
