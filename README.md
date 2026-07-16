# Kolik — İstatistiksel Maç Analiz Uygulaması

Kolik, futbol maçları için **Poisson dağılımına dayalı istatistiksel olasılık
analizi** sunan bir mobil (Android/Kivy) uygulamadır.

## ⚠️ Önemli: Bu uygulama ne YAPMAZ

- **Bahis sitelerinden (Nesine, Misli, Bilyoner vb.) veri scrape ETMEZ.**
  Bunun yerine [football-data.org](https://www.football-data.org) gibi açık,
  kullanım şartlarına uygun spor verisi API'lerini kullanır.
- **"Kesin sonuç" veya "garanti kazanç" iddiasında BULUNMAZ.** Tüm çıktılar
  "istatistiksel olasılık" olarak sunulur ve her ekranda bu netlik korunur.
  Futbol yüksek belirsizlikli bir spordur; hiçbir matematiksel model %100
  isabet garantisi veremez.
- Transfermarkt'ı otomatik olarak **scrape etmez** (bunun resmi bir API'si
  yoktur ve scraping ToS ihlalidir). Kadro değeri verisi, `data/market_values.csv`
  dosyasına kullanıcı tarafından manuel girilir; girilmezse bu faktör analizde
  nötr sayılır.

## Kurulum (Masaüstünde Test)

```bash
pip install -r requirements.txt

# football-data.org'dan ücretsiz API anahtarı alın:
# https://www.football-data.org/client/register
export FOOTBALL_DATA_API_KEY="buraya_kendi_anahtariniz"

python main.py
```

## Android APK Derlemesi (Linux/WSL üzerinde)

```bash
pip install buildozer cython
buildozer -v android debug
```

İlk derleme Android SDK/NDK indireceğinden 30-60 dakika sürebilir.
Derleme sonunda APK dosyası `./bin/` klasöründe oluşur.

**Not:** Mobil ortamda `export` ile ortam değişkeni ayarlamak mümkün
olmadığından, gerçek dağıtımda API anahtarını uygulama içi bir "Ayarlar"
ekranından kullanıcıya girdirip Kivy'nin `Store` API'siyle cihazda
saklamanız gerekir. Bu iskelet, hızlı başlamak için `os.environ` kullanır.

## Dosya Yapısı

```
kolik/
├── main.py              # Kivy App, ekran mantığı (UI controller)
├── kolik.kv              # Kivy arayüz tanımı (koyu zümrüt + altın tema)
├── analyzer.py            # Poisson tabanlı istatistiksel analiz motoru
├── data_fetcher.py        # Açık API'lerden veri çekme (fikstür, form, hava durumu)
├── models.py               # Ortak veri yapıları (dataclass'lar)
├── data/market_values.csv  # Kullanıcının manuel dolduracağı kadro değeri tablosu
├── buildozer.spec           # Android APK derleme konfigürasyonu
└── requirements.txt          # Python bağımlılıkları
```

## Metodoloji Özeti

1. **Beklenen gol (λ) hesabı**: Takımların son 5 maç formu, ev/deplasmana
   özel son 3 maç, kadro değeri oranı, hava durumu (yağış) ve ev sahibi
   avantajı ağırlıklandırılarak `analyzer.compute_expected_goals()` içinde
   hesaplanır.
2. **Skor olasılık matrisi**: İki bağımsız Poisson dağılımının dış çarpımı
   ile 7x7'lik bir skor olasılık matrisi kurulur.
3. **Pazar olasılıkları**: MS 1/X/2, KG Var/Yok, Alt/Üst, İY/MS kombinasyonları
   vb. bu matristen türetilir.
4. **Şeffaflık**: Sonuç ekranında her zaman "bu bir olasılık modelidir,
   garanti değildir" notu gösterilir.

## Sorumluluk Reddi

Bu uygulama eğitim ve kişisel istatistiksel analiz amaçlıdır. Bahis kararı
almak için tek başına kullanılmamalıdır. Geliştirici/asistan, üretilen
olasılık tahminlerinin doğruluğu veya sonuçları konusunda hiçbir garanti
vermez.
