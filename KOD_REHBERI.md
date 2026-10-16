# Kodu nereden okumalı?

Önce `app.py` dosyasındaki `create_app`, ardından `attendance_store.py` içindeki `AttendanceStore` sınıfını okuyun. Böylece ekrandaki bir tıklamanın dosyaya nasıl yazıldığını görürsünüz. Yüz tanımanın ayrıntıları ayrı bir adım olarak `face_manager.py` içindedir.

## Dosyaların görevi

| Dosya | Sorumluluğu |
|---|---|
| `app.py` | Ayarları okur, HTTP isteklerini doğrular, ilgili işleve iletir ve yanıtı döndürür. |
| `attendance_store.py` | Öğrencilerin var/yok durumunu, oturum kimliğini ve JSON kayıtlarını yönetir. |
| `face_manager.py` | Referans fotoğraflarını yükler, yüzleri bulur ve en yakın öğrenciyi arar. Yoklama dosyasına yazmaz. |
| `pdf_generator.py` | Verilen yoklama kopyasını PDF'e çevirir. Aktif oturumu değiştirmez. |
| `index.html` | Ekranın başlıklarını, form alanlarını ve düğmelerini tanımlar. |
| `app.js` | Kamera, arama, filtreler ve sunucu isteklerini yönetir. |
| `style.css` | Masaüstü/mobil yerleşimi ve görsel durumları tanımlar. |
| `tests/` | Kayıt kaybı, eski kamera yanıtı, hatalı dosya ve arayüz akışlarını sınar. |

## Bir öğrenciyi elle işaretlemek

1. Kullanıcı öğrenci satırına basar; `app.js` numarayı `/api/attendance/toggle` adresine gönderir.
2. `app.py` isteğin yerel kaynaktan ve mevcut tarayıcı oturumundan geldiğini denetler.
3. `AttendanceStore.toggle`, mevcut durumun bir kopyasını alır ve o öğrencinin durumunu değiştirir.
4. `_commit` önce yeni durumu dosyaya yazar, sonra bellekteki durumu değiştirir.
5. Arayüz güncel listeyi alır; arama ve durum filtresi korunur.

`manual_override`, kullanıcının kararının kameradan öncelikli olmasını sağlar. Elle “Yok” yapılan bir öğrenci, aynı oturumun sonraki karesinde otomatik “Var” olmaz.

## Kamera nasıl çalışıyor?

`app.js`, izin verilen kameradan bir kare alıp `/api/recognize` adresine yollar. `decode_image` biçimi ve boyutu denetler. `recognize_frame` hesap maliyetini düşürmek için uzun kenarı en fazla 640 piksele indirir; sonuç kutularını sonra asıl boyuta geri taşır.

`FaceManager.recognize` içindeki sıra şöyledir:

- `_detect_faces`: OpenCV ile yüz adaylarını bulur; göz yerleşimiyle yanlış adayları azaltır.
- `_crop_face`: yüzün çevresini küçük bir payla kırpar.
- `_represent`: Facenet'ten yüzü temsil eden sayı dizisini alır.
- `_match_embedding`: referanslarla cosine uzaklığını karşılaştırır. Eşik dışındaki veya iki kişiye çok yakın sonuçlar “Bilinmeyen” olur.

Sonuç, `AttendanceStore.mark_recognized` üzerinden kaydedilir. Tanıma başladığındaki `generation` ile güncel oturum kimliği farklıysa eski kare reddedilir. Bu sayede “Yeni yoklama” düğmesine basmadan önce çekilen bir kare yeni oturumu değiştiremez.

## Fotoğraf klasörü yenilenirken

`load_faces` bütün hazırlığı geçici listelerde yapar: dosyaları bulur, `_read_references` ile doğrular, `_make_embeddings` ile model çıktılarını hesaplar, en son `_commit` ile hazır listeyi değiştirir.

Numarası tekrar eden dosyalar, yüz bulunamayan fotoğraflar ve hatalı görüntüler durum bilgisine yazılır. Önceden çalışan bir referans bozulduğunda eski liste korunur. İlk açılışta model yüklenemezse geçerli fotoğraflardan gelen adlar manuel yoklama için kullanılabilir.

## Kayıt neden iki adımda yazılıyor?

`atomic_json` önce aynı dizinde geçici bir dosya oluşturur. Tamamını yazıp diske aktardıktan sonra `os.replace` ile hedef dosyanın yerine geçirir. Program yazma sırasında hata alırsa yarım dosya aktif kayıt hâline gelmez.

“Yoklamayı arşivle” aktif durumun ayrı kopyasını tutar. “Yeni yoklama” önce arşivler, sonra temiz oturum oluşturur. Liste yenileme ise mevcut oturumun işaretlerini korur. Bunlar birbirinden farklı işlemlerdir.

## Bu düzenlemede ne değişti?

Uzun yüz yükleme ve eşleştirme bölümleri adlandırılmış işlevlere ayrıldı; değişkenler ve Türkçe açıklamalar işin nedenini anlatacak şekilde düzenlendi. Tekrarlanan boş öğrenci durumu ortaklaştırıldı. API'deki görüntü ölçekleme ve güvenli fotoğraf yolu çözümü ayrıldı. PDF tablo üretimi kendi işlevine taşındı. Yeni bir framework veya veri modeli eklenmedi.

İşlev adları Python ekosistemiyle uyumlu İngilizce bırakıldı; açıklamalar Türkçe yazıldı. Kısa açıklamalar özellikle veri kaybını ve eski istekleri önleyen kararların yanında bulunur. Katkı bilgisi [README](README.md#katkılar) içindedir.
