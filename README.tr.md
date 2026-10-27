# SolidWorks Automation Skill — Türkçe başlangıç

**[English documentation](README.md)** · [Türkçe / English terimler](localization/TERMS.tr-en.md)

Bu depo, [özgün projenin](https://github.com/wzyn20051216/solidworks-automation-skill) Luxeville-Group tarafından Türkçe ve İngilizce kullanıma uyarlanan sürümüdür. Masaüstü arayüzü ve kullanım rehberleri Türkçedir; CAD terimleri İngilizce karşılıklarıyla korunur. Teknik belgeler, kod yorumları ve API adları İngilizcedir. CLI/API tanı mesajları Türkçe, İngilizce veya iki dilli olabilir.

## Nasıl çalışır?

```text
İstek → Codex / başka bir Agent → Skill veya MCP → Python / COM → SolidWorks → Dosyalar ve kontrol raporu
```

Skill, yapay zekâya iş akışını anlatan yönergeler ve yeniden kullanılabilir betikler içerir. MCP, aynı işlemleri araç çağrıları olarak sunar. SolidWorks ile iletişim çoğunlukla Windows COM API üzerinden kurulur; program ekranında fareyle koordinat seçmek temel yöntem değildir. SolidWorks penceresi yine açılabilir ve sonuçların görsel kontrolü gerekir.

**Bir komutun başarılı dönmesi, parçanın mühendislik açısından doğru olduğunu kanıtlamaz.** Sistem dosya, geometri ve yeniden açma kanıtlarını denetler; makine mühendisi ölçüleri, malzemeyi, toleransları ve üretilebilirliği doğrular.

## Hangi işler için kullanılabilir?

- Ölçüleri belirli parça (Part), delik, kanal, radyüs (Fillet) ve pah (Chamfer) oluşturma.
- Parametrik parça ailelerinde tekrar eden işlemler ve toplu dışa aktarma (Batch Export).
- Montaj (Assembly), montaj ilişkileri (Mate), özellikler ve malzeme listesi (BOM).
- Desteklenen iş akışlarında teknik resim (Drawing), STEP/PDF ve kontrol raporu üretme.
- Mevcut bir tasarımı kurallara göre inceleme; desteklenmeyen veya eksik girdili işlemleri durdurma.

Her özelliğin sınırı farklıdır. [Yetenek matrisi](capabilities.yaml) ve [alt skill rehberi](SUBSKILLS.md) esas alınmalıdır. Deneysel bir özelliğin listede bulunması, gözetimsiz üretime hazır olduğu anlamına gelmez.

## Ekip için ilk deneme

1. Makine mühendisi basit ve risk düzeyi düşük bir test parçası seçsin; ölçü, malzeme, delik konumları, tolerans ve çıktı biçimlerini yazsın.
2. Kurulu SolidWorks sürümü ve ortam `python scripts/cad_doctor.py` ile kontrol edilsin.
3. Codex önce planı ve eksik bilgileri çıkarsın. Örnek istek: “90 × 60 × 8 mm bir montaj plakası için plan hazırla. M5 vidalar için dört geçiş deliği istiyorum; delik konumlarını ben onaylayacağım. Önce varsayımları listele.”
4. Desteklenen akışla model oluşturulsun; SLDPRT, STEP, önizlemeler ve inceleme raporu birlikte kontrol edilsin.
5. Mühendis modeli SolidWorks içinde yeniden açıp ölçüleri ve unsur ağacını (Feature Tree) doğrulasın. Onaylanan örnek daha sonra şablon yapılabilir.

Bu örnek üretim ölçüsü önerisi değildir. Özellikle “M5 vida için delik” ifadesi, geçiş deliği (Clearance Hole) ile kılavuz deliği (Tapped Hole) arasında açıkça ayrıştırılmalıdır.

## Kurulum seçenekleri

Üç girişten biri yeterlidir: **Skill**, **MCP** veya **CAD Studio** masaüstü arayüzü. Hepsi aynı betik ve yetenek kayıtlarını kullanır.

Yerel SolidWorks işlemleri için Windows, lisanslı/kurulu SolidWorks ve uygun Python bağımlılıkları gerekir. Yerel kabul hedefi SolidWorks 2026'dır; farklı sürümlerde özellik doğrulaması yapılmalıdır.

Node.js/npm ve Git varsa mevcut kurucu:

```powershell
npx github:Luxeville-Group/solidworks-automation-skill
```

Bu kurucu birden fazla Agent dizinine kurulum yapabilir, Python bağımlılıklarını yükler ve MCP kaydını dener. [Kurucu kodu](install.js) incelenebilir.

**Python ile CAD işlemleri için Node.js/npm zorunlu değildir.** Depo Agent'ın tanıdığı skill dizinine alınarak Python bağımlılıklarıyla kullanılabilir; Python MCP sunucusu da ayrı çalıştırılabilir. JavaScript tabanlı toplu MCP kayıt aracı ise Node gerektirir. Bu çeviri değişikliğine yeni bir PowerShell kurucusu dahil değildir.

Ayrıntılar: [English kurulum rehberi](README.md#installation-and-entry-points), [MCP](mcp-server/README.md), [CAD Studio](docs/CAD_STUDIO_USER_MANUAL.md). Özgün deponun yayımlanmış kurulum paketleri bu Türkçe sürümle aynı kabul edilmemelidir.

## Durumları nasıl okuyacağız?

| Durum | Anlamı |
|---|---|
| `verified` | Belirtilen ortam ve örnek kapsamı için doğrulama kanıtı var. |
| `stable` | Yerleşik regresyon kontrolleri var; özellik sınırları yine geçerli. |
| `pilot` | Deneme ve mühendis kontrolü gerekiyor. |
| `blocked` | Bu ortamda otomatik teslim engelleniyor. |

Çeviri, önceki yerel SolidWorks testlerini yeniden yapmış veya parçayı üretime onaylamış sayılmaz. Türkçe SolidWorks arayüzüyle uyumluluk da ayrıca denenmelidir. Teknik resimdeki GB/T veya ISO varsayımları kendiliğinden TSE standardına dönüşmez.

## Verimlilik ve sonraki adımlar

En uygun başlangıç, mühendis tarafından onaylanmış bir şablonun kontrollü parametrelerle tekrarlanmasıdır. Önce başarı oranı, süre ve elle düzeltme ihtiyacı ölçülmelidir. Aynı deterministik işlem yüz kez yapılacaksa her seferinde modele yeniden akıl yürüttürmek yerine betik/şablon tekrar kullanılabilir. LLM gerektiren sınıflandırma ve planlama için model yönlendirmesi ayrıca ölçülerek tasarlanabilir; bu depodaki dil uyarlaması böyle bir yönlendirici eklemez.

Hata bildirirken sürümü, tekrarlama adımlarını ve gizli bilgilerden arındırılmış hata metnini paylaşın. Şirket çizimlerini veya erişim anahtarlarını genel Issue içine koymayın. [Güvenlik politikası](SECURITY.md).
