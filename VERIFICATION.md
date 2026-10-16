# Doğrulama kaydı — 17 Ekim 2026

Kaynak: `Quecc/yoklamaX`, başlangıç commit'i `dd11b9e`. Çalışma dalı: `codex/repair-and-verify`. Proje Python 3.12.14, Windows CPU ve Node.js ile kontrol edildi.

## Başlangıçta giderilen sorunlar

İlk çalıştırma Python 3.14 ortamında eksik `numpy` nedeniyle duruyordu. Bağımlılık listesi kodun kullandığı DeepFace ile uyuşmuyordu; Flask kökteki arayüz dosyalarını bulamıyordu; `.ttf` dosyası geçerli font değildi. Uyumlu bağımlılıklar, açık statik rotalar ve lisansıyla birlikte gerçek DejaVu fontu eklendi.

Yoklamanın bellekte kaybolması, liste yenilemede işaretlerin silinmesi, aynı saniyedeki arşivlerin çakışması ve eski kamera karesinin yeni oturumu değiştirmesi düzeltildi. Yerel erişim sınırı, CSRF doğrulaması, güvenli görüntü işleme ve kalıcı JSON kayıtları eklendi. Kullanıcının mevcut dosya düzeni ve fotoğrafları korundu.

## Bu sürüm

Python işlevleri okunabilir adımlara ayrıldı, ortak öğrenci durumu tanımı kullanıldı ve kritik kararların yanına Türkçe açıklamalar yazıldı. Arayüz sadeleştirildi; durum filtresi, açık işlem adları ve otomatik kayıt açıklaması eklendi. README, kod rehberi ve Mermaid akış şemaları hazırlandı. İnsan ve yapay zekâ katkısı README'de açıklandı. Yeni kişi veya yüz verisi üretilmedi.

## Sonuçlar

| Kontrol | Sonuç |
|---|---|
| Python unittest | **51/51 geçti** |
| JavaScript/Node testleri | **17/17 geçti** |
| Ruff kod denetimi | Temiz |
| Dört ana Python dosyasının Ruff biçimi | Uygun |
| Python compileall / JavaScript sözdizimi | Geçti |
| pip check | Bağımlılık çakışması yok |
| pip-audit | Kontrol anında bilinen açık bulunmadı |
| Gerçek Facenet + tanıma API'si | Mevcut altı referansın küçültülmüş JPEG kopyası kendi numarasıyla eşleşti: **6/6** |
| Fotoğraf sunumu | Asıl uygulamada altı yerel portre yüklendi |
| PDF | Türkçe metin, uzun ad, çok sayfa, oturum tarihi ve HTTP üretimi doğrulandı |
| Tarayıcı iş akışı | Manuel işaretleme, Türkçe arama, durum filtresi ve liste yenileme geçti |
| Arşiv / yeni yoklama | Geçici oturumda iki arşiv eski işaretlemeyi korudu; onay sonrası yeni oturum açıldı |
| Mobil görünüm | 390×844 boyutunda yatay taşma yok |

Gerçek model testi ve tarayıcıdaki değişiklikler ayrı geçici kayıt dizinlerinde yapıldı. Asıl yoklamanın öğrenci durumlarının kontrol öncesiyle aynı olduğu karşılaştırıldı. Kullanıcının fotoğrafları yalnız yerelde kullanıldı, kaynak deposuna veya paylaşılan rapora eklenmedi.

Regresyon testleri; atomik yazma hataları, manuel karar önceliği, eski oturum kareleri, hatalı/tekrar eden referanslar, belirsiz eşleşmeler, CSRF, güvenli DOM metni, kamera durdurulduktan sonraki yanıtlar ve filtre içindeki klavye odağını kapsar.

## Doğrulamanın sınırları

- Fiziksel kamera ve canlı kişi eşleşmesi bu kontrolde denenmedi. Referansın kendi küçültülmüş kopyasıyla eşleşmesi, canlı kullanım doğruluğu ölçümü değildir.
- Canlılık kontrolü ve çok kullanıcılı yetkilendirme bulunmaz.
- Tarayıcı indirmesinin yerel kaydetme diyaloğu bu turda denenmedi; PDF API çıktısı ve içeriği test edildi.
- Ayrı bir frontend build veya statik tip kontrolü yapılandırması yoktur.

Yerel uygulama `http://127.0.0.1:5050` adresinde normal yüz tanıma modunda çalıştırıldı. Özel fotoğraflar, yoklama kayıtları, `.env`, model ağırlıkları ve sanal ortam Git dışında tutuldu. Eski izlenen yoklama PDF'si disk üzerinde korunarak Git takibinden çıkarıldı; geçmiş commit'ler yeniden yazılmadı.
