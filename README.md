# YoklamaX

Tek bilgisayarda kullanılabilen bir yoklama uygulaması. Öğrencileri listeden işaretleyebilir, kamera ile yüz eşleştirmeyi açabilir ve sonucu PDF olarak alabilirsiniz. Yoklama her değişiklikte yerel dosyaya yazılır; uygulamayı kapatıp açmak işaretlemeleri silmez.

Python tarafında **Flask, OpenCV, DeepFace/Facenet ve ReportLab**, arayüzde HTML, CSS ve JavaScript kullanılır. Ayrı veritabanı sunucusu veya frontend derleme adımı yoktur.

## Katkılar

İlk proje ve özgün kaynak kodu **Erhan ([@Quecc](https://github.com/Quecc))** tarafından hazırlanmıştır. Projenin amacı, kullanım kararları ve bu sürümdeki geliştirme talepleri de proje sahibine aittir.

Bu sürüm **insan katkısı + yapay zekâ desteğiyle** geliştirilmiştir. Kodun yeniden düzenlenmesi, hata düzeltmeleri, arayüz çalışması, testler ve dokümantasyonda **OpenAI Codex** kullanılmıştır. Bu açıklama katkıların kaydını tutar; herhangi bir yapay zekâ tespit aracının sonucu hakkında iddia içermez.

## Başlatma

Python **3.12 / 64 bit** ile doğrulandı. Windows'ta PowerShell üzerinden:

```powershell
git clone https://github.com/Quecc/yoklamaX.git
cd yoklamaX
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # Yalnız .env dosyanız henüz yoksa
.venv\Scripts\python.exe app.py --mode manual
```

Adres: **http://127.0.0.1:5050**. Başlangıçta liste boşsa kendi öğrenci listenizi veya fotoğraflarınızı ekleyin. Depoya öğrenci verisi, yüz fotoğrafı veya model ağırlığı dahil edilmez.

macOS/Linux'ta sanal ortamı `python3.12 -m venv .venv` ile oluşturun; komutlarda `.venv/bin/python` kullanın. `.env.example` dosyasını mevcut `.env` dosyanızın üzerine yazmadan kopyalayın.

### Fotoğraflarla yüz tanıma

1. `requirements-recognition.txt` bağımlılıklarını kurun.
2. `faces/` klasörünü oluşturun ve izinli referans fotoğraflarınızı ekleyin. Dosya adı `numara_ad_soyad.png` biçiminde olmalı; numara yalnız rakamlardan oluşmalıdır. Ayrıntılar: [Fotoğraf ekleme](FOTOGRAF_EKLEME.md).
3. Uygulamayı normal modda başlatın:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-recognition.txt
.venv\Scripts\python.exe app.py
```

Kendi fotoğraf klasörünüz zaten varsa `.env` içindeki `YOKLAMAX_FACES_DIR` değerini o klasöre ayarlayın. Mevcut kurulumun yerel ayarları korunur.

İlk yüz tanıma kullanımı Facenet ağırlıklarını indirir; sonraki açılışlarda `.models/` önbelleğini kullanır. Fotoğraflar harici bir tanıma servisine gönderilmez. Model hazır değilse manuel işaretleme ve kamera önizlemesi kullanılabilir.

Windows'ta TensorFlow kurulumu uzun dosya yolu hatası verirse projeyi kısa bir yolda kurun. Mevcut uzun yolda, **Y: boşsa**, geçici eşleme de kullanılabilir:

```powershell
subst Y: (Get-Location).Path
Y:\.venv\Scripts\python.exe -m pip install -r requirements-recognition.txt
subst Y: /D
```

Python 3.14 ile yüz tanıma bağımlılıkları doğrulanmadı. Bazı Windows kurulumlarında Microsoft Visual C++ Redistributable gerekebilir.

### Fotoğrafsız manuel liste

`data/live/students.json` dosyasına kendi öğrenci listenizi yazın. Dosya bir JSON dizisidir; her kayıtta metin türünde `id` (1–64 rakam) ve `name` (1–200 karakter) bulunur. Numaralar benzersiz olmalıdır. `[]` geçerli bir boş listedir.

`python app.py --mode manual` bu dosyayı okur. Listeyi değiştirdikten sonra **Listeyi yenile** düğmesini kullanın. Geçersiz bir dosya mevcut yoklamayı silmez.

Mevcut `--demo` seçeneği, önceki sürümden gelen üç kurmaca kaydı `data/demo/` altında açar; normal başlangıçta kullanılmaz. Bu düzenlemede yeni kişi veya yüz verisi üretilmedi.

## Günlük kullanım

1. Öğrenci listesini kontrol edin. Fotoğraf veya liste değiştiyse **Listeyi yenile** kullanın.
2. **Kamerayı başlat** düğmesine basıp tarayıcıdan kamera izni verin. Yüz tanıma hazırsa eşleşen kişiler “Var” olur.
3. Bir öğrencinin satırına dokunarak durumu elle değiştirin. Elle “Yok” yaptığınız öğrenci aynı oturumda kamera tarafından tekrar “Var” yapılmaz.
4. **Yoklamayı arşivle** bir arşiv kopyası oluşturur. **PDF indir** o anki yoklamanın raporunu verir.
5. **Yeni yoklama** mevcut oturumu önce arşivler, sonra yeni listeyi açar. Sayfayı yenilemek yeni yoklama başlatmaz.

Kamera izni için adresi `localhost` veya `127.0.0.1` üzerinden açın. Kamera durdurulduğunda medya akışı kapatılır. Yanlış eşleşmeleri listeden düzeltin.

## Ayarlar ve kayıtlar

`python app.py`, proje dizinindeki `.env` dosyasını okur. Göreli yollar proje dizinine göre çözülür.

| Ayar | Varsayılan | Kullanımı |
|---|---|---|
| `YOKLAMAX_MODE` | `recognition` | `manual` veya `recognition` |
| `YOKLAMAX_FACES_DIR` | `faces` | Özel referans fotoğraf klasörü |
| `YOKLAMAX_DATA_DIR` | `data/live` | Yoklama dosyalarının dizini |
| `YOKLAMAX_PORT` | `5050` | `--port` ile de değiştirilebilir |
| `YOKLAMAX_SECRET_KEY` | Başlangıçta rastgele | İsteğe bağlı kalıcı oturum anahtarı; Git'e eklemeyin |
| `YOKLAMAX_DEMO` | `0` | `1` mevcut kurmaca demo listesini açar |
| `DEEPFACE_HOME` | `.models` | Model önbelleğinin kökü |

`data/live/current.json` aktif oturumu, `data/live/records/` arşivleri tutar. Yeni kurulumda dizinler otomatik oluşturulur; migration veya veritabanı sıfırlama komutu gerekmez. Bozuk veya bilinmeyen sürümlü kayıt dosyası korunur ve başlangıç durdurulur; yedekten geri alınmalıdır.

Listeyi yenilemek mevcut işaretlemeleri korur. Listeden kaldırılan kişiler o oturumda tutulur; **Yeni yoklama** güncel listeyi esas alır. Dosya yazımı başarısız olursa bellekteki eski yoklama da korunur. Aynı veri dizinini birden fazla sunucu işlemiyle açmayın.

## Kodu inceleme

[Kod rehberi](KOD_REHBERI.md), dosyaların görevlerini ve okunacak sırayı açıklar. [Akış şemaları](AKIS_SEMASI.md), uygulamanın başlangıcını, kamera işlemini ve kayıt akışını gösterir.

VS Code'da `YoklamaX.code-workspace` dosyasını açabilirsiniz. Python/debugpy eklentileriyle **F5**, 5051 portunda ayrı `data/debug/` kayıtlarını kullanır. Böylece 5050'deki normal oturumla çakışmaz.

## Kontroller

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m compileall -q app.py attendance_store.py face_manager.py pdf_generator.py tests
node --check app.js
node --test tests/frontend.test.js
.venv\Scripts\python.exe -m pip check
```

Python biçimlendirmesi için `python -m ruff format app.py attendance_store.py face_manager.py pdf_generator.py` kullanılabilir. Testlerde geçici dizinler, sahte model yanıtları ve kimseyi temsil etmeyen piksel dizileri kullanılır; kişisel fotoğraf veya kamera gerekmez. Ayrı statik tip kontrolü ya da frontend build komutu yapılandırılmamıştır.

İsteğe bağlı `python scripts/check_recognition.py` gerçek model kurulumunu sınar; kimlik doğruluğu veya fiziksel kamera testi değildir. Bağımlılık denetimi: `python -m pip_audit`. Son kontrol sonuçları: [Doğrulama kaydı](VERIFICATION.md).

## Sınırlar

Sunucu yalnız yerel bilgisayara açıktır; kullanıcı hesabı ve çok kullanıcılı yetkilendirme bulunmaz. Yerel Host kontrolü, aynı kaynak denetimi ve POST isteklerinde oturuma bağlı CSRF doğrulaması uygulanır. Öğrenci dosyaları genel statik dizinden sunulmaz.

Eşleştirme, cosine uzaklığı ≤ 0.35 ve en yakın ikinci kişiye en az 0.02 fark koşullarını kullanır. Uzaklık bir doğruluk yüzdesi değildir. Göz yerleşimi kontrolü giysilerin yüz sanılmasını azaltır; kapalı göz, yan açı ve zayıf ışıkta gerçek yüzü de atlayabilir. Canlılık kontrolü yoktur; fotoğraf/video ile yanıltmaya karşı güvence verilmez.

Fotoğraflar, kayıtlar, `.env`, sanal ortam ve model önbelleği Git dışında tutulur. Eski sürümlerde yayımlanmış dosyalar Git geçmişinde bulunabilir; bu çalışma geçmişi yeniden yazmaz. DejaVu Sans fontunun lisansı [FONT-LICENSE.txt](FONT-LICENSE.txt) içindedir.
