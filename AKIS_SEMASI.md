# YoklamaX akış şemaları

GitHub bu Mermaid şemalarını doğrudan çizer. VS Code Markdown önizlemesinde Mermaid desteği yoksa şema kaynağını metin olarak görebilirsiniz.

## Uygulamanın başlangıcı

```mermaid
flowchart TD
    A[python app.py] --> B[Ayarları ve klasör yollarını oku]
    B --> C{Çalışma modu}
    C -->|Manuel| D[students.json listesini doğrula]
    C -->|Yüz tanıma| E[Fotoğrafları doğrula ve yüzleri yükle]
    E --> F{Model hazır mı?}
    F -->|Evet| G[Otomatik tanıma ve manuel liste hazır]
    F -->|Hayır| H[Durumu göster ve manuel listeyi kullan]
    D --> I[Mevcut yoklama kaydını aç]
    G --> I
    H --> I
    I --> J{Kayıt geçerli mi?}
    J -->|Hayır| K[Dosyayı koru ve başlangıcı durdur]
    J -->|Evet veya ilk açılış| L[Yerel sunucuyu başlat]
    L --> M[Tarayıcıda öğrenci listesini göster]
```

İlk açılışta kayıt dosyası yoksa boş durumlu bir oturum oluşturulur. Demo seçeneği, daha önce tanımlanmış kurmaca listeyi ayrı veri diziniyle açar.

## Kamera ve manuel yoklama

```mermaid
flowchart TD
    A[Öğrenci listesi] --> B{Kullanıcının işlemi}
    B -->|Satıra dokun| C[Var veya yok durumunu değiştir]
    C --> D[Manuel kararı bu oturum için koru]
    B -->|Kamerayı başlat| E[Tarayıcı kamera izni]
    E -->|İzin yok| F[Açıklamayı göster]
    E -->|İzin var| G[Kamera önizlemesi]
    G --> H{Yüz tanıma hazır mı?}
    H -->|Hayır| G
    H -->|Evet| I[Kareyi doğrula ve küçült]
    I --> J[Yüzü bul ve Facenet ile karşılaştır]
    J --> K{Geçerli ve belirgin eşleşme?}
    K -->|Hayır| G
    K -->|Evet| L{Oturum aynı ve manuel engel yok mu?}
    L -->|Hayır| G
    L -->|Evet| M[Öğrenciyi var işaretle]
    D --> N[Değişikliği dosyaya yaz]
    M --> N
    N --> O{Yazma başarılı mı?}
    O -->|Hayır| P[Önceki durumu koru ve hata göster]
    O -->|Evet| Q[Belleği ve ekrandaki listeyi güncelle]
    Q --> A
```

Kamera kapatıldığında medya akışı ve bekleyen istekler durdurulur. Eşleşme için kimlik bilgileri dosya adından gelir; görüntüden isim tahmini yapılmaz.

## Arşiv, PDF ve yeni yoklama

```mermaid
flowchart LR
    A[Aktif yoklama] -->|Yoklamayı arşivle| B[Benzersiz JSON arşivi]
    A -->|PDF indir| C[Oturum tarihli PDF]
    A -->|Yeni yoklama| D[Kullanıcı onayı]
    D -->|Vazgeç| A
    D -->|Onayla| E[Önce mevcut oturumu arşivle]
    E --> F{Arşiv yazıldı mı?}
    F -->|Hayır| A
    F -->|Evet| G[Güncel listeyle yeni oturum aç]
```

Yeni oturumun yazımı da başarısız olursa eski aktif yoklama korunur; oluşturulmuş arşiv kullanılabilir. Kayıt biçiminin ayrıntısı `attendance_store.py` içindedir.
