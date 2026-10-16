# Fotoğraf ekleme

1. `.env` içindeki `YOKLAMAX_FACES_DIR` değerini kontrol edin. Yeni kurulumda `faces` kullanılır; mevcut kurulumunuz başka bir özel klasörü seçebilir.
2. Kişinin izinli fotoğrafını bu klasöre koyun. Dosya adı **numara_ad_soyad.png** biçiminde olmalıdır. `numara` yerine kişinin benzersiz öğrenci numarasını, `ad_soyad` yerine adını yazın.
3. Uygulamada **Listeyi yenile** düğmesine basın. Ad ve numara dosya adından okunur; yüzün görünümünden isim çıkarılmaz.

Her kişi için tek dosya kullanılır. Numara 1–32 ASCII rakam, ad 1–100 karakter olmalıdır. Türkçe harfler desteklenir; alt çizgiler ekranda boşluğa dönüşür. Aynı numaraya ait birden fazla fotoğraf varsa sistem birini rastgele seçmez, hata gösterir.

Fotoğrafta önden görünen, gözleri açık tek yüz bulunmalıdır. JPEG, PNG, WEBP veya BMP; en fazla **4 MB**, **4096 piksel kenar** ve **8 megapiksel** desteklenir. Bulanık, çok karanlık veya birden fazla kişi içeren fotoğrafları kullanmayın.

İsmi düzeltmek için numarayı koruyarak dosyayı yeniden adlandırın ve listeyi yenileyin. Mevcut yoklama işaretleri korunur. Klasörden kaldırılan kişiler, kayıt kaybı olmaması için aktif yoklamada kalır; **Yeni yoklama** güncel listeyle başlar.

Yüz tanıma hazır olduğunda **Kamerayı başlat** kullanın. Model hazır değilse yerel önizleme ve manuel işaretleme kullanılabilir. Kamera izni tarayıcıdan verilir. Göz yerleşimi kontrolü giysi gibi yanlış yüz adaylarını eler; canlılık kontrolü yapmaz.

Fotoğrafları ve yoklama kayıtlarını Git'e eklemeyin. `faces/` ve mevcut özel fotoğraf klasörü `.gitignore` kapsamındadır. Başka bir dizin seçerseniz onu da `.gitignore` dosyasına ekleyin.
