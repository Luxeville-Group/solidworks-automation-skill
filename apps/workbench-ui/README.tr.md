# CAD Studio: Türkçe başlangıç rehberi

CAD Studio, CAD görevlerini yerel bir kuyruğa kaydeden ve seçtiğiniz Agent CLI üzerinden yürüten masaüstü uygulamasıdır. Arayüz Türkçedir; SolidWorks, AutoCAD, COM, Inspector, Policy Gate ve Reviewer Gate gibi teknik terimler İngilizce korunur. Geliştirici ayrıntıları [İngilizce README](README.md) ve [kuyruk protokolündedir](docs/automation-queue-protocol.md).

## Gerekenler

Gerçek CAD işlemleri için Windows, Python, en az bir Agent CLI ve göreve uygun lisanslı SolidWorks veya AutoCAD gerekir. Kaynak koddan React/Tauri uygulamasını geliştirmek veya derlemek için Node.js/npm ve Tauri'nin Windows derleme araçları da gerekir. Hazır bir uygulamayı kullanmak ile kaynak koddan derlemek farklı kurulumlardır.

## İlk kullanım

1. Bir proje oluşturun veya mevcut projeyi açın.
2. İstenen parçayı, ölçüleri, birimleri, malzemeyi, üretim yöntemini ve teslim biçimlerini yazın. Eksik mühendislik kararlarını ekipteki yetkili mühendisle netleştirin.
3. Agent Bridge içinde Agent ve model seçimini kontrol edin. Otomatik seçim, belirtilmeyen seçenekleri görev için belirler.
4. Ayarlar bölümünden yerel worker'ı başlatın ve görevi kuyruğa ekleyin.
5. Policy Gate onay bekliyorsa istenen işlemi inceleyin. Onaylanmayan görev yürütülmez.
6. Çıktıları ve Reviewer Gate bulgularını inceleyin. Gerekli insan incelemesinden sonra teslim edin.

P0, teslimi engelleyen kritik bulguları ifade eder. Mock çıktılar deneme amaçlı yer tutuculardır ve üretimde kullanılamaz. Otomatik kontrolün başarılı olması mühendislik onayı yerine geçmez.

## Kaynak koddan arayüzü çalıştırma

Depo kökünden:

```powershell
cd apps\workbench-ui
npm install
npm run dev
```

Bu komut tarayıcı önizlemesini açar. Masaüstü geliştirme için `npm run desktop:dev`, yürütülebilir dosya için `npm run desktop:build`, kurulum paketi için `npm run desktop:bundle` kullanılır. Tarayıcı önizlemesi gerçek masaüstü worker ve dosya erişiminin tümünü sunmaz.

## Temel terimler

| Türkçe | Korunan İngilizce terim |
|---|---|
| Eskiz | Sketch |
| Yuvarlatma | Fillet |
| Pah | Chamfer |
| Montaj | Assembly |
| Montaj ilişkisi | Mate |
| Sac metal | Sheet metal |
| Teknik resim | Drawing |
| Teslim dosyası | Artifact |
| Güvenlik/onay kontrolü | Policy Gate |
| Teslim incelemesi | Reviewer Gate |

Dosya uzantıları, komutlar, API adları ve JSON alanları çevrilmez. Eski sürümlerden gelen projelerde özgün metinler bulunabilir; mevcut proje verileri otomatik olarak yeniden yazılmaz.
