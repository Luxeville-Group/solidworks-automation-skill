import {
  Aperture,
  Archive,
  ArrowClockwise,
  CaretDown,
  ChatCircleText,
  Check,
  CubeFocus,
  Export,
  FilePlus,
  FolderOpen,
  GearSix,
  Graph,
  Question,
  ImageSquare,
  Layout,
  Lightning,
  Minus,
  PaperPlaneTilt,
  PencilSimple,
  Play,
  Ruler,
  ShieldCheck,
  Sparkle,
  SpinnerGap,
  Square,
  Trash,
  UploadSimple,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type CSSProperties, type ChangeEvent, type DragEvent, type PointerEvent as ReactPointerEvent, startTransition, useEffect, useMemo, useRef, useState } from "react";
import { ArtifactBrowser } from "./components/ArtifactBrowser";
import { AppUpdatePanel } from "./components/AppUpdatePanel";
import { ConversationControls } from "./components/ConversationControls";
import { EnvironmentRemediationPanel } from "./components/EnvironmentRemediationPanel";
import { ManualReviewPanel } from "./components/ManualReviewPanel";
import { ProjectSwitcher } from "./components/ProjectSwitcher";
import { TaskSequence } from "./components/TaskSequence";
import { PreviewShowcase } from "./preview/PreviewShowcase";
import { collectJobArtifacts, deliveryFormatStatus, groupedArtifacts } from "./domain/artifacts";
import {
  artifactVersionComparison,
  assessDelivery,
  backendDiagnosticsFor,
  createRunSnapshot,
  retryStageForJob,
  retryStageLabel,
} from "./domain/delivery";
import { conciseTaskTitle, jobDisplayTitle, jobStatusLabel } from "./domain/jobs";
import { isTauriRuntime, readPersistedState, writePersistedState } from "./persistence";
import {
  DEFAULT_PROJECT,
  duplicateProjectRecord,
  filterProjects,
  hasActiveProjectJobs,
  jobProjectId,
  latestProjectConversation,
  LEGACY_PROJECT_ID,
  newProjectId,
  normalizeProjectName,
  terminalProjectJobs,
} from "./domain/projects";
import type {
  AgentChatMessage,
  AgentConversation,
  AgentProviderId,
  ApiIntegrationConfig,
  ApiIntegrationMode,
  ApiProviderSummary,
  AppSettings,
  AppStoreMigrationStatus,
  AutomationJob,
  AutomationJobKind,
  CcSwitchSync,
  CodexConfig,
  HelpTopicId,
  ImportedWallpaper,
  KnowledgeBaseConfig,
  ManualReviewDraft,
  PresetWallpaperId,
  ProjectRecord,
  QueueEvent,
  QueueLogTail,
  RecentWallpaper,
  RuntimeHealth,
  SubmissionKind,
  WallpaperFile,
  WallpaperId,
  WallpaperMotionMode,
  WorkerLogEntry,
  WorkerStatus,
} from "./types";

const DEFAULT_WALLPAPER_URL = new URL("./assets/default-blossom-wallpaper.mp4", import.meta.url).href;
const DEFAULT_WALLPAPER_POSTER_URL = new URL("./assets/default-blossom-poster.webp", import.meta.url).href;
const FUJI_WALLPAPER_URL = new URL("./assets/wallpaper-fuji.webp", import.meta.url).href;
const ANIME_SKY_WALLPAPER_URL = new URL("./assets/wallpaper-anime-sky.webp", import.meta.url).href;
const TOKYO_NEON_WALLPAPER_URL = new URL("./assets/wallpaper-tokyo-neon.webp", import.meta.url).href;

const wallpapers: Array<{ id: PresetWallpaperId; name: string; hint: string; assetUrl?: string; credit?: string }> = [
  { id: "blossom", name: "Kiraz Gölgesi", hint: "Yerleşik hareketli duvar kâğıdı" },
  { id: "fuji", name: "Fuji Alacakaranlığı", hint: "CC0 · Alpsdake", assetUrl: FUJI_WALLPAPER_URL, credit: "Alpsdake · CC0" },
  { id: "anime-sky", name: "Mavi Gökyüzü", hint: "CC BY-SA · mendhak", assetUrl: ANIME_SKY_WALLPAPER_URL, credit: "mendhak · CC BY-SA 4.0" },
  { id: "tokyo-neon", name: "Tokyo Neon", hint: "CC BY-SA · Basile Morin", assetUrl: TOKYO_NEON_WALLPAPER_URL, credit: "Basile Morin · CC BY-SA 4.0" },
  { id: "blueprint", name: "Blueprint", hint: "Açık mavi mühendislik ızgarası" },
  { id: "studio", name: "Studio", hint: "Beyaz stüdyo ışığı" },
  { id: "mist", name: "Mist", hint: "Sabah sisi cam dokusu" },
];

const navItems = [
  ["project", "01 Genel bakış", Layout],
  ["model", "02 Modelleme", CubeFocus],
  ["holes", "03 Özellik (feature)", Ruler],
  ["drawing", "04 Çizim", FilePlus],
  ["check", "05 İncele", ShieldCheck],
  ["export", "06 Teslim", Export],
  ["settings", "Ayarlar", GearSix],
  ["help", "Yardım", Question],
] as const;
type ActiveTab = (typeof navItems)[number][0];

const pageCopy: Record<ActiveTab, { title: string; subtitle: string }> = {
  project: {
    title: "Proje çalışma alanı",
    subtitle: "Eskiz, parametre tablosu veya model dosyalarını sürükleyin; parça, montaj, muhafaza, fikstür, sac, çizim ve teslim görevlerini yerel CAD Agent ile yürütün.",
  },
  model: {
    title: "Modelleme merkezi",
    subtitle: "Genel parçalar, montajlar, fikstürler, sac parçalar, muhafazalar ve tersine modelleme şablonlarından görev başlatın.",
  },
  holes: {
    title: "Delikler, kanallar ve bağlantılar",
    subtitle: "Geçişli, havşalı ve dişli delikleri, oval kanalları, arayüz açıklıklarını, delik dizilerini ve montaj konumlama özelliklerini gerçek malzeme kesimiyle yönetin.",
  },
  drawing: {
    title: "Çizim merkezi",
    subtitle: "GB/T teknik resimleri, ölçü zincirleri, delik tabloları, teknik koşullar, antet ve DWG/DXF/PDF çıktıları.",
  },
  check: {
    title: "Kontrol noktaları",
    subtitle: "Policy Gate, Artifact Ledger, Reviewer Gate, biçim kontrolleri ve 3D baskı/CNC/sac üretim risklerini inceleyin.",
  },
  export: {
    title: "Teslim merkezi",
    subtitle: "SLDPRT, SLDASM, STEP, STL, DWG, DXF, PDF, PNG önizlemelerini, inceleme raporlarını ve Git teslim kayıtlarını düzenleyin.",
  },
  settings: {
    title: "Uygulama ayarları",
    subtitle: "Yerel Agent, CC Switch model yönlendirmesi, onay politikası, duvar kâğıdı, varsayılan standartlar ve çıktı klasörünü yönetin.",
  },
  help: {
    title: "Kullanım yardımı",
    subtitle: "Ortam hazırlığından, AI  seçiminden modelleme, inceleme ve teslime kadar tam iş akışı.",
  },
};

const SETTINGS_KEY = "cad-studio.settings.v1";
const QUEUE_KEY = "cad-studio.queue.v1";
const CHAT_KEY = "cad-studio.agent-chat.v1";
const CONVERSATIONS_KEY = "cad-studio.agent-conversations.v1";
const APP_VERSION = "0.3.4";
const LEGACY_CONVERSATION_ID = "conversation-legacy";
const manualReviewOptions = [
  ["native-open", "Dosya hedef CAD uygulamasında açıldı ve hata olmadığı doğrulandı"],
  ["dimensions", "Kritik ölçüler, toleranslar, datum ve konum ölçüleri kontrol edildi"],
  ["features", "Delik, kanal, diş, montaj ve gerçek geometrik özellikler kontrol edildi"],
  ["artifacts", "Bu yürütmenin teslim dosyaları, biçimleri, yolları ve sürümleri kontrol edildi"],
] as const;
const helpTopics: Array<{
  id: HelpTopicId;
  label: string;
  title: string;
  summary: string;
  items: Array<{ title: string; detail: string }>;
}> = [
  {
    id: "start",
    label: "Hızlı başlangıç",
    title: "Gereksinimlerden ilk yürütmeye",
    summary: "Önce ortamı doğrulayın, ardından şablon seçin veya gereksinimleri girin. Şablon yalnızca ayarları doldurur; görev ancak Yürüt seçildiğinde oluşturulur.",
    items: [
      { title: "Ortamı kontrol et", detail: "Ayarlar bölümünden Python, Agent CLI ve kullanılacak SolidWorks veya AutoCAD ortamını doğrulayın." },
      { title: "Gereksinimleri hazırlama", detail: "Kullanımı, kritik ölçüleri, malzemeyi, üretim yöntemini ve çıktı biçimini belirtin. Güvenlik parametrelerini ve montaj arayüzlerini AI tahminine bırakmayın." },
      { title: "Şablon seç", detail: "Modelleme, delik/kanal ve çizim kartları görev türünü doldurur. Aşağıdaki ayarları kontrol edip Yürüt düğmesini seçin." },
      { title: "Onay ve yürütme", detail: "Masaüstü CAD, tam yetki veya klasörler arası erişim onay gerektirir. Onaydan sonra yerel worker görevi yürütür." },
    ],
  },
  {
    id: "projects",
    label: "Projeler ve görevler",
    title: "Soldaki görev geçmişini yönetme",
    summary: "Proje, görevler ve  AI  konuşmaları yerelde ve birbirinden ayrı saklanır. Proje değiştirildiğinde yalnızca o projenin görevleri ve konuşmaları gösterilir.",
    items: [
      { title: "Projeyi değiştir veya sil", detail: "Proje değiştirmek veya oluşturmak için sol üstteki proje adını seçin. Silme ikinci onay gerektirir; etkin görevler iptal edilmeden proje silinemez." },
      { title: "Yeni görev", detail: "Yeni görev yalnızca ayar bölümünü açar; otomatik yürütmez ve görev geçmişine kayıt eklemez." },
      { title: "Bağımsız AI Konuşma", detail: "AI konuşma başlığından konuşma değiştirin veya oluşturun. Her konuşma kendi bağlamını, Agent sağlayıcısını ve model seçimini korur." },
      { title: "Model ve sağlayıcı", detail: "OpenAI Codex, Anthropic Claude Code, Google Gemini CLI  ve  OpenCode  ayrı gösterilir; CC Switch  içindeki gerçek modeller seçim listesine otomatik eklenir." },
      { title: "Çalışan görevler", detail: "Çalışan görev önce iptal edilmelidir; durum İptal edildi olduğunda silinebilir." },
    ],
  },
  {
    id: "status",
    label: "Durum açıklamaları",
    title: "Görev durumlarını anlama",
    summary: "Kenar çubuğu çıktı üretilip üretilmediğini gösterir; görev izleyici onay, inceleme ve hata durumlarını ayrıntılı korur.",
    items: [
      { title: "Sırada / Çalışıyor", detail: "Görev yerel kuyruğa alındı veya  Worker  tarafından alındı. Uzun süre heartbeat yoksa yürütücüyü yeniden başlatın." },
      { title: "Onay bekliyor", detail: "Görev masaüstü erişimi istiyor:  CAD,  tam yetki, ağ veya klasörler arası erişim için açık kullanıcı onayı gerekir." },
      { title: "Tamamlandı", detail: "Görev sonuçları ve teslim dosyaları üretildi. Mühendislik uyarıları varsa görev ayrıntıları hâlâ insan onayı ister." },
      { title: "Başarısız / İptal edildi", detail: "Başarısız görevler yeniden çalıştırılabilir; iptal etmek geçmiş kaydını otomatik silmez." },
    ],
  },
  {
    id: "delivery",
    label: "İnceleme ve teslim",
    title: "Dosyaların teslim edilebilirliğini doğrulayın",
    summary: "Dosya üretmek üretim kabulü değildir. Kritik ölçüleri, delikleri, kanalları, montajı ve çizimleri hedef CAD uygulamasında inceleyin.",
    items: [
      { title: "Çıktıları kontrol et", detail: "STEP, STL, SLDPRT, DWG, DXF veya PDF dosyalarının yolunu, boyutunu ve bu yürütmede üretildiğini doğrulayın." },
      { title: "Teslim kontrolünü görüntüle", detail: "Teslim merkezi teslim edilebilir, insan incelemesi bekliyor, engellendi veya kanıt eksik durumlarını gösterir. Kenar çubuğundaki tamamlandı durumu yalnızca çıktı üretildiğini belirtir." },
      { title: "Özgün uygulamada aç", detail: "Dosyayı SolidWorks veya AutoCAD ile açın; onarım uyarısı, eksik referans veya sürüm sorunu olmadığını doğrulayın." },
      { title: "Geometriyi kontrol et", detail: "Dış ölçüleri, delik çap ve konumlarını, duvar kalınlığını, dişleri, montaj çakışmalarını ve üretim yönünü kontrol edin." },
      { title: "Kısmi yeniden üretim", detail: "Başarısız veya inceleme bekleyen görevler yeniden başlama aşamasını gösterir. Yalnızca o aşama ve devamı tekrarlanır; eski çıktılar, hatalar ve inceleme kanıtları sürüm geçmişinde korunur." },
      { title: "İncelemeyi tamamla", detail: "İnceleme sayfasında gerçekten tamamlanan kontrolleri işaretleyip açıklama yazın; kayıt yerel görev meta verisine eklenir." },
    ],
  },
  {
    id: "troubleshooting",
    label: "Sorun giderme",
    title: "Sık karşılaşılan sorunlar",
    summary: "Önce görev kartındaki hataları, worker heartbeat durumunu ve Agent çıktısını inceleyin; ardından yeniden çalıştırmaya veya yürütücüyü yeniden başlatmaya karar verin.",
    items: [
      { title: "Tıklamadan sonra bekleme", detail: "Bekleme düğmesi mevcut aşamayı hemen gösterir. İlk ortam denetimi yavaş olabilir; sonraki denetimler önbelleği kullanır." },
      { title: "Worker Heartbeat yok", detail: "Yürütücüyü yeniden başlatın. Çalışan görevler önce sıraya döner; yeni worker bunları devralır." },
      { title: "Windows Erişim reddedildi", detail: "Yinelenen CAD Studio/worker örneklerini kapatıp yeniden deneyin. Kuyruk yazmaları kısa beklemelerle yeniden denenir." },
      { title: "Görev başarısız", detail: "Hatayı ve günlükleri görmek için görevi genişletin; girdileri veya ortamı düzeltip yeniden çalıştırın." },
    ],
  },
];
const defaultApiConfig: ApiIntegrationConfig = {
  mode: "codex_cli",
  agentProvider: "codex",
  providerName: "Codex CLI",
  endpoint: "Yerel Codex oturum bilgisi",
  model: "Codex ayarlarını kullan",
  keyStatus: "configured",
};
const agentProviderCatalog: Record<AgentProviderId, { name: string; company: string; protocol: string; model: string; models: Array<{ value: string; label: string }> }> = {
  codex: {
    name: "Codex",
    company: "OpenAI",
    protocol: "codex-exec-v1",
    model: "Codex ayarlarını kullan",
    models: [
      { value: "gpt-5.5", label: "GPT-5.5" },
      { value: "gpt-5.6-sol", label: "GPT-5.6 Sol" },
      { value: "gpt-5.6-terra", label: "GPT-5.6 Terra" },
    ],
  },
  claude: { name: "Claude Code", company: "Anthropic", protocol: "claude-print-v1", model: "Claude ayarlarını kullan", models: [] },
  gemini: { name: "Gemini CLI", company: "Google", protocol: "gemini-headless-v1", model: "Gemini ayarlarını kullan", models: [] },
  opencode: { name: "OpenCode", company: "Birden fazla sağlayıcı", protocol: "opencode-jsonl-v1", model: "OpenCode ayarlarını kullan", models: [] },
};

function ccSwitchProvidersForAgent(sync: CcSwitchSync | null, agentProvider: AgentProviderId) {
  if (!sync) return [];
  const grouped = sync.providersByAgent?.[agentProvider];
  if (grouped) return grouped;
  if (agentProvider === "codex") return sync.codexProviders || [];
  if (agentProvider === "claude") return sync.claudeProviders || [];
  if (agentProvider === "gemini") return sync.geminiProviders || [];
  return sync.opencodeProviders || [];
}

function activeCcSwitchProvider(sync: CcSwitchSync | null, agentProvider: AgentProviderId) {
  const providers = ccSwitchProvidersForAgent(sync, agentProvider);
  return providers.find((provider) => provider.active) || providers[0];
}
const wallpaperShots = [
  { x: 0, y: 0, scale: 1.04 },
  { x: -2.5, y: -1.5, scale: 1.13 },
  { x: 3, y: 1, scale: 1.18 },
  { x: -1, y: 2.5, scale: 1.09 },
];
const wallpaperMotionLabels: Record<WallpaperMotionMode, string> = {
  still: "Durağan",
  breathe: "Nefes",
  cinematic: "Sinematik kamera",
  follow: "İşaretçiyi izle",
};
const defaultKnowledgeBase: KnowledgeBaseConfig = {
  cloudEnabled: false,
  localRoots: [],
  endpoint: "",
  namespace: "mechanical-engineering",
  tokenEnv: "CAD_STUDIO_RAG_TOKEN",
  topK: 6,
};

const cadApplicationLabels: Record<CodexConfig["cadApplication"], string> = {
  auto: "AI uygulamayı seçsin",
  solidworks: "SolidWorks 3B modelleme",
  autocad: "AutoCAD 2B çizim",
  both: "SolidWorks + AutoCAD Birlikte kullanım",
};

const cadApplicationRoutes: Record<CodexConfig["cadApplication"], string> = {
  auto: "AI göreve göre uygulamayı seçer: 3B katı, montaj ve delik için SolidWorks; DWG/DXF/PDF, GB/T teknik resimleri ve toplu çizim düzenlemeleri için AutoCAD önceliklidir. Teslim paketinde ikisi birlikte kullanılabilir.",
  solidworks: "Yerel SolidWorks uygulamasını kullanın. solidworks-automation Python COM wrapper üzerinden 3B modelleme, montaj, gerçek delik açma, STEP/STL/SLDPRT dışa aktarma ve önizleme incelemesini yürütün.",
  autocad: "Yerel AutoCAD uygulamasını kullanın. autocad-automation Python COM/ActiveX wrapper üzerinden DWG/DXF/PDF çizimlerini, katmanları, ölçülendirmeyi, çerçeve/anteti ve uygulama içi önizleme incelemesini tamamlayın.",
  both: "Önce SolidWorks ile 3B katı, montaj, delik ve STEP/STL çıktıları oluşturun. Ardından AutoCAD ile DWG/DXF/PDF teknik resimlerini, delik/kanal konum ölçülerini, anteti ve çizim incelemesini tamamlayın.",
};

const codexTargets: Record<CodexConfig["target"], string> = {
  auto: "AI otomatik belirlesin",
  general_part: "Genel parça modelleme",
  assembly: "Montaj ve kısıtlar (mates)",
  shell: "3D Baskı muhafazası modelleme",
  fixture: "Aparat/Fikstür/Braket",
  sheet_metal: "Sac açınımı ve büküm",
  holes: "Delik/kanal/Diş (thread)/Dizi (pattern)",
  drawing: "GB/T CAD Çizim",
  package: "Teslim paketini düzenle",
  reverse: "Tersine modelleme/Eskizi yeniden oluştur",
  skill: "Skills Standartları belgele",
};

const taskTemplates: Array<{
  key: string;
  tab: ActiveTab;
  title: string;
  detail: string;
  target: CodexConfig["target"];
  output: CodexConfig["expectedOutput"];
  icon: typeof CubeFocus;
}> = [
  { key: "part", tab: "model", title: "Genel parça", detail: "Extrude, revolve, delik/kanal, chamfer, fillet ve parametre tablosu modelleme", target: "general_part", output: "cad_files", icon: CubeFocus },
  { key: "assembly", tab: "model", title: "Montaj (assembly)", detail: "Parça içe aktarma, datum constraints, çakışma kontrolü ve patlatılmış görünüş hazırlığı", target: "assembly", output: "cad_files", icon: Graph },
  { key: "fixture", tab: "model", title: "Fikstür ve bağlama aparatları", detail: "Konumlama pimleri, sıkıştırma noktaları, montaj delikleri, hafifletme kanalları ve  CNC İşlenebilirlik", target: "fixture", output: "cad_files", icon: Aperture },
  { key: "sheet", tab: "model", title: "Sac parça", detail: "Büküm, açınım, K faktörü, delik boşlukları ve DXF açınım çıktısı", target: "sheet_metal", output: "drawing_package", icon: Layout },
  { key: "shell", tab: "model", title: "Elektronik muhafaza", detail: "Duvar kalınlığı, snap-fit, vida yuvaları, arayüz açıklıkları ve  3D Baskı kısıtları", target: "shell", output: "cad_files", icon: Archive },
  { key: "reverse", tab: "model", title: "Tersine yeniden modelleme", detail: "Resim, eskiz veya eski modelden parametrik feature tree oluşturun", target: "reverse", output: "cad_files", icon: ImageSquare },
  { key: "holes", tab: "holes", title: "Delik/kanal tasarımı", detail: "Geçişli, havşalı ve dişli delikler, oval kanallar, arayüz kanalları ve delik tabloları", target: "holes", output: "cad_files", icon: Ruler },
  { key: "threaded-holes", tab: "holes", title: "Dişli delik", detail: "M3/M4/M5/M6 Kılavuz deliği çapı, diş derinliği, ağız pahı ve hole callout", target: "holes", output: "cad_files", icon: GearSix },
  { key: "counterbore", tab: "holes", title: "Konik havşa (countersink)/Silindirik havşa (counterbore)", detail: "Havşa açısı, silindirik havşa çapı, vida standardı, montaj açıklığı ve kesit işaretleri", target: "holes", output: "drawing_package", icon: Aperture },
  { key: "hole-pattern", tab: "holes", title: "Delik dizisi", detail: "Doğrusal ve dairesel diziler, delik aralığı, datum konumlama ve delik tablosu", target: "holes", output: "drawing_package", icon: Graph },
  { key: "interface-cutout", tab: "holes", title: "Arayüz kanalı", detail: "USB, Ağ girişi, düğme, havalandırma, kablo çıkışı ve fillet için gerçek kesim", target: "holes", output: "cad_files", icon: Ruler },
  { key: "drawing", tab: "drawing", title: "GB/T Çizim", detail: "Üç görünüş, kesit, ölçü zincirleri, GD&T, teknik koşullar ve antet", target: "drawing", output: "drawing_package", icon: FilePlus },
  { key: "tolerance", tab: "drawing", title: "Tolerans gösterimi", detail: "Ölçü toleransları, GD&T, yüzey pürüzlülüğü, datum sembolleri ve teknik koşullar", target: "drawing", output: "drawing_package", icon: Ruler },
  { key: "bom", tab: "drawing", title: "Montaj detayları", detail: "Montaj çizimi, patlatılmış görünüş, BOM, balloons ve satın alma/işleme listesi", target: "assembly", output: "drawing_package", icon: Layout },
  { key: "drawing-convert", tab: "drawing", title: "Çizim dönüştürme", detail: "DWG, DXF, PDF, PNG Çıktı önizlemesi ve GB/T çizim çerçevesi kontrolü", target: "drawing", output: "drawing_package", icon: Export },
];

const codexOutputs: Record<CodexConfig["expectedOutput"], string> = {
  auto: "AI çıktıyı seçsin",
  cad_files: "SLDPRT / STEP / STL",
  drawing_package: "DWG / DXF / PDF Çizim paketi",
  research_report: "Araştırma raporu / Yürütme önerileri",
};

function resolvedExpectedOutput(config: CodexConfig) {
  if (config.expectedOutput === "cad_files" && config.target === "assembly") return "SLDASM / STEP / STL";
  return codexOutputs[config.expectedOutput];
}

const processLabels: Record<CodexConfig["process"], string> = {
  auto: "AI üretim yöntemini seçsin",
  FDM: "FDM 3D Baskı",
  SLA: "SLA Fotopolimer baskı",
  CNC: "CNC İşleme",
  sheet_metal: "Sac (sheet metal)",
};

const materialLabels: Record<CodexConfig["material"], string> = {
  auto: "AI malzemeyi seçsin",
  PLA: "PLA",
  PETG: "PETG",
  ABS: "ABS",
  Al6061: "Al6061",
};

const deliveryFormats = ["STEP", "STL", "SLDPRT", "SLDASM", "DWG", "DXF", "PDF", "PNG", "DFM Rapor", "İnceleme raporu"];

function nextPaint() {
  return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

function jobKindDetail(kind: AutomationJobKind) {
  if (kind === "create_shell") return { title: "Yeni CAD Görev", detail: "Parça, montaj, muhafaza, delik/kanal ve temel kontrol görevleri oluşturun" };
  if (kind === "import_model") return { title: "Mevcut dosyayı içe aktar", detail: "CAD modeli, çizimi veya resim/eskizi referans olarak okuyun" };
  if (kind === "dfm_review") return { title: "DFM Üretim incelemesi", detail: "İşleme, sac, lazer kesim veya 3D baskı riskleri" };
  if (kind === "codex_task" || kind === "agent_task") return { title: "Agent Yürüt", detail: "Görsel ayarları seçili AI için etkileşimsiz yürütme görevine dönüştürün" };
  return { title: "Teslim paketi oluştur", detail: "STEP, STL, PDF, DWG dosyalarını ve teslim listesini düzenleyin" };
}

function isVideoPath(path: string) {
  return /\.(mp4|webm|mov|m4v|avi)$/i.test(path);
}

function displayNameFromPath(path: string) {
  return path.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "Duvar kâğıtlarım";
}

function revokeObjectUrl(url?: string) {
  if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
}

function wallpaperFromPath(path: string): WallpaperFile {
  return {
    url: convertFileSrc(path),
    name: displayNameFromPath(path),
    kind: isVideoPath(path) ? "video" : "image",
    sourcePath: path,
  };
}

function preloadWallpaper(wallpaper: WallpaperFile) {
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("Duvar kâğıdı yükleme zaman aşımı")), 12_000);
    if (wallpaper.kind === "video") {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadeddata = () => {
        window.clearTimeout(timeout);
        resolve();
      };
      video.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("Video biçimi yüklenemiyor"));
      };
      video.src = wallpaper.url;
      video.load();
      return;
    }
    const image = new Image();
    image.onload = () => {
      window.clearTimeout(timeout);
      resolve();
    };
    image.onerror = () => {
      window.clearTimeout(timeout);
      reject(new Error("Resim biçimi yüklenemiyor"));
    };
    image.src = wallpaper.url;
  });
}

function clampNumber(value: unknown, fallback: number, min: number, max: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function loadSettings(payload?: unknown): AppSettings | null {
  try {
    const raw = payload === undefined ? localStorage.getItem(SETTINGS_KEY) : null;
    if (payload === undefined && !raw) return null;
    const parsed = (payload === undefined ? JSON.parse(raw as string) : payload) as Partial<AppSettings>;
    const migratedWallpaper =
      parsed.defaultWallpaperVersion === 1
        ? parsed.activeWallpaper ?? "blossom"
        : parsed.customWallpaperPath
          ? parsed.activeWallpaper ?? "custom"
          : "blossom";
    const migratedName = typeof parsed.projectName === "string" && parsed.projectName.trim() ? parsed.projectName.trim().slice(0, 48) : "Adsız proje";
    const migratedProject: ProjectRecord = {
      ...DEFAULT_PROJECT,
      name: migratedName,
      sourcePath: parsed.recentProjectPath,
    };
    const projects = Array.isArray(parsed.projects)
      ? parsed.projects
          .filter((item): item is ProjectRecord => Boolean(item && typeof item.id === "string" && typeof item.name === "string" && item.name.trim()))
          .map((item) => ({
            id: item.id,
            name: item.name.trim().slice(0, 48),
            sourcePath: typeof item.sourcePath === "string" ? item.sourcePath : undefined,
            createdAt: typeof item.createdAt === "string" ? item.createdAt : "",
            updatedAt: typeof item.updatedAt === "string" ? item.updatedAt : "",
            archivedAt: typeof item.archivedAt === "string" ? item.archivedAt : undefined,
          }))
      : [];
    const normalizedProjects = projects.length ? projects : [migratedProject];
    const activeProjectId = normalizedProjects.some((item) => item.id === parsed.activeProjectId)
      ? parsed.activeProjectId
      : normalizedProjects[0].id;
    const activeProject = normalizedProjects.find((item) => item.id === activeProjectId) ?? normalizedProjects[0];
    return {
      activeWallpaper: parsed.customWallpaperPath ? migratedWallpaper : migratedWallpaper === "custom" ? "blossom" : migratedWallpaper,
      customWallpaperPath: parsed.customWallpaperPath,
      wallpaperBrightness: clampNumber(parsed.wallpaperBrightness, 94, 72, 112),
      wallpaperBlur: clampNumber(parsed.wallpaperBlur, 3, 0, 14),
      wallpaperVignette: clampNumber(parsed.wallpaperVignette, 18, 0, 42),
      workspaceOpacity: parsed.panelOpacityVersion === 1 ? clampNumber(parsed.workspaceOpacity, 36, 18, 92) : 36,
      wallpaperMotionMode: parsed.wallpaperMotionMode ?? "cinematic",
      wallpaperMotionStrength: clampNumber(parsed.wallpaperMotionStrength, 55, 0, 100),
      defaultWallpaperVersion: 1,
      panelOpacityVersion: 1,
      recentWallpapers: Array.isArray(parsed.recentWallpapers) ? parsed.recentWallpapers.slice(0, 6) : [],
      projects: normalizedProjects,
      activeProjectId,
      projectName: activeProject.name,
      recentProjectPath: activeProject.sourcePath,
      apiConfig: parsed.apiConfig
        ? {
            mode: parsed.apiConfig.mode ?? defaultApiConfig.mode,
            agentProvider: parsed.apiConfig.agentProvider ?? defaultApiConfig.agentProvider,
            providerName: parsed.apiConfig.providerName ?? defaultApiConfig.providerName,
            endpoint: parsed.apiConfig.endpoint ?? defaultApiConfig.endpoint,
            model: parsed.apiConfig.model ?? defaultApiConfig.model,
            keyStatus: parsed.apiConfig.keyStatus ?? defaultApiConfig.keyStatus,
            lastSyncAt: parsed.apiConfig.lastSyncAt,
            sourcePath: parsed.apiConfig.sourcePath,
          }
        : defaultApiConfig,
      knowledgeBase: parsed.knowledgeBase
        ? {
            cloudEnabled: parsed.knowledgeBase.cloudEnabled === true,
            localRoots: Array.isArray(parsed.knowledgeBase.localRoots) ? parsed.knowledgeBase.localRoots.filter((item): item is string => typeof item === "string").slice(0, 8) : [],
            endpoint: parsed.knowledgeBase.endpoint ?? "",
            namespace: parsed.knowledgeBase.namespace ?? defaultKnowledgeBase.namespace,
            tokenEnv: parsed.knowledgeBase.tokenEnv ?? defaultKnowledgeBase.tokenEnv,
            topK: clampNumber(parsed.knowledgeBase.topK, 6, 1, 12),
          }
        : defaultKnowledgeBase,
    };
  } catch {
    return null;
  }
}

function loadLocalQueue(): AutomationJob[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    const jobs = JSON.parse(raw);
    return Array.isArray(jobs) ? jobs.slice(0, 100) : [];
  } catch {
    return [];
  }
}

function loadAgentChat(payload?: unknown): AgentChatMessage[] {
  try {
    const raw = payload === undefined ? localStorage.getItem(CHAT_KEY) : null;
    if (payload === undefined && !raw) return [];
    const messages = payload === undefined ? JSON.parse(raw as string) : payload;
    return Array.isArray(messages)
      ? messages.filter((message) => !String(message?.content || "").startsWith("Merhaba, ben  CAD Studio   AI Yürütme asistanı")).slice(-30)
      : [];
  } catch {
    return [];
  }
}

function loadAgentConversations(payload?: unknown): AgentConversation[] {
  try {
    const raw = payload === undefined ? localStorage.getItem(CONVERSATIONS_KEY) : null;
    if (payload === undefined && !raw) return [];
    const conversations = payload === undefined ? JSON.parse(raw as string) : payload;
    return Array.isArray(conversations)
      ? conversations
          .filter((conversation) => conversation?.id && conversation?.projectId && conversation?.title)
          .map((conversation) => {
            const provider: AgentProviderId = ["codex", "claude", "gemini", "opencode"].includes(conversation.provider) ? conversation.provider : "codex";
            return {
              id: String(conversation.id),
              projectId: String(conversation.projectId),
              title: String(conversation.title).slice(0, 64),
              provider,
              model: typeof conversation.model === "string" ? conversation.model : agentProviderCatalog[provider].model,
              createdAt: typeof conversation.createdAt === "string" ? conversation.createdAt : "",
              updatedAt: typeof conversation.updatedAt === "string" ? conversation.updatedAt : "",
            } satisfies AgentConversation;
          })
          .slice(0, 100)
      : [];
  } catch {
    return [];
  }
}

function createChatMessage(
  role: AgentChatMessage["role"],
  content: string,
  jobId?: string,
  conversationId?: string,
  projectId?: string,
): AgentChatMessage {
  return {
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role,
    content,
    at: new Date().toISOString(),
    jobId,
    conversationId,
    projectId,
  };
}

function newConversationId() {
  return `conversation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function formatTimeLabel(value?: string) {
  if (!value) return "Az önce";
  if (value.startsWith("unix:")) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function eventTypeLabel(type?: string) {
  if (!type) return "Yürütme kaydı";
  if (type.includes("approval")) return "Onay";
  if (type.includes("codex.started")) return "AI Başlat";
  if (type.includes("codex.completed")) return "AI Bitir";
  if (type.includes("heartbeat")) return "Heartbeat";
  if (type.includes("claimed")) return "Görevi al";
  if (type.includes("failed")) return "Başarısız";
  if (type.includes("passed")) return "Tamamlandı";
  if (type.includes("review")) return "İncele";
  if (type.includes("artifact")) return "Teslim dosyaları";
  if (type.includes("step")) return "Adımlar";
  return type.replaceAll(".", " ");
}

function workerLogMessage(entry: WorkerLogEntry | string) {
  if (typeof entry === "string") return entry;
  return entry.message || entry.status || "worker Görev durumu güncellendi";
}

function workerLogTime(entry: WorkerLogEntry | string) {
  return typeof entry === "string" ? "" : entry.at;
}

function readableExecutionMessage(message?: string, job?: AutomationJob) {
  if (!message) return "";
  if (message.includes("WinError 2") || message.includes("Sistem belirtilen dosyayı bulamıyor")) {
    if (job?.executor === "codex" || job?.kind === "codex_task") {
      return "Seçilen Agent CLI bulunamadı. Ayarlardan yürütücüyü kontrol edin; ilgili CLI yüklü ve komut satırından çalıştırılabilir olmalıdır.";
    }
    return "Başlatılacak yerel program bulunamadı. Python, SolidWorks, AutoCAD veya ilgili yürütücünün yüklü olduğunu doğrulayın.";
  }
  return message;
}

function compactJobMessage(job: AutomationJob, events?: QueueEvent[]) {
  const message =
    (job.status === "approval_required" ? job.approvalReasons?.[0] : undefined) ||
    events?.[events.length - 1]?.message ||
    (job.reviewGate?.status ? `İnceleme sonucu: ${job.reviewGate.status}` : undefined) ||
    job.lastMessage ||
    job.result?.message ||
    job.result?.outputPath ||
    job.error ||
    job.detail;
  return readableExecutionMessage(message, job);
}

function buildChatPrompt(
  config: CodexConfig,
  api: ApiIntegrationConfig,
  userText: string,
  history: AgentChatMessage[],
  projectPath?: string,
  runtime?: RuntimeHealth | null,
) {
  const recentHistory = history
    .slice(-8)
    .map((message) => `${message.role === "user" ? "Kullanıcı" : message.role === "assistant" ? "AI" : "Sistem"}: ${message.content}`)
    .join("\n");
  return [
    buildCodexPrompt(config, projectPath, runtime),
    "",
    "CAD Studio Konuşma yürütme gereksinimleri:",
    "- Uygulama içindeki AI konuşmasına yanıt veriyorsunuz. Gizli akıl yürütmeyi paylaşmayın; kullanıcıya yönelik yürütme planını, önemli kararları, araç sonuçlarını, dosya yollarını ve doğrulama sonucunu gösterin.",
    "- Kullanıcı değişikliğe devam etmek, yeniden yapmak, görünümü ayarlamak veya ölçü eklemek isterse önceki konuşma ve yerel dosyalardan devam edin; sıfırdan başlamayın.",
    "- Kullanıcıya anlaşılır biçimde yanıt verin; ilgisiz geliştirici ayarlarını göstermeyin. Gerekli komutları, dosya yollarını ve hata nedenlerini açıkça yazın.",
    "- SolidWorks veya AutoCAD kullanırken yerel skill kurallarına ve GB/T mekanik çizim/üretim şartlarına uyun.",
    `- Mevcut AI Bağlantı yöntemi: ${apiModeLabel(api.mode)}; Provider: ${api.providerName}; Endpoint: ${api.endpoint}; Model: ${api.model}; Key: ${keyStatusLabel(api.keyStatus)}.`,
    "",
    "Son konuşmalar:",
    recentHistory || "Önceki konuşma yok.",
    "",
    "Kullanıcının mevcut talimatı:",
    userText,
  ].join("\n");
}

function apiModeLabel(mode: ApiIntegrationMode) {
  if (mode === "cc_switch") return "Eşitle CC Switch";
  return "Yerel Agent CLI";
}

function keyStatusLabel(status: ApiIntegrationConfig["keyStatus"]) {
  if (status === "synced") return "Eşitlendi";
  if (status === "configured") return "Yapılandırıldı";
  return "Yapılandırılmadı";
}

function reviewStatusLabel(status?: string) {
  if (status === "pass") return "Geçti";
  if (status === "fail") return "Başarısız";
  if (status === "warning") return "Not";
  return status || "İnceleme bekliyor";
}

function jobReviewStatusLabel(job?: AutomationJob) {
  if (job?.reviewDecision === "approved") return "İnsan incelemesi geçti";
  if (job?.reviewDecision === "rejected") return "İnsan incelemesi reddetti";
  if (job?.reviewGate?.status) return reviewStatusLabel(job.reviewGate.status);
  return "İncelenmedi";
}

function reviewOptionsFor(job?: AutomationJob): Array<readonly [string, string]> {
  const options: Array<readonly [string, string]> = [...manualReviewOptions];
  const descriptor = `${job?.kind ?? ""} ${job?.expectedOutput ?? ""} ${job?.target ?? ""} ${(job?.requiredArtifacts ?? []).join(" ")}`;
  if (/DWG|DXF|PDF|SLDDRW|DRAWING|çizim|teknik resim/i.test(descriptor) || job?.drawingEvidence) {
    options.push(["drawing", "Çerçeve, antet, görünüşler, ölçü zincirleri, delik tabloları ve teknik koşullar kontrol edildi"]);
  }
  if (/BOM|bill of materials|malzeme|parça listesi|ayrıntı tablosu/i.test(descriptor) || job?.bomEvidence) {
    options.push(["bom", "BOM, konfigürasyon, malzeme, parça numarası ve adetlerin modelle uyumu kontrol edildi"]);
  }
  if (/DFM|manufacturing|CNC|sheet metal|laser|print|üretim|sac|lazer|baskı/i.test(descriptor) || job?.dfmEvidence) {
    options.push(["dfm", "Malzeme, işlem, ölçüler, toleranslar ve tedarikçi yetenekleri dikkate alınarak DFM insan incelemesi tamamlandı"]);
  }
  return options;
}

function realFeatureRows(job?: AutomationJob): Array<Record<string, unknown>> {
  const features = job?.result?.features;
  return Array.isArray(features) ? features.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function recordText(record: Record<string, unknown>, keys: string[], fallback = "") {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
  }
  return fallback;
}

function createJob(kind: AutomationJobKind, projectPath?: string, overrides: Partial<AutomationJob> = {}): AutomationJob {
  const now = new Date().toISOString();
  const copy = jobKindDetail(kind);
  return {
    schemaVersion: "2.0",
    id: `job-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    runId: `run-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    kind,
    title: copy.title,
    detail: projectPath ? `${copy.detail} · ${displayNameFromPath(projectPath)}` : copy.detail,
    status: "queued",
    progress: 0,
    createdAt: now,
    updatedAt: now,
    requestedBy: "local-user",
    createdByAppVersion: APP_VERSION,
    policy: {
      sandbox: "workspace-write",
      approval: "never",
      requireSkillRead: true,
      requireTests: true,
      requireCommit: true,
      requirePush: false,
      requireReviewerPass: true,
    },
    artifacts: [],
    projectPath,
    projectId: overrides.projectId || "project-default",
    conversationId: overrides.conversationId || `conversation-${Date.now()}`,
    inputs: [],
    stage: "intake",
    capabilitySnapshot: {},
    assumptions: [],
    requiredArtifacts: [],
    verificationEvidence: [],
    ...overrides,
  };
}

function capabilityIdsForConfig(config: CodexConfig) {
  const ids = new Set<string>(["requirements_planning", "geometry_and_delivery_review"]);
  if (config.target === "assembly") ids.add("assembly_and_mates");
  if (["general_part", "shell", "fixture", "holes", "reverse", "auto"].includes(config.target)) ids.add("part_and_features");
  if (["holes", "shell", "fixture", "auto"].includes(config.target)) ids.add("holes_and_finishing");
  if (config.target === "sheet_metal") ids.add("sheet_metal");
  if (config.target === "drawing" || config.expectedOutput === "drawing_package") ids.add("drawings_and_bom");
  if (config.cadApplication === "autocad") ids.add("autocad_basic_drafting");
  if (config.process !== "auto") ids.add("dfm_checks");
  if (config.expectedOutput !== "research_report") ids.add("export_delivery");
  return Array.from(ids);
}

function capabilitySnapshot(runtime: RuntimeHealth, capabilityIds: string[]) {
  const entries = runtime.capabilityManifest?.capabilities ?? [];
  return {
    manifestSchema: runtime.capabilityManifest?.schema_version ?? "unknown",
    verifiedVersions: runtime.capabilityManifest?.verified_versions ?? {},
    capabilities: capabilityIds.map((id) => entries.find((item) => item.id === id) ?? { id, level: "not_implemented" }),
  };
}

function buildCodexPrompt(config: CodexConfig, projectPath?: string, runtime?: RuntimeHealth | null) {
  const strictRules = [
    "Kullanıcının açıkça belirtmediği modelleme türü, işlem, malzeme, çıktı biçimi, ölçü ayrıntıları ve kontrol öğeleri için  AI Mühendislik hedefine göre en uygun yaklaşımı seçip sonuçta gerekçeyi açıklayın.",
    config.realCutouts ? "Tüm delikler, kanallar, dişler, arayüzler ve hafifletme yapıları gerçek geometrik özellikler olmalıdır; yalnızca çizgi veya görünüm işareti yeterli değildir." : "Delik veya kanal varsa malzemenin gerçekten kesilip kesilmediğini açıkça belirtin.",
    config.strictGbDrawing ? "CAD Çizimleri GB/T mekanik çizim kurallarına göre inceleyin; boyut zincirleri, delik tabloları, teknik şartlar, çizim çerçevesi ve antet eksiksiz olmalıdır." : "Çizim çıktıları mevcut standart kapsamını belirtmelidir.",
    "Sonuçları kullanıcının belirttiği yerel çıktı klasörüne kaydedin; GitHub veya dış hizmetlerde yayınlamayın.",
  ];

  return [
    "Kullanıcının seçtiği yerel Agent sağlayıcısı olarak CAD Studio arayüzünde oluşturulan görevi yürütün.",
    "",
    `Görev hedefi: ${config.objective}`,
    `Hedef CAD Uygulama: ${cadApplicationLabels[config.cadApplication]}`,
    `Uygulama yönlendirme politikası: ${cadApplicationRoutes[config.cadApplication]}`,
    `Görev türü: ${codexTargets[config.target]}`,
    `Beklenen çıktı: ${resolvedExpectedOutput(config)}`,
    `Proje/Model yolu: ${projectPath || "Belirtilmedi"}`,
    `Üretim yöntemi: ${processLabels[config.process]}`,
    `Malzeme: ${materialLabels[config.material]}`,
    `Birim: ${config.unit}`,
    `Referans dış ölçüler: ${config.length > 0 && config.width > 0 && config.height > 0 ? `${config.length} x ${config.width} x ${config.height} ${config.unit}` : "Belirtilmedi; montaj arayüzü veya üretim öncesinde kullanıcıdan doğrulanmalıdır"}`,
    `Referans duvar kalınlığı/Sac kalınlığı: ${config.wallThickness > 0 ? `${config.wallThickness} ${config.unit}` : "Belirtilmedi; AI öneri sunmalıdır. Üretimden önce doğrulama zorunludur."}`,
    `Çıktı klasörü: ${config.outputDir}`,
    `Skill Yol: ${runtime?.solidworksSkillPath || "Masaüstü uygulaması başlatıldığında otomatik algılanır"}`,
    `AutoCAD Alt skill yolu: ${runtime?.autocadSkillPath || "Masaüstü uygulaması başlatıldığında otomatik algılanır"}`,
    "",
    "Zorunlu kurallar:",
    ...strictRules.map((rule) => `- ${rule}`),
    "",
    "Otomatik karar kuralları:",
    "- Otomatik seçilen alanlarda kullanıcı hedeflerini, girdileri, üretim yöntemini, maliyeti, dayanımı, işlenebilirliği ve teslim gereksinimlerini değerlendirin.",
    "- Otomatik seçimden sonra  summary  veya  verification  içinde seçimin nedenini açıklayın.",
    "- Güvenilir karar için bilgi yetersizse yaygın muhafazakâr bir yaklaşım kullanın ve kalan riski açıkça belirtin.",
    "- Montaj arayüzleri, kritik ölçüler, toleranslar, yükler ve güvenlikle ilgili malzemeler tahmin edilmemelidir; eksik bilgiler sorulmalı veya tasarımın üretime uygun olmayan bir konsept olduğu açıkça belirtilmelidir.",
    "",
    "Yürütme yöntemi:",
    "- CAD Studio arayüz ayarlarını yürütülebilir yerel CAD otomasyon görevlerine dönüştürün.",
    "- 3B katı, montaj, delik, sac, STEP/STL/SLDPRT Export için öncelik:  SolidWorks.",
    "- 2B DWG/DXF/PDF, Standart çizim, ölçü zinciri, delik tablosu, çerçeve ve antet için öncelik:  AutoCAD.",
    "- Uygulama seçimi otomatikse görevin SolidWorks, AutoCAD veya ikisini birlikte gerektirip gerektirmediğini belirleyip açıklayın.",
    "- Öncelikle kullanın:  solidworks-automation skill  ve  SolidWorks/AutoCAD  subskill.",
    "- Önce mevcut dosya ve standartları kontrol edin, sonra küçük adımlarla uygulayın.",
    "- Sonuçta çıktı dosyalarını, doğrulama sonuçlarını ve yerel kayıt konumunu Türkçe olarak, İngilizce teknik terimleri koruyarak açıklayın.",
  ].join("\n");
}

function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("project");
  const [activeWallpaper, setActiveWallpaper] = useState<WallpaperId>("blossom");
  const [customWallpaper, setCustomWallpaper] = useState<WallpaperFile | null>(null);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [wallpaperBrightness, setWallpaperBrightness] = useState(94);
  const [wallpaperBlur, setWallpaperBlur] = useState(3);
  const [wallpaperVignette, setWallpaperVignette] = useState(18);
  const [workspaceOpacity, setWorkspaceOpacity] = useState(36);
  const [wallpaperMotionMode, setWallpaperMotionMode] = useState<WallpaperMotionMode>("cinematic");
  const [wallpaperMotionStrength, setWallpaperMotionStrength] = useState(55);
  const [wallpaperShot, setWallpaperShot] = useState(0);
  const [recentWallpapers, setRecentWallpapers] = useState<RecentWallpaper[]>([]);
  const [projects, setProjects] = useState<ProjectRecord[]>([DEFAULT_PROJECT]);
  const [activeProjectId, setActiveProjectId] = useState(LEGACY_PROJECT_ID);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [deleteCandidateProjectId, setDeleteCandidateProjectId] = useState<string | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("Adsız proje");
  const [projectNameDraft, setProjectNameDraft] = useState("Adsız proje");
  const [editingProjectName, setEditingProjectName] = useState(false);
  const [recentProjectPath, setRecentProjectPath] = useState<string | undefined>();
  const [apiConfig, setApiConfig] = useState<ApiIntegrationConfig>(defaultApiConfig);
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBaseConfig>(defaultKnowledgeBase);
  const [ccSwitchSync, setCcSwitchSync] = useState<CcSwitchSync | null>(null);
  const [apiSyncMessage, setApiSyncMessage] = useState("CC Switch ile eşitleyebilir veya yerel Agent CLI ayarlarını kullanabilirsiniz.");
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [storeMigration, setStoreMigration] = useState<AppStoreMigrationStatus | null>(null);
  const [persistenceWarning, setPersistenceWarning] = useState<string | null>(null);
  const [queueLoaded, setQueueLoaded] = useState(false);
  const [queueLoadError, setQueueLoadError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [jobEvents, setJobEvents] = useState<Record<string, QueueEvent[]>>({});
  const [jobLogTails, setJobLogTails] = useState<Record<string, QueueLogTail>>({});
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [activeAgentJobId, setActiveAgentJobId] = useState<string | null>(null);
  const [agentMessages, setAgentMessages] = useState<AgentChatMessage[]>([]);
  const [agentConversations, setAgentConversations] = useState<AgentConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [chatLoaded, setChatLoaded] = useState(false);
  const [agentInput, setAgentInput] = useState("");
  const [manualReviewDrafts, setManualReviewDrafts] = useState<Record<string, ManualReviewDraft>>({});
  const [workerStatus, setWorkerStatus] = useState<WorkerStatus>({ running: false, message: "Masaüstü sürümü başlatabilir" });
  const [workerAction, setWorkerAction] = useState<"start" | "stop" | "restart" | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [submissionKind, setSubmissionKind] = useState<SubmissionKind>(null);
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string | null>(null);
  const [deleteCandidateJobId, setDeleteCandidateJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [selectedPreviewArtifactPath, setSelectedPreviewArtifactPath] = useState<string | undefined>();
  const [activeHelpTopic, setActiveHelpTopic] = useState<HelpTopicId>("start");
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [runtimeMessage, setRuntimeMessage] = useState("Agent, skill ve CAD ortamı algılanıyor...");
  const [windowHint, setWindowHint] = useState("Pencere kontrolü hazır");
  const [codexConfig, setCodexConfig] = useState<CodexConfig>({
    objective: "Kullanıcı girdisine göre CAD görev türünü, üretim yöntemini, malzemeyi ve teslim biçimini seçin. Üretilebilir sonuç oluşturup seçimlerinizi açıklayın.",
    cadApplication: "auto",
    target: "auto",
    expectedOutput: "auto",
    process: "auto",
    material: "auto",
    unit: "mm",
    length: 0,
    width: 0,
    height: 0,
    wallThickness: 0,
    outputDir: "Documents/CADAutomationWorkbench",
    strictGbDrawing: true,
    realCutouts: true,
    localCadAutomation: true,
  });
  const wallpaperInputRef = useRef<HTMLInputElement>(null);
  const bridgeRef = useRef<HTMLElement>(null);
  const completedChatJobIdsRef = useRef<Set<string>>(new Set());
  const reducedMotion = useReducedMotion();

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? projects[0] ?? DEFAULT_PROJECT,
    [activeProjectId, projects],
  );
  const activeProjectJobs = useMemo(
    () => jobs.filter((job) => jobProjectId(job) === activeProject.id),
    [activeProject.id, jobs],
  );
  const projectConversations = useMemo(
    () => agentConversations
      .filter((conversation) => conversation.projectId === activeProject.id)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    [activeProject.id, agentConversations],
  );
  const activeConversation = useMemo(
    () => projectConversations.find((conversation) => conversation.id === activeConversationId) ?? projectConversations[0],
    [activeConversationId, projectConversations],
  );
  const activeConversationMessages = useMemo(
    () => activeConversation
      ? agentMessages.filter((message) => message.conversationId === activeConversation.id)
      : [],
    [activeConversation, agentMessages],
  );
  const queueSummary = useMemo(() => {
    const approvalRequired = activeProjectJobs.filter((job) => job.status === "approval_required").length;
    const reviewRequired = activeProjectJobs.filter((job) => job.status === "review_required").length;
    const running = activeProjectJobs.filter((job) => job.status === "running").length;
    const queued = activeProjectJobs.filter((job) => job.status === "queued").length;
    if (approvalRequired > 0) return `${approvalRequired}  onay bekliyor`;
    if (reviewRequired > 0) return `${reviewRequired}  inceleme bekliyor`;
    if (running > 0) return `${running}  çalışıyor`;
    if (queued > 0) return `${queued}  sırada`;
    return activeProjectJobs.length > 0 ? "Kuyruk hazır" : "Görev yok";
  }, [activeProjectJobs]);

  const workerLabel = useMemo(() => {
    const health = workerStatus.health?.status;
    if (workerStatus.running) return health ? `Worker ${health}` : `Worker ${workerStatus.pid ?? ""}`;
    if (health) return `Önceki ${health}`;
    return workerStatus.message;
  }, [workerStatus]);

  const currentPage = pageCopy[activeTab];
  const workspaceTemplates = useMemo(() => {
    if (!["model", "holes", "drawing"].includes(activeTab)) return [];
    return taskTemplates.filter((item) => item.tab === activeTab);
  }, [activeTab]);

  const activeAgentJob = useMemo(
    () => activeProjectJobs.find((job) => job.id === activeAgentJobId)
      ?? activeProjectJobs.find((job) => job.conversationId && job.conversationId === activeConversation?.id)
      ?? activeProjectJobs.find((job) => job.uiConfig?.agentChat === true)
      ?? activeProjectJobs[0],
    [activeAgentJobId, activeConversation?.id, activeProjectJobs],
  );
  const resultJob = useMemo(
    () => activeAgentJob || activeProjectJobs.find((job) => collectJobArtifacts(job).length > 0 || job.reviewGate?.checks?.length || job.result?.message || job.error),
    [activeAgentJob, activeProjectJobs],
  );
  const resultArtifacts = useMemo(() => collectJobArtifacts(resultJob), [resultJob]);
  const selectedPreviewArtifact = useMemo(
    () => resultArtifacts.find((artifact) => artifact.path === selectedPreviewArtifactPath)
      ?? resultArtifacts.find((artifact) => /\.(stl|glb|gltf|obj|dxf|json|svg|png|jpe?g|webp|bmp|gif)$/i.test(artifact.path ?? "")),
    [resultArtifacts, selectedPreviewArtifactPath],
  );
  const resultChecks = resultJob?.reviewGate?.checks ?? resultJob?.result?.checks ?? [];
  const resultFeatures = realFeatureRows(resultJob);
  const codexPrompt = useMemo(() => buildCodexPrompt(codexConfig, recentProjectPath, runtimeHealth), [codexConfig, recentProjectPath, runtimeHealth]);
  const recentJobs = useMemo(() => activeProjectJobs.slice(0, 8), [activeProjectJobs]);
  const terminalJobs = useMemo(() => terminalProjectJobs(jobs, activeProject.id), [activeProject.id, jobs]);
  const projectTaskCounts = useMemo(() => jobs.reduce<Record<string, number>>((counts, job) => {
    const projectId = jobProjectId(job);
    counts[projectId] = (counts[projectId] ?? 0) + 1;
    return counts;
  }, {}), [jobs]);
  const selectedProvider = useMemo(
    () => runtimeHealth?.agentProviders?.find((provider) => provider.id === apiConfig.agentProvider),
    [apiConfig.agentProvider, runtimeHealth],
  );
  const selectedCcSwitchProviders = useMemo(
    () => ccSwitchProvidersForAgent(ccSwitchSync, apiConfig.agentProvider),
    [apiConfig.agentProvider, ccSwitchSync],
  );
  const providerModelOptions = useMemo(() => {
    const metadata = agentProviderCatalog[apiConfig.agentProvider];
    const configuredModels = selectedCcSwitchProviders.flatMap((provider) => [provider.model, ...(provider.models ?? [])]);
    const candidates = [metadata.model, ...metadata.models.map((model) => model.value), ...configuredModels, apiConfig.model]
      .filter((model): model is string => Boolean(model?.trim()));
    return Array.from(new Set(candidates)).map((value) => ({
      value,
      label: metadata.models.find((model) => model.value === value)?.label ?? value,
    }));
  }, [apiConfig.agentProvider, apiConfig.model, selectedCcSwitchProviders]);

  function updateCodexConfig(patch: Partial<CodexConfig>) {
    setCodexConfig((config) => ({ ...config, ...patch }));
  }

  function updateConversationRuntime(provider: AgentProviderId, model: string) {
    if (!activeConversation) return;
    setAgentConversations((items) => items.map((conversation) => conversation.id === activeConversation.id
      ? { ...conversation, provider, model, updatedAt: new Date().toISOString() }
      : conversation));
  }

  function selectAgentProvider(providerId: AgentProviderId) {
    const metadata = agentProviderCatalog[providerId];
    const health = runtimeHealth?.agentProviders?.find((item) => item.id === providerId);
    const ccSwitchRoute = activeCcSwitchProvider(ccSwitchSync, providerId);
    const model = ccSwitchRoute?.model || metadata.model;
    setApiConfig((config) => ({
      ...config,
      agentProvider: providerId,
      providerName: ccSwitchRoute?.name || metadata.name,
      endpoint: ccSwitchRoute?.endpoint || health?.entry || "Yerel CLI",
      model,
      keyStatus: ccSwitchRoute ? "synced" : health?.verified ? "configured" : "missing",
    }));
    updateConversationRuntime(providerId, model);
  }

  function selectAgentModel(model: string) {
    setApiConfig((config) => ({ ...config, model }));
    updateConversationRuntime(apiConfig.agentProvider, model);
  }

  function createAgentConversation(title?: string) {
    const now = new Date().toISOString();
    const conversation: AgentConversation = {
      id: newConversationId(),
      projectId: activeProject.id,
      title: title || `Yeni konuşma ${projectConversations.length + 1}`,
      provider: apiConfig.agentProvider,
      model: apiConfig.model,
      createdAt: now,
      updatedAt: now,
    };
    setAgentConversations((items) => [conversation, ...items]);
    setActiveConversationId(conversation.id);
    setActiveAgentJobId(null);
    setExpandedJobId(null);
    setAgentInput("");
    return conversation;
  }

  function selectAgentConversation(conversationId: string) {
    const conversation = agentConversations.find((item) => item.id === conversationId);
    if (!conversation) return;
    setActiveConversationId(conversation.id);
    setAgentConversations((items) => items.map((item) => item.id === conversation.id
      ? { ...item, updatedAt: new Date().toISOString() }
      : item));
    const latestJob = activeProjectJobs.find((job) => job.conversationId === conversation.id);
    setActiveAgentJobId(latestJob?.id ?? null);
    setExpandedJobId(latestJob?.id ?? null);
    setAgentInput("");
    const metadata = agentProviderCatalog[conversation.provider];
    const health = runtimeHealth?.agentProviders?.find((item) => item.id === conversation.provider);
    const ccSwitchRoute = activeCcSwitchProvider(ccSwitchSync, conversation.provider);
    setApiConfig((config) => ({
      ...config,
      agentProvider: conversation.provider,
      providerName: ccSwitchRoute?.name || metadata.name,
      endpoint: ccSwitchRoute?.endpoint || health?.entry || "Yerel CLI",
      model: conversation.model,
      keyStatus: ccSwitchRoute ? "synced" : health?.verified ? "configured" : "missing",
    }));
  }

  async function persistJob(job: AutomationJob) {
    if (isTauriRuntime()) {
      await invoke("save_queue_job", { job });
    }
  }

  function saveLocalQueue(nextJobs: AutomationJob[]) {
    if (!isTauriRuntime()) localStorage.setItem(QUEUE_KEY, JSON.stringify(nextJobs));
  }

  function upsertJob(nextJob: AutomationJob) {
    setJobs((items) => {
      const exists = items.some((item) => item.id === nextJob.id);
      const next = exists ? items.map((item) => (item.id === nextJob.id ? nextJob : item)) : [nextJob, ...items].slice(0, 100);
      saveLocalQueue(next);
      return next;
    });
  }

  function updateJob(id: string, updater: (job: AutomationJob) => AutomationJob) {
    setJobs((items) => {
      const next = items.map((item) => {
        if (item.id !== id) return item;
        return updater(item);
      });
      saveLocalQueue(next);
      return next;
    });
  }

  async function refreshWorkerStatus() {
    if (!isTauriRuntime()) {
      setWorkerStatus({ running: false, message: "Tarayıcı önizlemesi worker başlatmaz" });
      return;
    }
    try {
      const status = await invoke<WorkerStatus>("worker_status");
      setWorkerStatus(status);
    } catch (error) {
      setWorkerStatus({ running: false, message: `worker Durum okunamadı: ${String(error)}` });
    }
  }

  async function startLocalWorker() {
    if (!isTauriRuntime()) {
      setWorkerStatus({ running: false, message: "Worker'ı masaüstü sürümünden başlatın" });
      return;
    }
    setWorkerAction("start");
    try {
      const status = await invoke<WorkerStatus>("start_worker", {
        repoPath: runtimeHealth?.skillRoot ?? "",
        enableCodex: true,
        codexFullAccess: codexConfig.localCadAutomation,
      });
      setWorkerStatus(status);
    } catch (error) {
      setWorkerStatus({ running: false, message: `worker Başlatma başarısız: ${String(error)}` });
    } finally {
      setWorkerAction(null);
    }
  }

  async function stopLocalWorker() {
    if (!isTauriRuntime()) return;
    setWorkerAction("stop");
    try {
      const status = await invoke<WorkerStatus>("stop_worker");
      setWorkerStatus(status);
    } catch (error) {
      setWorkerStatus({ running: false, message: `worker Durdurma başarısız: ${String(error)}` });
    } finally {
      setWorkerAction(null);
    }
  }

  async function restartLocalWorker() {
    if (!isTauriRuntime()) {
      setWorkerStatus({ running: false, message: "Worker'ı masaüstü sürümünden yeniden başlatın" });
      return;
    }
    setWorkerAction("restart");
    try {
      const stopped = await invoke<WorkerStatus>("stop_worker");
      const status = await invoke<WorkerStatus>("start_worker", {
        repoPath: runtimeHealth?.skillRoot ?? "",
        enableCodex: true,
        codexFullAccess: codexConfig.localCadAutomation,
      });
      const recovered = stopped.recoveredJobs ?? 0;
      setWorkerStatus({
        ...status,
        message: recovered > 0 ? `worker Yeniden başlatıldı; kurtarılan görev:  ${recovered}  adet` : "worker Yeniden başlatıldı",
      });
    } catch (error) {
      setWorkerStatus({ running: false, message: `worker Yeniden başlatma başarısız: ${String(error)}` });
    } finally {
      setWorkerAction(null);
    }
  }

  async function syncCcSwitchConfig() {
    if (!isTauriRuntime()) {
      setApiSyncMessage("Tarayıcı önizlemesi yerel CC Switch ayarlarını okuyamaz; masaüstü sürümünden eşitleyin.");
      return;
    }
    setApiSyncMessage("CC Switch ayarları okunuyor...");
    try {
      const sync = await invoke<CcSwitchSync>("sync_cc_switch_config");
      const agentProvider = apiConfig.agentProvider;
      const provider = activeCcSwitchProvider(sync, agentProvider);
      const providerCount = ccSwitchProvidersForAgent(sync, agentProvider).length;
      const nextConfig: ApiIntegrationConfig = {
        mode: "cc_switch",
        agentProvider,
        providerName: provider?.name || provider?.id || agentProviderCatalog[agentProvider].name,
        endpoint: provider?.endpoint || " by  CC Switch Ayarlar belirler",
        model: provider?.model || " by  CC Switch Ayarlar belirler",
        keyStatus: provider ? "synced" : selectedProvider?.ready ? "configured" : "missing",
        lastSyncAt: sync.syncedAt,
        sourcePath: sync.databasePath || sync.configPath,
      };
      setCcSwitchSync(sync);
      setApiConfig(nextConfig);
      updateConversationRuntime(agentProvider, nextConfig.model);
      setApiSyncMessage(providerCount > 0
        ? `${providerCount} adet ${agentProviderCatalog[agentProvider].name} yönlendirmesi okundu; kimlik bilgileri CC Switch tarafından yönetilir.`
        : `CC Switch içinde ${agentProviderCatalog[agentProvider].name} yönlendirmesi yapılandırılmadı; mevcut CLI oturumu kullanılacak.`);
    } catch (error) {
      setApiSyncMessage(`Eşitleme başarısız: ${String(error)}`);
    }
  }

  function enqueueCodexTask() {
    if (submissionKind) return;
    void enqueueCodexTaskWithConfig(codexConfig);
  }

  async function ensureRuntimeHealth(): Promise<RuntimeHealth> {
    let health = runtimeHealth;
    if (!health?.skillRoot) {
      setRuntimeMessage("Agent, skill ve CAD ortamı algılanıyor...");
      health = await invoke<RuntimeHealth>("runtime_health");
    }
    setRuntimeHealth(health);
    const provider = health.agentProviders?.find((item) => item.id === apiConfig.agentProvider);
    if (!provider?.installed || !provider.ready) {
      throw new Error(provider?.auth?.message || provider?.version?.message || `${agentProviderCatalog[apiConfig.agentProvider].name} CLI Hazır değil`);
    }
    setRuntimeMessage(
      provider.verified
        ? `${provider.name} Gerçek görev doğrulandı; skills  ve yerel  CAD Yönlendirme hazır`
        : `${provider.name} CLI Yüklü; ilk gerçek görev tamamlandığında doğrulama durumu kaydedilecek`,
    );
    return health;
  }

  /** @brief Copy the controlled installation command provided by doctor and show the result in the current UI. */
  async function copyRuntimeCommand(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      setRuntimeMessage("Kurulum komutu kopyalandı. PowerShell içinde çalıştırdıktan sonra ortamı yeniden denetleyin.");
    } catch (error) {
      setRuntimeMessage(`Kopyalanamadı; komut metnini elle seçin: ${String(error)}`);
    }
  }

  /** @brief Open official URLs through allowlisted desktop commands; use a new tab in the browser preview. */
  async function openRuntimeDownload(url: string) {
    try {
      if (isTauriRuntime()) await invoke("open_external_download", { url });
      else window.open(url, "_blank", "noopener,noreferrer");
      setRuntimeMessage("Resmî indirme sayfası açıldı. Kurulumdan sonra ortamı yeniden denetleyin.");
    } catch (error) {
      setRuntimeMessage(`İndirme sayfası açılamıyor: ${String(error)}`);
    }
  }

  async function enqueueCodexTaskWithConfig(config: CodexConfig) {
    if (!isTauriRuntime()) {
      setAgentMessages((messages) => [...messages, createChatMessage("system", "Tarayıcı yalnızca arayüz önizlemesidir. Gerçek görevleri yürütmek için CAD Studio masaüstü sürümünü başlatın.")].slice(-40));
      return;
    }
    setSubmissionKind("task");
    setWindowHint("Görev hazırlanıyor...");
    await nextPaint();
    let activeRuntime: RuntimeHealth;
    try {
      activeRuntime = await ensureRuntimeHealth();
    } catch (error) {
      setAgentMessages((messages) => [...messages, createChatMessage("system", `Yerel çalışma ortamı hazır değil: ${String(error)}`)].slice(-40));
      setWindowHint("Görev oluşturulmadı · Yerel ortamı kontrol edin");
      setSubmissionKind(null);
      return;
    }
    const strictRules = [
      config.realCutouts ? "Delik, kanal, arayüz, havşa ve dişler gerçek geometrik kesim olmalıdır" : "Delik/kanal uygulama durumunu açıkça belirtin",
      config.strictGbDrawing ? "CAD çizimlerini GB/T mekanik çizim kurallarına göre inceleyin" : "Çizim standardının mevcut kapsamını açıklayın",
      `${cadApplicationLabels[config.cadApplication]}: ${cadApplicationRoutes[config.cadApplication]}`,
      config.localCadAutomation ? "Onaydan sonra yerel SolidWorks/AutoCAD masaüstü otomasyonu kullanılabilir." : "Yerel CAD uygulamasını doğrudan çağırmayın; yalnızca plan, betik veya açıklama üretin.",
      `Tüm teslim dosyaları yalnızca yerel çıktı klasörüne kaydedilir: ${config.outputDir}`,
    ];
    const capabilities = capabilityIdsForConfig(config);
    const providerMeta = agentProviderCatalog[apiConfig.agentProvider];
    const job = createJob("agent_task", recentProjectPath, {
      projectId: activeProjectId,
      executor: "agent",
      title: conciseTaskTitle(config.objective, `${codexTargets[config.target]}Görev`),
      detail: `${cadApplicationLabels[config.cadApplication]} · ${codexTargets[config.target]} · ${resolvedExpectedOutput(config)}`,
      objective: config.objective,
      targetSoftware: cadApplicationLabels[config.cadApplication],
      target: codexTargets[config.target],
      expectedOutput: resolvedExpectedOutput(config),
      strictRules,
      capabilities,
      capabilitySnapshot: capabilitySnapshot(activeRuntime, capabilities),
      prompt: buildCodexPrompt(config, recentProjectPath),
      cwd: activeRuntime.skillRoot,
      skillPath: activeRuntime.solidworksSkillPath,
      policy: {
        sandbox: config.localCadAutomation ? "danger-full-access" : "workspace-write",
        approval: "never",
        requireSkillRead: true,
        requireTests: true,
        requireCommit: false,
        requirePush: false,
        requireReviewerPass: true,
      },
      uiConfig: {
        agentRuntime: {
          provider: apiConfig.agentProvider,
          providerName: providerMeta.name,
          protocol: providerMeta.protocol,
          model: apiConfig.model.endsWith("ayarlarını kullan") ? "" : apiConfig.model,
        },
        cadRuntime: {
          application: config.cadApplication,
          applicationLabel: cadApplicationLabels[config.cadApplication],
          route: cadApplicationRoutes[config.cadApplication],
          localCadAutomation: config.localCadAutomation,
          solidworksSkillPath: activeRuntime.solidworksSkillPath,
          autocadSkillPath: activeRuntime.autocadSkillPath,
        },
        manufacturing: {
          process: config.process,
          processLabel: processLabels[config.process],
          material: config.material,
          materialLabel: materialLabels[config.material],
          unit: config.unit,
        },
        selection: {
          mode: "auto_best",
          autoTarget: config.target === "auto",
          autoCadApplication: config.cadApplication === "auto",
          autoOutput: config.expectedOutput === "auto",
          autoProcess: config.process === "auto",
          autoMaterial: config.material === "auto",
          instruction: "Belirtilmeyen alanlar için AI uygun mühendislik yaklaşımını, hedef CAD uygulamasını ve yürütme yolunu seçip gerekçesini açıklamalıdır.",
        },
        engineeringOrchestration: {
          mode: "plan_guided_dag",
          trigger: "Parça, delik/kanal, montaj, Motion,  çizim veya teslim içeren birleşik görevlerde otomatik etkinleşir",
          stages: ["Gereksinimler", "Parça", "Delik/kanal ve chamfer", "Montaj Mate", "Motion", "Mühendislik çizimi BOM", "Dışa aktar", "Birleşik inceleme"],
          retry: "Follow-up edits replan only affected stages and invalidate their downstream results",
          cadConcurrency: 1,
        },
        geometry: {
          length: config.length,
          width: config.width,
          height: config.height,
          wallThickness: config.wallThickness,
        },
        gates: {
          realCutouts: config.realCutouts,
          strictGbDrawing: config.strictGbDrawing,
          localCadAutomation: config.localCadAutomation,
        },
        outputDir: config.outputDir,
        knowledgeBase,
      },
    });
    try {
      setWindowHint("Yerel kuyruğa yazılıyor...");
      await persistJob(job);
      upsertJob(job);
      setActiveAgentJobId(job.id);
      setExpandedJobId(job.id);
      setWindowHint("Görev yerel kuyruğa alındı");
      if (!workerStatus.running) void startLocalWorker();
    } catch (error) {
      setAgentMessages((messages) => [
        ...messages,
        createChatMessage("system", `Görev yazılamadı ve yürütme kuyruğuna alınmadı: ${String(error)}`),
      ].slice(-40));
      setWindowHint("Görev yazılamadı");
    } finally {
      setSubmissionKind(null);
    }
  }

  async function submitAgentMessage() {
    const text = agentInput.trim();
    if (!text || submissionKind) return;

    const conversation = activeConversation ?? createAgentConversation(conciseTaskTitle(text, "Yeni konuşma"));
    const userMessage = createChatMessage("user", text, undefined, conversation.id, activeProject.id);
    setAgentConversations((items) => items.map((item) => item.id === conversation.id
      ? {
          ...item,
          title: item.title.startsWith("Yeni konuşma") ? conciseTaskTitle(text, "Yeni konuşma") : item.title,
          provider: apiConfig.agentProvider,
          model: apiConfig.model,
          updatedAt: new Date().toISOString(),
        }
      : item));
    if (!isTauriRuntime()) {
      setAgentMessages((messages) => [...messages, userMessage, createChatMessage("system", "Tarayıcı önizlemesi sahte görev oluşturmaz. Devam etmek için masaüstü sürümünü açın.", undefined, conversation.id, activeProject.id)].slice(-200));
      setAgentInput("");
      return;
    }
    setSubmissionKind("chat");
    setWindowHint("Konuşma görevi hazırlanıyor...");
    await nextPaint();
    let activeRuntime: RuntimeHealth;
    try {
      activeRuntime = await ensureRuntimeHealth();
    } catch (error) {
      setAgentMessages((messages) => [...messages, userMessage, createChatMessage("system", `Yerel ortam hazır değil: ${String(error)}`, undefined, conversation.id, activeProject.id)].slice(-200));
      setAgentInput("");
      setWindowHint("Konuşma görevi oluşturulmadı · Yerel ortamı kontrol edin");
      setSubmissionKind(null);
      return;
    }
    const prompt = buildChatPrompt(codexConfig, apiConfig, text, [...activeConversationMessages, userMessage], recentProjectPath, activeRuntime);
    const providerMeta = agentProviderCatalog[apiConfig.agentProvider];
    const job = createJob("agent_task", recentProjectPath, {
      projectId: activeProjectId,
      conversationId: conversation.id,
      executor: "agent",
      title: conciseTaskTitle(text, "AI CAD Konuşma görevi"),
      detail: `${cadApplicationLabels[codexConfig.cadApplication]} · ${codexTargets[codexConfig.target]} · Değişiklik istemeye devam edebilirsiniz`,
      objective: text,
      targetSoftware: cadApplicationLabels[codexConfig.cadApplication],
      target: codexTargets[codexConfig.target],
      expectedOutput: resolvedExpectedOutput(codexConfig),
      strictRules: [
        "Uygulama içindeki  AI  konuşma biçiminde yanıt verin; paylaşılabilir adım özeti, yürütme sonuçları ve dosya konumlarını gösterin.",
        codexConfig.realCutouts ? "Delik ve kanallar gerçek geometrik kesim (cut) olmalıdır." : "Delik/kanal varsa uygulama durumunu açıklayın.",
        codexConfig.strictGbDrawing ? "Çizimlerde GB/T mekanik çizim kurallarına uyun ve boyut zincirlerini inceleyin." : "Çizim görevlerinde standart kapsamını açıklayın.",
        "Tüm teslim dosyalarını yalnızca kullanıcının belirttiği yerel çıktı klasörüne kaydedin.",
      ],
      capabilities: capabilityIdsForConfig(codexConfig),
      capabilitySnapshot: capabilitySnapshot(activeRuntime, capabilityIdsForConfig(codexConfig)),
      prompt,
      cwd: activeRuntime.skillRoot,
      skillPath: activeRuntime.solidworksSkillPath,
      policy: {
        sandbox: codexConfig.localCadAutomation ? "danger-full-access" : "workspace-write",
        approval: "never",
        requireSkillRead: true,
        requireTests: true,
        requireCommit: false,
        requirePush: false,
        requireReviewerPass: true,
      },
      uiConfig: {
        agentChat: true,
        agentRuntime: {
          provider: apiConfig.agentProvider,
          providerName: providerMeta.name,
          protocol: providerMeta.protocol,
          model: apiConfig.model.endsWith("ayarlarını kullan") ? "" : apiConfig.model,
        },
        outputDir: codexConfig.outputDir,
        knowledgeBase,
        engineeringOrchestration: {
          mode: "plan_guided_dag",
          trigger: "Karmaşık mekanik işleri aşamalara ayırır; basit görevlerde en kısa yürütme yolu korunur",
          stages: ["Gereksinimler", "Parça", "Delik/kanal ve chamfer", "Montaj Mate", "Motion", "Mühendislik çizimi BOM", "Dışa aktar", "Birleşik inceleme"],
          retry: "Yerel düzenlemeler yalnızca etkilenen aşamayı ve devamını yeniden planlar",
          cadConcurrency: 1,
        },
        sourceJobId: activeAgentJob?.id,
        apiRuntime: apiConfig,
        cadRuntime: {
          application: codexConfig.cadApplication,
          applicationLabel: cadApplicationLabels[codexConfig.cadApplication],
          route: cadApplicationRoutes[codexConfig.cadApplication],
          localCadAutomation: codexConfig.localCadAutomation,
          solidworksSkillPath: activeRuntime.solidworksSkillPath,
          autocadSkillPath: activeRuntime.autocadSkillPath,
        },
      },
    });

    setAgentInput("");
    try {
      setWindowHint("Konuşma görevi yazılıyor...");
      await persistJob(job);
      setActiveAgentJobId(job.id);
      setExpandedJobId(job.id);
      setAgentMessages((messages) => [
        ...messages,
        userMessage,
        createChatMessage("assistant", `İsteğiniz yerel bir ${providerMeta.name} görevi olarak kuyruğa alındı. Aşağıda adımları, onayları, günlükleri ve sonuçları görebilirsiniz. Değişiklik için yeni gereksinim yazabilirsiniz.`, job.id, conversation.id, activeProject.id),
      ].slice(-200));
      upsertJob(job);
      setWindowHint("Konuşma görevi yerel kuyruğa alındı");
      if (!workerStatus.running) void startLocalWorker();
    } catch (error) {
      setAgentMessages((messages) => [
        ...messages,
        userMessage,
        createChatMessage("system", `Görev yazılamadı ve yürütme kuyruğuna alınmadı: ${String(error)}`, undefined, conversation.id, activeProject.id),
      ].slice(-200));
      setWindowHint("Konuşma görevi yazılamadı");
    } finally {
      setSubmissionKind(null);
    }
  }

  function selectTemplate(template: (typeof taskTemplates)[number]) {
    const nextConfig = {
      ...codexConfig,
      target: template.target,
      expectedOutput: template.output,
      objective: `${template.title}: ${template.detail}.İçe aktarılan kaynaklara veya mevcut ayarlara göre üretilebilir  CAD  sonuçları ve gerekli inceleme kayıtlarını üretin.`,
    } satisfies CodexConfig;
    setCodexConfig(nextConfig);
    setSelectedTemplateKey(template.key);
    setWindowHint(`«${template.title}» ayarları yüklendi · Kontrol edip yürütün`);
    requestAnimationFrame(() => bridgeRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" }));
  }

  function commitProjectName() {
    const nextName = normalizeProjectName(projectNameDraft);
    setProjectName(nextName);
    setProjectNameDraft(nextName);
    setProjects((items) => items.map((item) => item.id === activeProjectId
      ? { ...item, name: nextName, updatedAt: new Date().toISOString() }
      : item));
    setEditingProjectName(false);
    setWindowHint(`Proje adı: «${nextName}»`);
  }

  function selectProject(project: ProjectRecord) {
    const switchStartedAt = performance.now();
    const nextConversation = latestProjectConversation(agentConversations, project.id);
    setActiveProjectId(project.id);
    setActiveConversationId(nextConversation?.id ?? null);
    if (nextConversation) {
      const metadata = agentProviderCatalog[nextConversation.provider];
      const health = runtimeHealth?.agentProviders?.find((item) => item.id === nextConversation.provider);
      const ccSwitchRoute = activeCcSwitchProvider(ccSwitchSync, nextConversation.provider);
      setApiConfig((config) => ({
        ...config,
        agentProvider: nextConversation.provider,
        providerName: ccSwitchRoute?.name || metadata.name,
        endpoint: ccSwitchRoute?.endpoint || health?.entry || "Yerel CLI",
        model: nextConversation.model,
        keyStatus: ccSwitchRoute ? "synced" : health?.verified ? "configured" : "missing",
      }));
    }
    setProjectName(project.name);
    setProjectNameDraft(project.name);
    setRecentProjectPath(project.sourcePath);
    setProjectMenuOpen(false);
    setDeleteCandidateProjectId(null);
    setEditingProjectName(false);
    setDeleteCandidateJobId(null);
    setActiveAgentJobId(null);
    setExpandedJobId(null);
    setSelectedTemplateKey(null);
    setActiveTab("project");
    setWindowHint(`Geçiş yapıldı: «${project.name}»`);
    requestAnimationFrame(() => performance.measure("cad-studio.project-switch", { start: switchStartedAt }));
  }

  function createProject() {
    const now = new Date().toISOString();
    const project: ProjectRecord = {
      id: newProjectId(),
      name: `Yeni proje ${projects.length + 1}`,
      createdAt: now,
      updatedAt: now,
    };
    setProjects((items) => [project, ...items]);
    selectProject(project);
    setActiveConversationId(null);
    setEditingProjectName(true);
    setWindowHint("Yeni proje oluşturuldu; proje adını girin");
  }

  function duplicateProject(project: ProjectRecord) {
    const duplicate = duplicateProjectRecord(project, projects.length);
    setProjects((items) => [duplicate, ...items]);
    selectProject(duplicate);
    setActiveConversationId(null);
    setEditingProjectName(true);
    setWindowHint("Proje yapısı kopyalandı; görevler, konuşmalar ve  CAD Dosyalar kopyalanmadı");
  }

  function toggleProjectArchive(project: ProjectRecord) {
    if (project.id === activeProjectId) {
      setWindowHint("Bu projeyi arşivlemeden önce başka bir projeye geçin");
      return;
    }
    const archivedAt = project.archivedAt ? undefined : new Date().toISOString();
    setProjects((items) => items.map((item) => item.id === project.id
      ? { ...item, archivedAt, updatedAt: new Date().toISOString() }
      : item));
    setDeleteCandidateProjectId(null);
    setWindowHint(`«${project.name}» projesi ${archivedAt ? "arşivlendi" : "geri yüklendi"}`);
  }

  async function deleteProject(project: ProjectRecord) {
    if (!project.archivedAt && projects.filter((item) => !item.archivedAt).length <= 1) {
      setWindowHint("En az bir arşivlenmemiş proje kalmalıdır");
      return;
    }
    const projectJobs = jobs.filter((job) => jobProjectId(job) === project.id);
    if (hasActiveProjectJobs(jobs, project.id)) {
      setDeleteCandidateProjectId(null);
      setWindowHint("Projede sırada, çalışıyor veya onay bekliyor durumunda görevler var; önce bunları iptal edin");
      return;
    }
    if (deleteCandidateProjectId !== project.id) {
      setDeleteCandidateProjectId(project.id);
      setWindowHint(projectJobs.length
        ? `Silmek için tekrar seçin: «${project.name}» ve  ${projectJobs.length}  görev kaydı; CAD Teslim dosyaları korunacak`
        : `Boş projeyi silmeyi onaylamak için tekrar seçin: «${project.name}»`);
      return;
    }

    setDeletingProjectId(project.id);
    try {
      if (isTauriRuntime()) {
        for (const job of projectJobs) {
          await invoke("delete_queue_job", { id: job.id });
        }
      }
      const deletedJobIds = new Set(projectJobs.map((job) => job.id));
      const deletedConversationIds = new Set(agentConversations.filter((conversation) => conversation.projectId === project.id).map((conversation) => conversation.id));
      setJobs((items) => {
        const next = items.filter((job) => !deletedJobIds.has(job.id));
        saveLocalQueue(next);
        return next;
      });
      setJobEvents((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !deletedJobIds.has(id))));
      setJobLogTails((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !deletedJobIds.has(id))));
      setManualReviewDrafts((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !deletedJobIds.has(id))));
      setAgentConversations((items) => items.filter((conversation) => !deletedConversationIds.has(conversation.id)));
      setAgentMessages((items) => items.filter((message) => !message.conversationId || !deletedConversationIds.has(message.conversationId)));

      const remainingProjects = projects.filter((item) => item.id !== project.id);
      setProjects(remainingProjects);
      if (project.id === activeProjectId) {
        const fallback = remainingProjects.find((item) => !item.archivedAt) ?? remainingProjects[0];
        const fallbackConversation = latestProjectConversation(agentConversations, fallback.id);
        setActiveProjectId(fallback.id);
        setActiveConversationId(fallbackConversation?.id ?? null);
        setProjectName(fallback.name);
        setProjectNameDraft(fallback.name);
        setRecentProjectPath(fallback.sourcePath);
        if (fallbackConversation) {
          const metadata = agentProviderCatalog[fallbackConversation.provider];
          const health = runtimeHealth?.agentProviders?.find((item) => item.id === fallbackConversation.provider);
          const ccSwitchRoute = activeCcSwitchProvider(ccSwitchSync, fallbackConversation.provider);
          setApiConfig((config) => ({
            ...config,
            agentProvider: fallbackConversation.provider,
            providerName: ccSwitchRoute?.name || metadata.name,
            endpoint: ccSwitchRoute?.endpoint || health?.entry || "Yerel CLI",
            model: fallbackConversation.model,
            keyStatus: ccSwitchRoute ? "synced" : health?.verified ? "configured" : "missing",
          }));
        }
        setActiveAgentJobId(null);
        setExpandedJobId(null);
        setSelectedTemplateKey(null);
        setActiveTab("project");
      } else {
        if (activeAgentJobId && deletedJobIds.has(activeAgentJobId)) setActiveAgentJobId(null);
        if (expandedJobId && deletedJobIds.has(expandedJobId)) setExpandedJobId(null);
      }
      setProjectMenuOpen(false);
      setWindowHint(`«${project.name}» projesi silindi; CAD teslim dosyaları korundu`);
    } catch (error) {
      setWindowHint(`Proje silinemedi: ${String(error)}`);
    } finally {
      setDeletingProjectId(null);
      setDeleteCandidateProjectId(null);
    }
  }

  function removeJobsFromUi(ids: Set<string>) {
    setJobs((items) => {
      const next = items.filter((item) => !ids.has(item.id));
      saveLocalQueue(next);
      return next;
    });
    setJobEvents((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !ids.has(id))));
    setJobLogTails((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !ids.has(id))));
    setManualReviewDrafts((items) => Object.fromEntries(Object.entries(items).filter(([id]) => !ids.has(id))));
    if (activeAgentJobId && ids.has(activeAgentJobId)) setActiveAgentJobId(null);
    if (expandedJobId && ids.has(expandedJobId)) setExpandedJobId(null);
  }

  function removeJobFromUi(id: string) {
    removeJobsFromUi(new Set([id]));
  }

  async function deleteJob(job: AutomationJob) {
    if (deleteCandidateJobId !== job.id) {
      setDeleteCandidateJobId(job.id);
      setWindowHint("Onaylamak için silme simgesini tekrar seçin; CAD Teslim dosyaları silinmeyecek");
      return;
    }
    setDeletingJobId(job.id);
    try {
      if (isTauriRuntime()) {
        let current = job;
        if (["queued", "running", "approval_required"].includes(current.status)) {
          current = await invoke<AutomationJob>("cancel_queue_job", { id: job.id });
          upsertJob(current);
          if (current.status === "running") {
            setWindowHint("Durdurma istendi; İptal edildi durumundan sonra görev silinebilir");
            setDeleteCandidateJobId(null);
            return;
          }
        }
        await invoke("delete_queue_job", { id: job.id });
      }
      removeJobFromUi(job.id);
      setWindowHint("Görev kaydı silindi; CAD Teslim dosyaları değişmeden kalır");
    } catch (error) {
      updateJob(job.id, (item) => ({ ...item, lastMessage: `Silme başarısız: ${String(error)}` }));
      setWindowHint("Görev kaydı silinemedi");
    } finally {
      setDeletingJobId(null);
      setDeleteCandidateJobId(null);
    }
  }

  async function clearTerminalJobRecords() {
    const targets = terminalProjectJobs(jobs, activeProject.id);
    if (!targets.length) return;
    const deletedIds = new Set<string>();
    let failure: unknown;
    if (isTauriRuntime()) {
      for (const job of targets) {
        try {
          await invoke("delete_queue_job", { id: job.id });
          deletedIds.add(job.id);
        } catch (error) {
          failure = error;
          break;
        }
      }
    } else {
      targets.forEach((job) => deletedIds.add(job.id));
    }
    if (deletedIds.size) removeJobsFromUi(deletedIds);
    setDeleteCandidateJobId(null);
    if (failure) {
      setWindowHint(`Temizlendi ${deletedIds.size}  kayıt; diğer kayıtlar başarısız: ${String(failure)}`);
      throw failure;
    }
    setWindowHint(`Temizlendi ${targets.length}  terminal görev kaydı; CAD Teslim dosyaları değişmeden kalır`);
  }

  function enqueueDeliveryTask() {
    const nextConfig = {
      ...codexConfig,
      target: "package",
      expectedOutput: "auto",
      objective: "Mevcut projenin gerçek CAD çıktılarını düzenleyin: dosyaların varlığını ve biçimini doğrulayıp yerel teslim listesi oluşturun. Eksik dosyalarda açık hata verin; yer tutucu dosya oluşturmayın.",
    } satisfies CodexConfig;
    setCodexConfig(nextConfig);
    void enqueueCodexTaskWithConfig(nextConfig);
  }

  async function enqueueDfmReviewTask() {
    if (submissionKind) return;
    if (!isTauriRuntime()) {
      setWindowHint("DFM görevi oluşturmak için masaüstü sürümünü başlatın");
      return;
    }
    setSubmissionKind("task");
    setWindowHint("DFM incelemesi hazırlanıyor...");
    await nextPaint();
    try {
      const activeRuntime = await ensureRuntimeHealth();
      const capabilityIds = ["dfm_checks"];
      const job = createJob("dfm_review", recentProjectPath, {
        projectId: activeProjectId,
        title: "DFM Üretim riski incelemesi",
        detail: `${processLabels[codexConfig.process]} · ${materialLabels[codexConfig.material]} · Dış ölçüleri ayarla`,
        target: "DFM",
        expectedOutput: "DFM report",
        objective: "Mevcut üretim ayarlarına göre malzemeyi, duvar kalınlığını, dış ölçüleri, delik çapını, işlem parametrelerini ve baskı/kesim risklerini inceleyin.",
        capabilities: capabilityIds,
        capabilitySnapshot: capabilitySnapshot(activeRuntime, capabilityIds),
        requiredArtifacts: ["dfm_report"],
        requiredOutputs: ["dfm_report"],
        preferredBackend: "headless",
        fallbackPolicy: "allow_open_formats",
        cwd: activeRuntime.skillRoot,
        skillPath: activeRuntime.solidworksSkillPath,
        policy: {
          sandbox: "workspace-write",
          approval: "never",
          requireSkillRead: true,
          requireTests: true,
          requireCommit: false,
          requirePush: false,
          requireReviewerPass: true,
        },
        uiConfig: {
          outputDir: codexConfig.outputDir,
          process: codexConfig.process,
          geometry: {
            length: codexConfig.length,
            width: codexConfig.width,
            height: codexConfig.height,
            wallThickness: codexConfig.wallThickness,
          },
          manufacturing: {
            process: codexConfig.process,
            material: codexConfig.material,
            unit: codexConfig.unit,
          },
        },
      });
      await persistJob(job);
      upsertJob(job);
      setActiveAgentJobId(job.id);
      setExpandedJobId(job.id);
      setWindowHint("DFM Görev yerel kuyruğa alındı");
      if (!workerStatus.running) void startLocalWorker();
    } catch (error) {
      setWindowHint(`DFM Görev oluşturulmadı: ${String(error)}`);
    } finally {
      setSubmissionKind(null);
    }
  }

  async function cancelJob(id: string) {
    if (isTauriRuntime()) {
      try {
        const cancelled = await invoke<AutomationJob>("cancel_queue_job", { id });
        upsertJob(cancelled);
        return;
      } catch (error) {
        updateJob(id, (item) => ({ ...item, lastMessage: `İptal başarısız: ${String(error)}`, updatedAt: new Date().toISOString() }));
        return;
      }
    }
    updateJob(id, (item) => ({ ...item, status: "cancelled", progress: 0, updatedAt: new Date().toISOString() }));
  }

  async function retryJob(id: string) {
    if (retryingJobId) return;
    setRetryingJobId(id);
    try {
      if (isTauriRuntime()) {
        const retried = await invoke<AutomationJob>("retry_queue_job", { id });
        upsertJob(retried);
      } else {
        updateJob(id, (item) => ({
          ...item,
          runHistory: [...(item.runHistory ?? []), createRunSnapshot(item)].slice(-20),
          retryPolicy: {
            previousRunId: item.runId,
            retryFromStage: retryStageForJob(item),
            scope: "failed_stage_and_downstream",
            preservePreviousArtifacts: true,
            overwrite: false,
            requestedAt: new Date().toISOString(),
          },
          runId: `retry-${Date.now()}`,
          status: "queued",
          progress: 0,
          updatedAt: new Date().toISOString(),
          lastMessage: "Kullanıcı başarısız görevi yeniden başlattı; worker'ın görevi alması bekleniyor.",
          result: undefined,
          artifacts: [],
          artifactLedgerPath: undefined,
          reviewGatePath: undefined,
          reviewGate: undefined,
          reviewedAt: undefined,
          reviewedBy: undefined,
          reviewDecision: undefined,
          reviewNote: undefined,
          drawingEvidence: undefined,
          bomEvidence: undefined,
          reviewFindings: undefined,
          artifactRelations: undefined,
          blockedReasons: undefined,
          runnerId: undefined,
          workerPid: undefined,
          heartbeatAt: undefined,
          leaseUntil: undefined,
          workerLog: undefined,
          error: undefined,
        }));
      }
      setExpandedJobId(id);
      if (!workerStatus.running) void startLocalWorker();
    } catch (error) {
      updateJob(id, (item) => ({
        ...item,
        lastMessage: `Yeniden yürütme başarısız: ${String(error)}`,
        updatedAt: new Date().toISOString(),
      }));
    } finally {
      setRetryingJobId(null);
    }
  }

  async function approveJob(id: string) {
    if (isTauriRuntime()) {
      try {
        const approvedJob = await invoke<AutomationJob>("approve_queue_job", { id });
        upsertJob(approvedJob);
      } catch (error) {
        updateJob(id, (item) => ({
          ...item,
          lastMessage: `Onay başarısız: ${String(error)}`,
          updatedAt: new Date().toISOString(),
        }));
      }
      return;
    }

    updateJob(id, (item) => ({
      ...item,
      status: "queued",
      approvedAt: new Date().toISOString(),
      approvedBy: "local-user",
      approvedPolicyReasons: item.approvalReasons ?? [],
      lastMessage: "İnsan onayı verildi; görev yeniden kuyruğa alındı.",
      updatedAt: new Date().toISOString(),
    }));
  }

  async function reviewJob(id: string, approved: boolean) {
    const job = jobs.find((item) => item.id === id);
    const draft = manualReviewDrafts[id] ?? { note: "", checks: [] };
    const requiredChecks = reviewOptionsFor(job).map(([key]) => key);
    if (draft.note.trim().length < (approved ? 8 : 4)) {
      updateJob(id, (item) => ({
        ...item,
        lastMessage: approved ? "İncelemeyi onaylamak için en az 8 karakterlik somut bir inceleme açıklaması yazın." : "Reddetmeden önce somut sorunları yazın.",
      }));
      return;
    }
    if (approved && requiredChecks.some((key) => !draft.checks.includes(key))) {
      updateJob(id, (item) => ({ ...item, lastMessage: "Mevcut görevin tüm gerekli insan inceleme öğelerini tamamlayın." }));
      return;
    }
    if (isTauriRuntime()) {
      try {
        const reviewedJob = await invoke<AutomationJob>(
          approved ? "approve_review_job" : "reject_review_job",
          approved ? { id, reason: draft.note.trim(), checks: draft.checks } : { id, reason: draft.note.trim() },
        );
        upsertJob(reviewedJob);
        setManualReviewDrafts((items) => {
          const next = { ...items };
          delete next[id];
          return next;
        });
      } catch (error) {
        updateJob(id, (item) => ({
          ...item,
          lastMessage: `İnsan incelemesi başarısız: ${String(error)}`,
          updatedAt: new Date().toISOString(),
        }));
      }
      return;
    }

    updateJob(id, (item) => ({
      ...item,
      status: approved ? "passed" : "failed",
      reviewDecision: approved ? "approved" : "rejected",
      reviewedAt: new Date().toISOString(),
      reviewedBy: "local-user",
      reviewNote: draft.note.trim(),
      lastMessage: approved ? "İnsan incelemesi geçti; görev teslim edilebilir." : "İnsan incelemesi başarısız; görev reddedildi.",
      updatedAt: new Date().toISOString(),
    }));
  }

  function updateManualReviewDraft(id: string, patch: Partial<ManualReviewDraft>) {
    setManualReviewDrafts((items) => ({
      ...items,
      [id]: { ...(items[id] ?? { note: "", checks: [] }), ...patch },
    }));
  }

  function rememberWallpaper(path: string, name = displayNameFromPath(path), kind: "image" | "video" = isVideoPath(path) ? "video" : "image") {
    const nextWallpaper = {
      path,
      name,
      kind,
    } satisfies RecentWallpaper;

    setRecentWallpapers((items) => [nextWallpaper, ...items.filter((item) => item.path !== path)].slice(0, 6));
  }

  function useWallpaperFile(file?: File) {
    if (!file) return;
    const isImage = file.type.startsWith("image/");
    const isVideo = file.type.startsWith("video/");
    if (!isImage && !isVideo) return;

    setCustomWallpaper((previous) => {
      revokeObjectUrl(previous?.url);
      return {
        url: URL.createObjectURL(file),
        name: file.name.replace(/\.[^.]+$/, ""),
        kind: isVideo ? "video" : "image",
      };
    });
    setActiveWallpaper("custom");
    setAppearanceOpen(true);
  }

  async function applyWallpaperPath(path: string, options: { remember?: boolean; open?: boolean } = {}) {
    setWindowHint("Yerel duvar kâğıdı içe aktarılıyor...");
    try {
      const imported = isTauriRuntime()
        ? await invoke<ImportedWallpaper>("import_wallpaper", { sourcePath: path })
        : { path, name: displayNameFromPath(path), kind: isVideoPath(path) ? "video" as const : "image" as const };
      const wallpaper = { ...wallpaperFromPath(imported.path), name: imported.name, kind: imported.kind };
      await preloadWallpaper(wallpaper);
      setCustomWallpaper((previous) => {
        revokeObjectUrl(previous?.url);
        return wallpaper;
      });
      if (options.remember !== false) rememberWallpaper(imported.path, imported.name, imported.kind);
      setActiveWallpaper("custom");
      if (options.open !== false) setAppearanceOpen(true);
      setWindowHint(`«${imported.name}» duvar kâğıdı uygulandı`);
      return true;
    } catch (error) {
      setActiveWallpaper((current) => current === "custom" ? "blossom" : current);
      setWindowHint(`Duvar kâğıdı içe aktarılamadı: ${String(error)}`);
      return false;
    }
  }

  async function chooseWallpaper() {
    if (!isTauriRuntime()) {
      wallpaperInputRef.current?.click();
      return;
    }

    const selected = await openDialog({
      multiple: false,
      filters: [
        {
          name: "Wallpapers",
          extensions: ["png", "jpg", "jpeg", "webp", "gif", "bmp", "mp4", "webm", "mov", "m4v", "avi"],
        },
      ],
    });

    if (!selected || Array.isArray(selected)) return;

    await applyWallpaperPath(selected);
  }

  async function chooseProjectFile() {
    if (!isTauriRuntime()) {
      setAgentMessages((messages) => [...messages, createChatMessage("system", "Tarayıcı önizlemesi yerel CAD dosyalarına erişemez. STEP, STL, SLDPRT, SLDASM, DWG, DXF, PDF veya resimleri masaüstü sürümünden içe aktarın.")].slice(-40));
      return;
    }

    const selected = await openDialog({
      multiple: false,
      filters: [
        {
          name: "CAD / Drawing / Sketch",
          extensions: ["step", "stp", "sldprt", "sldasm", "stl", "iges", "igs", "dxf", "dwg", "pdf", "png", "jpg", "jpeg", "webp", "bmp"],
        },
      ],
    });

    if (!selected || Array.isArray(selected)) return;
    setRecentProjectPath(selected);
    const importedName = displayNameFromPath(selected);
    const nextName = projectName === "Adsız proje" || /^Yeni proje \d+$/.test(projectName) ? importedName : projectName;
    setProjectName(nextName);
    setProjectNameDraft(nextName);
    setProjects((items) => items.map((item) => item.id === activeProjectId
      ? { ...item, name: nextName, sourcePath: selected, updatedAt: new Date().toISOString() }
      : item));
    if (activeConversation) {
      setAgentMessages((messages) => [
        ...messages,
        createChatMessage(
          "system",
          `${displayNameFromPath(selected)} mevcut görev bağlamına eklendi. Yeni model, değişiklik, çizim veya kontrol isteğinizi konuşmada belirtin.`,
          undefined,
          activeConversation.id,
          activeProject.id,
        ),
      ].slice(-200));
    }
  }

  async function chooseOutputDir() {
    if (!isTauriRuntime()) return;

    const selected = await openDialog({
      multiple: false,
      directory: true,
    });

    if (!selected || Array.isArray(selected)) return;
    updateCodexConfig({ outputDir: selected });
  }

  async function chooseKnowledgeRoot() {
    if (!isTauriRuntime()) return;
    const selected = await openDialog({ multiple: false, directory: true });
    if (!selected || Array.isArray(selected)) return;
    setKnowledgeBase((config) => ({
      ...config,
      localRoots: [selected, ...config.localRoots.filter((item) => item !== selected)].slice(0, 8),
    }));
  }

  function importWallpaper(event: ChangeEvent<HTMLInputElement>) {
    useWallpaperFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function dropWallpaper(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    useWallpaperFile(event.dataTransfer.files?.[0]);
  }

  function controlWallpaperPointer(event: ReactPointerEvent<HTMLElement>) {
    if (reducedMotion || wallpaperMotionMode !== "follow") return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const strength = wallpaperMotionStrength / 100;
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * -18 * strength;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * -12 * strength;
    event.currentTarget.style.setProperty("--wallpaper-pointer-x", `${x}px`);
    event.currentTarget.style.setProperty("--wallpaper-pointer-y", `${y}px`);
  }

  function resetWallpaperPointer(event: ReactPointerEvent<HTMLElement>) {
    event.currentTarget.style.setProperty("--wallpaper-pointer-x", "0px");
    event.currentTarget.style.setProperty("--wallpaper-pointer-y", "0px");
  }

  async function controlWindow(action: "close" | "minimize" | "maximize") {
    const labels = { close: "Kapat", minimize: "Küçült", maximize: "Büyüt/Geri yükle" };
    if (!isTauriRuntime()) {
      setWindowHint("Pencere kontrolü tarayıcı önizlemesinde yoktur; masaüstünde kullanılabilir");
      return;
    }
    try {
      const appWindow = getCurrentWindow();
      setWindowHint(`İşleniyor${labels[action]}`);
      if (action === "close") {
        await invoke("close_app");
        return;
      }
      if (action === "minimize") await appWindow.minimize();
      if (action === "maximize") {
        if (await appWindow.isMaximized()) {
          await appWindow.unmaximize();
          setWindowHint("Pencere geri yüklendi");
          return;
        }
        await appWindow.maximize();
      }
      setWindowHint(`Pencere ${labels[action]}`);
    } catch (error) {
      console.error(error);
      setWindowHint("Pencere kontrolü başarısız; masaüstü uygulamasını yeniden başlatın");
    }
  }

  useEffect(() => {
    if (!isTauriRuntime()) {
      setRuntimeMessage("Tarayıcı önizleme modu: Agent, skill ve CAD ortamının gerçek denetimi yalnızca masaüstünde çalışır.");
      return;
    }
    let disposed = false;
    void invoke<RuntimeHealth>("runtime_health")
      .then((health) => {
        if (disposed) return;
        setRuntimeHealth(health);
        if (health.defaultOutputDir) {
          setCodexConfig((config) => ({
            ...config,
            outputDir: config.outputDir === "Documents/CADAutomationWorkbench" ? health.defaultOutputDir! : config.outputDir,
          }));
        }
        const installedProviders = health.agentProviders?.filter((provider) => provider.installed) ?? [];
        const verifiedProviders = installedProviders.filter((provider) => provider.verified);
        setApiConfig((config) => {
          const current = health.agentProviders?.find((provider) => provider.id === config.agentProvider);
          return { ...config, keyStatus: current?.verified ? "configured" : "missing" };
        });
        setRuntimeMessage(
          installedProviders.length
            ? `Yüklü ${installedProviders.map((provider) => provider.name).join(", ")}; Gerçek görev doğrulandı ${verifiedProviders.length ? verifiedProviders.map((provider) => provider.name).join(", ") : "Yok"}.SolidWorks ${health.solidworks?.ok ? "Kullanılabilir" : "Kontrol bekliyor"}, AutoCAD ${health.autocad?.ok ? "Kullanılabilir" : "Algılanmadı"}.`
            : "Agent sağlayıcısı algılanmadı. Ayarlardan CLI kurulum durumunu kontrol edin.",
        );
      })
      .catch((error) => {
        if (!disposed) setRuntimeMessage(`Ortam algılama başarısız: ${String(error)}`);
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      revokeObjectUrl(customWallpaper?.url);
    };
  }, [customWallpaper?.url]);

  useEffect(() => {
    if (!projectMenuOpen) return;
    const closeProjectMenu = (event: PointerEvent) => {
      if (!(event.target as Element | null)?.closest(".project-switcher")) {
        setProjectMenuOpen(false);
        setDeleteCandidateProjectId(null);
      }
    };
    const closeProjectMenuWithKeyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProjectMenuOpen(false);
        setDeleteCandidateProjectId(null);
      }
    };
    document.addEventListener("pointerdown", closeProjectMenu);
    document.addEventListener("keydown", closeProjectMenuWithKeyboard);
    return () => {
      document.removeEventListener("pointerdown", closeProjectMenu);
      document.removeEventListener("keydown", closeProjectMenuWithKeyboard);
    };
  }, [projectMenuOpen]);

  useEffect(() => {
    setWallpaperShot(0);
    if (reducedMotion || wallpaperMotionMode !== "cinematic") return;
    const timer = window.setInterval(() => setWallpaperShot((shot) => (shot + 1) % wallpaperShots.length), 14000);
    return () => window.clearInterval(timer);
  }, [activeWallpaper, reducedMotion, wallpaperMotionMode]);

  useEffect(() => {
    async function restoreSettings() {
      const persisted = await readPersistedState("settings", SETTINGS_KEY);
      if (persisted.degraded) setPersistenceWarning(persisted.value === null
        ? "SQLite  geçici olarak kullanılamıyor. Ayar yedeği bulunamadı; sonraki kayıtta yeniden denenecek."
        : "SQLite  geçici olarak kullanılamıyor. Ayarlar yerel yedekten kurtarıldı; sonraki kayıtta yeniden denenecek.");
      const settings = loadSettings(persisted.value ?? undefined);
      if (!settings) {
        setSettingsLoaded(true);
        return;
      }
      setActiveWallpaper(settings.activeWallpaper);
      setWallpaperBrightness(settings.wallpaperBrightness);
      setWallpaperBlur(settings.wallpaperBlur);
      setWallpaperVignette(settings.wallpaperVignette);
      setWorkspaceOpacity(settings.workspaceOpacity);
      setWallpaperMotionMode(settings.wallpaperMotionMode);
      setWallpaperMotionStrength(settings.wallpaperMotionStrength);
      setRecentWallpapers(settings.recentWallpapers);
      setProjects(settings.projects ?? [DEFAULT_PROJECT]);
      setActiveProjectId(settings.activeProjectId ?? LEGACY_PROJECT_ID);
      setProjectName(settings.projectName ?? "Adsız proje");
      setProjectNameDraft(settings.projectName ?? "Adsız proje");
      setRecentProjectPath(settings.recentProjectPath);
      setApiConfig(settings.apiConfig ?? defaultApiConfig);
      setKnowledgeBase(settings.knowledgeBase ?? defaultKnowledgeBase);
      if (settings.customWallpaperPath) {
        setActiveWallpaper("blossom");
        await applyWallpaperPath(settings.customWallpaperPath, { remember: false, open: false });
      }
      setSettingsLoaded(true);
    }
    void restoreSettings().catch((error) => {
      setPersistenceWarning(`Ayarlar kurtarılamadı: ${error instanceof Error ? error.message : String(error)}`);
      setSettingsLoaded(true);
    });
  }, []);

  useEffect(() => {
    async function restoreChat() {
      const [messagePayload, conversationPayload] = await Promise.all([
        readPersistedState("messages", CHAT_KEY),
        readPersistedState("conversations", CONVERSATIONS_KEY),
      ]);
      if (messagePayload.degraded || conversationPayload.degraded) {
        setPersistenceWarning(messagePayload.value === null && conversationPayload.value === null
          ? "SQLite  geçici olarak kullanılamıyor. Konuşma yedeği bulunamadı; sonraki kayıtta yeniden denenecek."
          : "SQLite  geçici olarak kullanılamıyor. Konuşma yerel yedekten kurtarıldı; sonraki kayıtta yeniden denenecek.");
      }
      const savedMessages = loadAgentChat(messagePayload.value ?? undefined);
      let savedConversations = loadAgentConversations(conversationPayload.value ?? undefined);
      const hasLegacyMessages = savedMessages.some((message) => !message.conversationId);
      if (hasLegacyMessages && !savedConversations.some((conversation) => conversation.id === LEGACY_CONVERSATION_ID)) {
        const legacyAt = savedMessages[0]?.at || new Date().toISOString();
        savedConversations = [{
          id: LEGACY_CONVERSATION_ID,
          projectId: LEGACY_PROJECT_ID,
          title: "Konuşma geçmişi",
          provider: "codex",
          model: defaultApiConfig.model,
          createdAt: legacyAt,
          updatedAt: savedMessages.at(-1)?.at || legacyAt,
        }, ...savedConversations];
      }
      setAgentMessages(savedMessages.map((message) => message.conversationId ? message : {
        ...message,
        projectId: LEGACY_PROJECT_ID,
        conversationId: LEGACY_CONVERSATION_ID,
      }));
      setAgentConversations(savedConversations);
      setChatLoaded(true);
    }
    void restoreChat().catch((error) => {
      setPersistenceWarning(`Konuşma kurtarılamadı: ${error instanceof Error ? error.message : String(error)}`);
      setChatLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (!chatLoaded) return;
    void writePersistedState("messages", CHAT_KEY, agentMessages.slice(-200))
      .then((result) => result.degraded && setPersistenceWarning("SQLite Yazma başarısız; konuşma yerel yedeğe güvenle kaydedildi."))
      .catch((error) => setPersistenceWarning(`Konuşma kaydedilemedi: ${error instanceof Error ? error.message : String(error)}`));
    void writePersistedState("conversations", CONVERSATIONS_KEY, agentConversations.slice(0, 100))
      .then((result) => result.degraded && setPersistenceWarning("SQLite  yazılamadı; konuşma dizini yerel yedeğe güvenle kaydedildi."))
      .catch((error) => setPersistenceWarning(`Konuşma dizini kaydedilemedi: ${error instanceof Error ? error.message : String(error)}`));
  }, [agentConversations, agentMessages, chatLoaded]);

  useEffect(() => {
    if (!settingsLoaded || !chatLoaded || !isTauriRuntime()) return;
    const timer = window.setTimeout(() => {
      void invoke<AppStoreMigrationStatus>("app_store_migration_status")
        .then(setStoreMigration)
        .catch(() => setStoreMigration(null));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [agentConversations, agentMessages, chatLoaded, projects, settingsLoaded]);

  useEffect(() => {
    if (!chatLoaded) return;
    const nextConversation = activeConversation?.projectId === activeProject.id ? activeConversation : projectConversations[0];
    if (!nextConversation) {
      if (activeConversationId) setActiveConversationId(null);
      return;
    }
    if (activeConversationId !== nextConversation.id) setActiveConversationId(nextConversation.id);
    if (apiConfig.agentProvider === nextConversation.provider && apiConfig.model === nextConversation.model) return;
    const metadata = agentProviderCatalog[nextConversation.provider];
    const health = runtimeHealth?.agentProviders?.find((item) => item.id === nextConversation.provider);
    const ccSwitchRoute = activeCcSwitchProvider(ccSwitchSync, nextConversation.provider);
    setApiConfig((config) => ({
      ...config,
      agentProvider: nextConversation.provider,
      providerName: ccSwitchRoute?.name || metadata.name,
      endpoint: ccSwitchRoute?.endpoint || health?.entry || "Yerel CLI",
      model: nextConversation.model,
      keyStatus: ccSwitchRoute ? "synced" : health?.verified ? "configured" : "missing",
    }));
  }, [activeConversation, activeConversationId, activeProject.id, apiConfig.agentProvider, apiConfig.model, ccSwitchSync, chatLoaded, projectConversations, runtimeHealth]);

  useEffect(() => {
    let disposed = false;

    async function loadQueue() {
      if (!isTauriRuntime()) {
        setJobs(loadLocalQueue());
        setQueueLoaded(true);
        return;
      }

      try {
        const savedJobs = await invoke<AutomationJob[]>("read_queue_jobs");
        if (disposed) return;
        setQueueLoadError(null);
        const nextJobs = savedJobs
          .filter((job) => typeof job.id === "string")
          .sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""))
          .slice(0, 100);
        startTransition(() => setJobs(nextJobs));
        const visibleProjectJobs = nextJobs.filter((job) => jobProjectId(job) === activeProjectId);
        const visibleJobIds = Array.from(new Set([...visibleProjectJobs.slice(0, 4).map((job) => job.id), activeAgentJobId, expandedJobId].filter(Boolean))) as string[];
        const eventPairs = await Promise.all(visibleJobIds.map(async (id) => [id, await invoke<QueueEvent[]>("read_queue_events", { id })] as const));
        const logPairs = await Promise.all(
          visibleJobIds.map(async (id) => {
            try {
              return [id, await invoke<QueueLogTail>("read_queue_log_tail", { id })] as const;
            } catch {
              return [id, {}] as const;
            }
          }),
        );
        if (!disposed) {
          startTransition(() => {
            setJobEvents(Object.fromEntries(eventPairs));
            setJobLogTails(Object.fromEntries(logPairs));
          });
        }
      } catch (error) {
        if (!disposed) setQueueLoadError(`Görev kuyruğu okuma hatası: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        if (!disposed) setQueueLoaded(true);
      }
    }

    void loadQueue();
    if (!isTauriRuntime()) return () => {
      disposed = true;
    };

    let debounceTimer: number | undefined;
    let unlisten: (() => void) | undefined;
    void listen("queue-changed", () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        void loadQueue();
        void refreshWorkerStatus();
      }, 80);
    }).then((dispose) => {
      if (disposed) dispose();
      else unlisten = dispose;
    }).catch((error) => {
      if (!disposed) setQueueLoadError(`Görev kuyruğu dinleme hatası: ${error instanceof Error ? error.message : String(error)}`);
    });
    return () => {
      disposed = true;
      window.clearTimeout(debounceTimer);
      unlisten?.();
    };
  }, [activeAgentJobId, activeProjectId, expandedJobId]);

  useEffect(() => {
    void refreshWorkerStatus();
  }, []);

  useEffect(() => {
    const updates: AgentChatMessage[] = [];
    for (const job of jobs) {
      if (job.uiConfig?.agentChat !== true) continue;
      if (!job.conversationId) continue;
      if (!["passed", "review_required", "failed", "approval_required", "cancelled", "blocked"].includes(job.status)) continue;
      const marker = `${job.id}:${job.status}`;
      if (completedChatJobIdsRef.current.has(marker)) continue;
      completedChatJobIdsRef.current.add(marker);

      if (job.status === "passed") {
        const lines = [
          "Bu yürütme tamamlandı.",
          job.result?.message,
          job.result?.outputPath ? `Çıktı konumu: ${job.result.outputPath}` : undefined,
          job.reviewGate?.status ? `İnceleme sonucu: ${job.reviewGate.status}` : undefined,
        ].filter(Boolean);
        updates.push(createChatMessage("assistant", lines.join("\n"), job.id, job.conversationId, jobProjectId(job)));
      } else if (job.status === "review_required") {
        updates.push(createChatMessage("assistant", `Bu yürütme bitti ancak henüz son teslim sayılamaz: ${job.lastMessage || "Hedef CAD uygulamasında kontrol veya insan incelemesi gerekiyor."}`, job.id, job.conversationId, jobProjectId(job)));
      } else if (job.status === "approval_required") {
        updates.push(createChatMessage("assistant", `Bu işlem için yerel otomasyon yetkisini onaylamanız gerekiyor: ${job.approvalReasons?.join("; ") || "Devam etmek için insan onayı gerekiyor."}`, job.id, job.conversationId, jobProjectId(job)));
      } else if (job.status === "failed") {
        updates.push(createChatMessage("assistant", `Bu yürütme başarısız: ${job.error || job.lastMessage || "Bilinmeyen hata"}\nDoğrudan «Bu hatayı düzeltmeye devam et» diyebilirsiniz.`, job.id, job.conversationId, jobProjectId(job)));
      } else if (job.status === "cancelled") {
        updates.push(createChatMessage("assistant", "Bu görev iptal edildi. Farklı gereksinimlerle yeni görev başlatabilirsiniz.", job.id, job.conversationId, jobProjectId(job)));
      } else if (job.status === "blocked") {
        updates.push(createChatMessage("assistant", `Bu görev ortam veya yetenek kontrolünde engellendi: ${job.blockedReasons?.join("; ") || job.lastMessage || "Bu yetenek henüz doğrulanmadı."}`, job.id, job.conversationId, jobProjectId(job)));
      }
    }
    if (updates.length > 0) {
      setAgentMessages((messages) => [...messages, ...updates].slice(-200));
      const updatedConversationIds = new Set(updates.map((message) => message.conversationId).filter(Boolean));
      setAgentConversations((items) => items.map((conversation) => updatedConversationIds.has(conversation.id)
        ? { ...conversation, updatedAt: new Date().toISOString() }
        : conversation));
    }
  }, [jobs]);

  useEffect(() => {
    if (!settingsLoaded) return;
    const settings: AppSettings = {
      activeWallpaper: activeWallpaper === "custom" && !customWallpaper?.sourcePath ? "blossom" : activeWallpaper,
      customWallpaperPath: customWallpaper?.sourcePath,
      wallpaperBrightness,
      wallpaperBlur,
      wallpaperVignette,
      workspaceOpacity,
      wallpaperMotionMode,
      wallpaperMotionStrength,
      defaultWallpaperVersion: 1,
      panelOpacityVersion: 1,
      recentWallpapers,
      projects,
      activeProjectId,
      projectName,
      recentProjectPath,
      apiConfig,
      knowledgeBase,
    };
    void writePersistedState("settings", SETTINGS_KEY, settings)
      .then((result) => result.degraded && setPersistenceWarning("SQLite Yazma başarısız; ayarlar yerel yedeğe güvenle kaydedildi."))
      .catch((error) => setPersistenceWarning(`Ayarlar kaydedilemedi: ${error instanceof Error ? error.message : String(error)}`));
  }, [activeProjectId, activeWallpaper, apiConfig, customWallpaper?.sourcePath, knowledgeBase, projectName, projects, recentProjectPath, recentWallpapers, settingsLoaded, wallpaperBlur, wallpaperBrightness, wallpaperMotionMode, wallpaperMotionStrength, wallpaperVignette, workspaceOpacity]);

  function renderTemplatePanel() {
    return (
      <section className="capability-board">
        {workspaceTemplates.map((template, index) => {
          const Icon = template.icon;
          return (
            <motion.button
              className={selectedTemplateKey === template.key ? "capability-card selected" : "capability-card"}
              key={template.key}
              onClick={() => selectTemplate(template)}
              initial={reducedMotion ? false : { y: 12, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.35, delay: index * 0.04 }}
              whileHover={reducedMotion ? undefined : { y: -3 }}
              whileTap={{ scale: 0.985 }}
            >
              <Icon size={22} weight="duotone" />
              <span>{selectedTemplateKey === template.key ? "Ayarlar yüklendi" : codexTargets[template.target]}</span>
              <strong>{template.title}</strong>
              <p>{template.detail}</p>
            </motion.button>
          );
        })}
      </section>
    );
  }

  function renderProjectPanel() {
    const capabilityAlerts = capabilityIdsForConfig(codexConfig)
      .map((id) => runtimeHealth?.capabilityManifest?.capabilities?.find((item) => item.id === id))
      .filter((item): item is Record<string, unknown> & { id?: string; level?: string } => Boolean(item && ["reference_only", "not_implemented"].includes(String(item.level))));
    return (
      <section className="project-console">
        <article className="project-brief">
          <div className="panel-heading compact">
            <div>
              <p className="eyebrow">PROJECT</p>
              <h2>{projectName}</h2>
            </div>
            <span className="status-pill">{workerStatus.running ? "Çalıştırılabilir" : "Başlatma bekliyor"}</span>
          </div>
          <div className="project-quick-grid">
            <button type="button" onClick={() => setActiveTab("model")}>
              <CubeFocus size={19} weight="duotone" />
              <strong>Sıfırdan modelle</strong>
              <span>Önce dosya içe aktarmak gerekmez</span>
            </button>
            <button type="button" onClick={chooseProjectFile}>
              <FolderOpen size={19} weight="duotone" />
              <strong>Mevcut dosyayı içe aktar</strong>
              <span>STEP / STL / DWG / PDF / Resim</span>
            </button>
            <button type="button" onClick={() => setActiveTab("drawing")}>
              <FilePlus size={19} weight="duotone" />
              <strong>Mühendislik çizimi oluştur</strong>
              <span>GB/T Çerçeve, ölçüler, delik tablosu</span>
            </button>
          </div>
        </article>

        <aside className="project-list-panel">
          <div className="panel-heading compact">
            <div>
              <p className="eyebrow">CONTEXT</p>
              <h2>Mevcut bağlam</h2>
            </div>
          </div>
          <div className="context-summary">
            <span>Referans dosyaları</span>
            <strong>{recentProjectPath ? displayNameFromPath(recentProjectPath) : "İçe aktarılmadı; sıfırdan modelleme yapılabilir"}</strong>
            <span>Yürütme ortamı</span>
            <strong>{runtimeMessage}</strong>
            <span>Varsayılan karar</span>
            <strong>Belirtilmeyen öğeleri AI seçer; kritik ölçüler ve güvenlik parametreleri doğrulanmalıdır</strong>
          </div>
          {capabilityAlerts.length > 0 ? (
            <div className="capability-alert" role="status">
              <strong>Mevcut ayarlar doğrulanmamış yetenek içeriyor</strong>
              <span>{capabilityAlerts.map((item) => `${item.id} · ${item.level}`).join("; ")}, Gönderim engellenir veya insan incelemesine alınır.</span>
            </div>
          ) : null}
        </aside>
      </section>
    );
  }

  function renderCheckPanel() {
    return (
      <section className="review-workspace">
        <article className="review-summary-card">
          <div className="panel-heading compact">
            <div>
              <p className="eyebrow">REVIEW</p>
              <h2>{resultJob ? jobDisplayTitle(resultJob) : "Görevin tamamlanması bekleniyor"}</h2>
            </div>
            <span className="status-pill">{jobReviewStatusLabel(resultJob)}</span>
          </div>
          <div className="review-table">
            {resultChecks.length > 0 ? (
              resultChecks.map((check, index) => (
                <div className={`review-row ${check.status || "pending"}`} key={check.id || index}>
                  <span>{check.severity || "CHECK"}</span>
                  <strong>{reviewStatusLabel(check.status)}</strong>
                  <small>{check.message || "İnceleme öğeleri döndürüldü ancak açıklama yok."}</small>
                </div>
              ))
            ) : (
              <div className="inspector-empty">
                <strong>Gerçek inceleme verisi yok</strong>
                <p>Görev tamamlandığında dosya varlığı, biçim, delik/kanal, çizim standardı ve üretim riskleri burada gösterilir.</p>
              </div>
            )}
          </div>
        </article>

        <aside className="review-summary-card compact-side">
          <div className="panel-heading compact">
            <div>
              <p className="eyebrow">FEATURES</p>
              <h2>Geometrik özellikler</h2>
            </div>
          </div>
          <div className="hole-list">
            {resultFeatures.length > 0 ? (
              resultFeatures.map((feature, index) => (
                <div className="hole-row" key={index}>
                  <span>{recordText(feature, ["name", "type", "label"], `Özellik (feature) ${index + 1}`)}</span>
                  <strong>{recordText(feature, ["spec", "size", "dimension", "value"], "")}</strong>
                  <small>{recordText(feature, ["position", "pos", "location", "note"], "Görev sonucu tarafından döndürüldü")}</small>
                  <em>{recordText(feature, ["status"], "İnceleme bekliyor")}</em>
                </div>
              ))
            ) : (
              <div className="inspector-empty">
                <strong>Henüz özellik tablosu yok</strong>
                <p>AI gerçek delik, kanal, diş veya montaj özelliklerini döndürdüğünde bunlar otomatik listelenir.</p>
              </div>
            )}
          </div>
        </aside>
      </section>
    );
  }

  function renderExportPanel() {
    const grouped = groupedArtifacts(resultArtifacts);
    const assessment = assessDelivery(resultJob);
    const retryStage = retryStageForJob(resultJob);
    const versionComparison = artifactVersionComparison(resultJob);
    const diagnostics = backendDiagnosticsFor(resultJob);
    const history = resultJob?.runHistory ?? [];
    const relations = resultJob?.artifactRelations ?? [];
    const canRetry = Boolean(resultJob && ["failed", "blocked", "cancelled", "review_required"].includes(resultJob.status));
    const groupLabels: Array<[keyof typeof grouped, string]> = [
      ["model", "Model"],
      ["drawing", "Mühendislik çizimi"],
      ["bom", "BOM"],
      ["preview", "Önizleme"],
      ["report", "İnceleme raporu"],
      ["other", "Diğer"],
    ];
    return (
      <section className="delivery-console">
        <article className="delivery-main">
          <div className="panel-heading compact">
            <div>
              <p className="eyebrow">DELIVERY</p>
              <h2>Yerel teslim listesi</h2>
            </div>
            <div className="delivery-heading-actions">
              {canRetry && resultJob ? (
                <motion.button className="ghost-button compact-action" type="button" disabled={retryingJobId !== null} onClick={() => void retryJob(resultJob.id)} whileTap={{ scale: 0.975 }}>
                  <ArrowClockwise className={retryingJobId === resultJob.id ? "spin" : undefined} size={17} weight="bold" />
                  {retryingJobId === resultJob.id ? "Sıraya alınıyor" : `${retryStageLabel(retryStage)} aşamasından yeniden üret`}
                </motion.button>
              ) : null}
              <motion.button className="primary-button compact-action shine" type="button" onClick={enqueueDeliveryTask} whileHover={reducedMotion ? undefined : { y: -2 }} whileTap={{ scale: 0.975 }}>
                <Archive size={17} weight="duotone" />
                Teslim paketi oluştur
              </motion.button>
            </div>
          </div>
          <div className={`delivery-gate ${assessment.disposition}`}>
            <div className="delivery-gate-copy">
              <span>{assessment.disposition === "ready" ? "DELIVERY READY" : assessment.disposition === "review_required" ? "MANUAL REVIEW" : "DELIVERY GATE"}</span>
              <strong>{assessment.title}</strong>
              <p>{assessment.summary}</p>
            </div>
            <div className="delivery-gate-metrics">
              <span><strong>{assessment.readyArtifacts}</strong> Bu yürütmenin geçerli çıktıları</span>
              <span><strong>{history.length + (resultJob ? 1 : 0)}</strong> Sürümü koru</span>
              <span><strong>{resultJob?.reviewGate?.checks?.length ?? resultJob?.result?.checks?.length ?? 0}</strong> Makine kontrolleri</span>
            </div>
            {assessment.issues.length ? (
              <div className="delivery-issue-list">
                {assessment.issues.slice(0, 5).map((issue) => <span key={issue}>{issue}</span>)}
              </div>
            ) : null}
          </div>
          {selectedPreviewArtifact ? (
            <section className="delivery-preview-stage">
              <div className="delivery-section-heading"><strong>Mevcut önizleme</strong><span>{selectedPreviewArtifact.path?.split(/[\\/]/).pop()}</span></div>
              <ArtifactBrowser artifacts={[]} selected={selectedPreviewArtifact} onSelect={setSelectedPreviewArtifactPath} />
            </section>
          ) : null}
          <div className="delivery-groups">
            {groupLabels.map(([group, label]) => grouped[group].length > 0 ? (
              <section className="delivery-group" key={group}>
                <div className="delivery-group-heading"><strong>{label}</strong><span>{grouped[group].length}  öğe</span></div>
                <ArtifactBrowser artifacts={grouped[group]} selected={selectedPreviewArtifact} onSelect={setSelectedPreviewArtifactPath} showPreview={false} />
              </section>
            ) : null)}
            {!resultArtifacts.length ? <ArtifactBrowser artifacts={resultArtifacts} selected={selectedPreviewArtifact} onSelect={setSelectedPreviewArtifactPath} showPreview={false} /> : null}
          </div>
          {relations.length ? (
            <section className="delivery-trace">
              <div className="delivery-section-heading"><strong>Çıktı izlenebilirliği</strong><span>{relations.length}  ilişki</span></div>
              {relations.slice(0, 8).map((relation, index) => (
                <div className="delivery-trace-row" key={`${relation.from}-${relation.to}-${index}`}>
                  <span title={relation.from}>{relation.from?.split(/[\\/]/).pop() || "Kaynak çıktı"}</span>
                  <strong>{relation.type || relation.relation || "Oluştur"}</strong>
                  <span title={relation.to}>{relation.to?.split(/[\\/]/).pop() || "Hedef çıktı"}</span>
                </div>
              ))}
            </section>
          ) : null}
        </article>

        <aside className="delivery-side">
          <div className="delivery-path">
            <span>Çıktı klasörü</span>
            <strong>{codexConfig.outputDir}</strong>
            <button type="button" onClick={chooseOutputDir}>Klasörü değiştir</button>
          </div>
          <div className="format-strip">
            {deliveryFormats.map((format) => {
              const status = deliveryFormatStatus(format, resultJob, resultArtifacts);
              return (
                <span className={status} key={format}>
                  {format} · {status === "ready" ? "Üretildi" : status === "missing" ? "Eksik" : "İstenmedi"}
                </span>
              );
            })}
          </div>
          <div className="review-mini">
            <span>İnceleme durumu</span>
            <strong>{resultJob ? jobReviewStatusLabel(resultJob) : "Üretim sonrası inceleme bekleniyor"}</strong>
          </div>
          {resultJob?.drawingEvidence ? <div className="review-mini"><span>Çizim kanıtı</span><strong>{reviewStatusLabel(resultJob.drawingEvidence.status)}</strong><small>{resultJob.drawingEvidence.error_code || retryStageLabel(resultJob.drawingEvidence.stage)}</small></div> : null}
          {resultJob?.bomEvidence ? <div className="review-mini"><span>BOM Kanıt</span><strong>{reviewStatusLabel(resultJob.bomEvidence.status)}</strong><small>{resultJob.bomEvidence.error_code || retryStageLabel(resultJob.bomEvidence.stage)}</small></div> : null}
          {resultJob?.dfmEvidence ? <div className="review-mini"><span>DFM Kanıt</span><strong>{reviewStatusLabel(resultJob.dfmEvidence.status)}</strong><small>{resultJob.dfmEvidence.error_code || retryStageLabel(resultJob.dfmEvidence.stage)}</small></div> : null}
          {diagnostics.length ? (
            <div className="delivery-diagnostics">
              <div className="delivery-section-heading"><strong>Backend tanılama</strong><span>{diagnostics.length}  öğe</span></div>
              {diagnostics.map((diagnostic, index) => (
                <div className={`delivery-diagnostic-row ${diagnostic.status ?? "unknown"}`} key={`${diagnostic.backend}-${index}`}>
                  <span>{diagnostic.backend || "CAD Backend"}</span>
                  <strong>{diagnostic.status || "unknown"}</strong>
                  <small>{diagnostic.error_code || diagnostic.limitations?.[0] || retryStageLabel(diagnostic.stage)}</small>
                </div>
              ))}
            </div>
          ) : null}
          {resultJob ? (
            <div className="delivery-versions">
              <div className="delivery-section-heading"><strong>Sürüm geçmişi</strong><span>{history.length + 1}  yürütme</span></div>
              <div className="delivery-version-row current">
                <span>Mevcut</span><strong>{resultJob.runId}</strong><small>{jobStatusLabel(resultJob.status)} · {resultArtifacts.length}  öğe</small>
              </div>
              {[...history].reverse().slice(0, 5).map((run, index) => (
                <div className="delivery-version-row" key={`${run.runId}-${index}`}>
                  <span>V{history.length - index}</span><strong>{run.runId || "Önceki sürüm"}</strong><small>{run.status ? jobStatusLabel(run.status) : "Arşivlendi"} · {run.artifacts?.length ?? 0}  öğe</small>
                </div>
              ))}
              {history.length ? <p className="version-diff">Önceki yürütmeye göre: eklenen  {versionComparison.added} · Sil {versionComparison.removed} · Değişiklik {versionComparison.changed} · Değişmedi {versionComparison.unchanged}</p> : null}
            </div>
          ) : null}
        </aside>
      </section>
    );
  }

  function renderSettingsPanel() {
    return (
      <section className="tab-surface">
        <EnvironmentRemediationPanel remediations={runtimeHealth?.remediations ?? []} onCopyCommand={copyRuntimeCommand} onOpenDownload={openRuntimeDownload} />
        {persistenceWarning ? (
          <div className="persistence-warning" role="status">
            <WarningCircle size={18} weight="duotone" />
            <span>{persistenceWarning}</span>
            <button type="button" onClick={() => setPersistenceWarning(null)}>Anladım</button>
          </div>
        ) : null}
        <div className="settings-studio">
          <article className="setting-card api-card primary-setting">
            <div className="setting-title">
              <span>Yürütme çekirdeği</span>
              <strong>{agentProviderCatalog[apiConfig.agentProvider].name}</strong>
              <p>Yerel Agent CLI otomatik algılanır. Görev protokolü, onay, RAG, CAD araçları ve teslim incelemesi birlikte yönetilir. Bu uygulama API anahtarı saklamaz.</p>
            </div>
            <div className="agent-provider-grid" role="radiogroup" aria-label="Agent Provider">
              {(Object.keys(agentProviderCatalog) as AgentProviderId[]).map((providerId) => {
                const metadata = agentProviderCatalog[providerId];
                const health = runtimeHealth?.agentProviders?.find((item) => item.id === providerId);
                const unavailable = runtimeHealth ? !health?.installed : false;
                return (
                  <button
                    type="button"
                    role="radio"
                    aria-checked={apiConfig.agentProvider === providerId}
                    disabled={unavailable}
                    className={apiConfig.agentProvider === providerId ? "active" : ""}
                    key={providerId}
                    onClick={() => selectAgentProvider(providerId)}
                  >
                    <strong>{metadata.company} · {metadata.name}</strong>
                    <span>{health?.installed ? `Yüklü · ${health.version?.message || "Sürüm bilinmiyor"}` : runtimeHealth ? "Yüklü değil" : "Algılama bekleniyor"}</span>
                    <small>{health?.verified ? "Gerçek görev doğrulandı" : health?.auth?.ok === false ? "Kimlik doğrulama başarısız; yürütülemiyor" : health?.installed ? "İlk gerçek görev doğrulaması bekleniyor" : "Önce CLI kurulmalıdır"}</small>
                  </button>
                );
              })}
            </div>
            <label className="agent-model-select">
              <span>Mevcut model · {agentProviderCatalog[apiConfig.agentProvider].company}</span>
              <select aria-label="AI modelini seç" value={apiConfig.model} onChange={(event) => selectAgentModel(event.target.value)}>
                {providerModelOptions.map((model) => (
                  <option value={model.value} key={model.value}>{agentProviderCatalog[apiConfig.agentProvider].company} · {model.label}</option>
                ))}
              </select>
              <small>CC Switch ayarlarındaki modeller listeye otomatik eklenir. Model seçmezseniz yerel CLI ayarları kullanılır.</small>
            </label>
            <div className="api-mode-grid">
              {(["codex_cli", "cc_switch"] as ApiIntegrationMode[]).map((mode) => (
                <button type="button" className={apiConfig.mode === mode ? "active" : ""} key={mode} onClick={() => setApiConfig((config) => ({ ...config, mode }))}>
                  {apiModeLabel(mode)}
                </button>
              ))}
            </div>
            <div className="api-sync-row">
              <button type="button" onClick={() => void syncCcSwitchConfig()}>
                CC Switch durumunu oku
              </button>
              <span>{apiSyncMessage}</span>
            </div>
            <div className="api-status-strip">
              <span>{selectedProvider?.name || agentProviderCatalog[apiConfig.agentProvider].name}: {selectedProvider?.ready ? "Çalıştırılabilir" : "Doğrulama bekliyor"}</span>
              <span>CLI: {selectedProvider?.version?.message || "Algılanıyor"}</span>
              <span className="settings-path">Giriş: {selectedProvider?.entry || "Algılanıyor"}</span>
              <span>Skill: {runtimeHealth?.solidworksSkillPath || "Algılanıyor"}</span>
              <span>SQLite Dizin: {storeMigration ? storeMigration.countsMatch ? "Adet tutarlı" : "Düzeltme bekliyor" : "Algılanıyor"}</span>
            </div>
            {selectedCcSwitchProviders.length ? (
              <div className="provider-list">
                <div className="provider-list-head">
                  <strong>{agentProviderCatalog[apiConfig.agentProvider].name} Model yönlendirmesi</strong>
                  <span>{selectedCcSwitchProviders.length}  adet · Mevcut öğeyi seçer:  CC Switch Belirle</span>
                </div>
                {selectedCcSwitchProviders.map((provider) => (
                  <div className={provider.active ? "provider-row active" : "provider-row"} key={provider.id || provider.name}>
                    <div className="provider-main">
                      <strong>{provider.name || provider.id}</strong>
                      <small>{provider.endpoint || "Endpoint, CC Switch tarafından yönetilir"}</small>
                    </div>
                    <span>{provider.model || "Modeli izle CC Switch"}</span>
                    <small>{provider.authLabel || "Yapılandırma, CC Switch tarafından yönetilir"}</small>
                  </div>
                ))}
              </div>
            ) : null}
          </article>

          <article className="setting-card status-setting">
            <span>Yerel yürütme</span>
            <strong>{workerStatus.running ? `Çalışıyor · PID ${workerStatus.pid ?? "-"}` : "Başlatılmadı"}</strong>
            <p>{workerStatus.health?.heartbeatAt ? `Son heartbeat ${workerStatus.health.heartbeatAt}` : runtimeMessage}</p>
            <button type="button" onClick={() => void (workerStatus.running ? stopLocalWorker() : startLocalWorker())}>
              {workerStatus.running ? "Yerel yürütücüyü durdur" : "Yerel yürütücüyü başlat"}
            </button>
          </article>
          <article className="setting-card status-setting amber">
            <span>Yerel çıktı</span>
            <strong>Yalnızca yerelde sakla</strong>
            <p>{codexConfig.outputDir}</p>
            <button type="button" onClick={chooseOutputDir}>Çıktı klasörünü seç</button>
          </article>
          <article className="setting-card status-setting dark">
            <span>Görünüm</span>
            <strong>{activeWallpaperName}</strong>
            <p>Yerel resim, GIF ve video duvar kâğıtları desteklenir. CAD bilgilerinin okunabilirliği için düşük doygunluklu arka plan kullanın.</p>
            <button type="button" onClick={() => setAppearanceOpen(true)}>Görünüm ayarlarını aç</button>
          </article>
          <article className="setting-card knowledge-setting">
            <span>Uzmanlık bilgi tabanı</span>
            <strong>{knowledgeBase.cloudEnabled ? "Yerel + Bulut" : "Yerel öncelikli"}</strong>
            <div className="knowledge-mode" role="group" aria-label="Bilgi tabanı modu">
              <button type="button" className={!knowledgeBase.cloudEnabled ? "active" : ""} onClick={() => setKnowledgeBase((config) => ({ ...config, cloudEnabled: false }))}>Yerel</button>
              <button type="button" className={knowledgeBase.cloudEnabled ? "active" : ""} onClick={() => setKnowledgeBase((config) => ({ ...config, cloudEnabled: true }))}>Bulut desteği</button>
            </div>
            {knowledgeBase.cloudEnabled ? (
              <div className="knowledge-fields">
                <label>
                  <span>HTTPS Arama adresi</span>
                  <input value={knowledgeBase.endpoint} placeholder="https://rag.example.com/retrieve" onChange={(event) => setKnowledgeBase((config) => ({ ...config, endpoint: event.target.value }))} />
                </label>
                <label>
                  <span>Namespace</span>
                  <input value={knowledgeBase.namespace} onChange={(event) => setKnowledgeBase((config) => ({ ...config, namespace: event.target.value }))} />
                </label>
              </div>
            ) : (
              <p>{knowledgeBase.localRoots[0] || "Yerleşik SolidWorks, üretim ve çizim standartları bilgisi kullanılır."}</p>
            )}
            <button type="button" onClick={() => void chooseKnowledgeRoot()}>Yerel standart kitaplığı ekle</button>
          </article>
        </div>
      </section>
    );
  }

  function renderHelpPanel() {
    const providers = runtimeHealth?.agentProviders ?? [];
    const installedProviders = providers.filter((provider) => provider.installed).map((provider) => provider.name);
    const topic = helpTopics.find((item) => item.id === activeHelpTopic) ?? helpTopics[0];
    return (
      <section className="help-workspace">
        <div className="help-intro">
          <div className="help-intro-title">
            <Question size={22} weight="duotone" />
            <div>
              <span>Kullanım kılavuzu</span>
              <strong>CAD Studio İşlemler ve sorun giderme</strong>
            </div>
          </div>
          <p>Mevcut ortam durumuna göre yerel yardım. Soldan bir konu seçip denetim adımlarını izleyin.</p>
        </div>
        <div className="help-status-grid">
          <div><span>AI</span><strong>{installedProviders.length ? installedProviders.join(", ") : "Kullanılabilir CLI henüz algılanmadı"}</strong></div>
          <div><span>Python</span><strong>{runtimeHealth?.python?.ok ? "Hazır" : "Python 3 kurulmalıdır"}</strong></div>
          <div><span>SolidWorks</span><strong>{runtimeHealth?.solidworks?.ok ? "Kullanılabilir" : "Algılanmadı veya kontrol bekliyor"}</strong></div>
          <div><span>AutoCAD</span><strong>{runtimeHealth?.autocad?.ok ? "Kullanılabilir" : "Algılanmadı"}</strong></div>
        </div>
        <EnvironmentRemediationPanel remediations={runtimeHealth?.remediations ?? []} onCopyCommand={copyRuntimeCommand} onOpenDownload={openRuntimeDownload} />
        <div className="help-guide">
          <nav className="help-topic-list" aria-label="Yardım konuları">
            {helpTopics.map((item) => (
              <button
                type="button"
                className={activeHelpTopic === item.id ? "active" : ""}
                aria-current={activeHelpTopic === item.id ? "page" : undefined}
                key={item.id}
                onClick={() => setActiveHelpTopic(item.id)}
              >
                <strong>{item.label}</strong>
                <span>{item.title}</span>
              </button>
            ))}
          </nav>
          <article className="help-topic-detail">
            <p className="eyebrow">{topic.label}</p>
            <h2>{topic.title}</h2>
            <p className="help-topic-summary">{topic.summary}</p>
            <ol>
              {topic.items.map((item, index) => (
                <li key={item.title}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </article>
        </div>
        <PreviewShowcase />
        <div className="help-note">
          <ShieldCheck size={19} weight="duotone" />
          <p>Görev kayıtları, onaylar ve incelemeler yerelde saklanır. Soldaki görevi silmek yalnızca geçmiş meta verisini temizler; dışa aktarılan CAD dosyalarını silmez.</p>
        </div>
      </section>
    );
  }

  function renderWorkspacePanel() {
    if (activeTab === "project") return renderProjectPanel();
    if (activeTab === "check") return renderCheckPanel();
    if (activeTab === "export") return renderExportPanel();
    if (activeTab === "settings") return renderSettingsPanel();
    if (activeTab === "help") return renderHelpPanel();
    return renderTemplatePanel();
  }

  const activeWallpaperName =
    activeWallpaper === "custom" ? customWallpaper?.name ?? "Duvar kâğıtlarım" : wallpapers.find((item) => item.id === activeWallpaper)?.name ?? "Aurora";
  const activePresetWallpaper = activeWallpaper === "custom" ? undefined : wallpapers.find((item) => item.id === activeWallpaper);
  const effectiveWallpaperMotion: WallpaperMotionMode = reducedMotion ? "still" : wallpaperMotionMode;
  const shot = wallpaperShots[wallpaperShot % wallpaperShots.length];
  const shotStrength = wallpaperMotionStrength / 100;
  const wallpaperCameraStyle = {
    "--wallpaper-camera-x": `${shot.x * shotStrength}%`,
    "--wallpaper-camera-y": `${shot.y * shotStrength}%`,
    "--wallpaper-camera-scale": `${1 + (shot.scale - 1) * shotStrength}`,
  } as CSSProperties;
  const activeAgentEvents = activeAgentJob ? jobEvents[activeAgentJob.id] ?? [] : [];
  const activeAgentLogs = activeAgentJob ? jobLogTails[activeAgentJob.id] ?? {} : {};
  const activeManualReviewDraft = activeAgentJob ? manualReviewDrafts[activeAgentJob.id] ?? { note: "", checks: [] } : { note: "", checks: [] };
  const activeManualReviewOptions = reviewOptionsFor(activeAgentJob);

  return (
    <main
      className={`app-shell theme-${activeWallpaper}`}
      style={
        {
          "--wallpaper-brightness": `${wallpaperBrightness}%`,
          "--wallpaper-blur": `${wallpaperBlur}px`,
          "--wallpaper-vignette": `${wallpaperVignette / 100}`,
          "--workspace-opacity": `${workspaceOpacity / 100}`,
        } as CSSProperties
      }
      onPointerMove={controlWallpaperPointer}
      onPointerLeave={resetWallpaperPointer}
    >
      <div className="wallpaper" aria-hidden="true">
        <div className={`wallpaper-camera motion-${effectiveWallpaperMotion}`} style={wallpaperCameraStyle}>
        <AnimatePresence>
          {activeWallpaper === "blossom" ? (
            <motion.video
              key="default-blossom"
              className="custom-wallpaper-layer custom-wallpaper-video"
              src={DEFAULT_WALLPAPER_URL}
              poster={DEFAULT_WALLPAPER_POSTER_URL}
              autoPlay={!reducedMotion}
              loop
              muted
              playsInline
              initial={reducedMotion ? false : { opacity: 0, scale: 1.02 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={reducedMotion ? undefined : { opacity: 0, scale: 1.02 }}
              transition={{ duration: 0.55 }}
            />
          ) : customWallpaper && activeWallpaper === "custom" ? (
            customWallpaper.kind === "video" ? (
              <motion.video
                className="custom-wallpaper-layer custom-wallpaper-video"
                src={customWallpaper.url}
                autoPlay={!reducedMotion}
                loop
                muted
                playsInline
                initial={reducedMotion ? false : { opacity: 0, scale: 1.02 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={reducedMotion ? undefined : { opacity: 0, scale: 1.02 }}
                transition={{ duration: 0.55 }}
              />
            ) : (
              <motion.div
                className="custom-wallpaper-layer"
                style={{ backgroundImage: `url("${customWallpaper.url}")` }}
                initial={reducedMotion ? false : { opacity: 0, scale: 1.02 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={reducedMotion ? undefined : { opacity: 0, scale: 1.02 }}
                transition={{ duration: 0.55 }}
              />
            )
          ) : activePresetWallpaper?.assetUrl ? (
            <motion.div
              key={activePresetWallpaper.id}
              className="custom-wallpaper-layer preset-wallpaper-layer"
              style={{ backgroundImage: `url("${activePresetWallpaper.assetUrl}")` }}
              initial={reducedMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reducedMotion ? undefined : { opacity: 0 }}
              transition={{ duration: 0.7 }}
            />
          ) : null}
        </AnimatePresence>
        </div>
      </div>

      <motion.section
        className="desktop-frame"
        initial={reducedMotion ? false : { y: 24, opacity: 0, scale: 0.985 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        transition={{ duration: 0.75, ease: [0.22, 1, 0.36, 1] }}
      >
        <aside className="dock-panel liquid">
          <div className="profile-card">
            <div className="avatar">
              <CubeFocus size={24} weight="duotone" />
            </div>
            <div>
              <strong>CAD Studio</strong>
              <span>Yerel otomasyon çalışma alanı</span>
            </div>
          </div>

          <div className="sidebar-project-head">
            <span>Mevcut proje</span>
            <ProjectSwitcher
              activeProjectId={activeProjectId}
              projectName={projectName}
              projectNameDraft={projectNameDraft}
              projects={projects}
              projectTaskCounts={projectTaskCounts}
              editing={editingProjectName}
              menuOpen={projectMenuOpen}
              reducedMotion={Boolean(reducedMotion)}
              deleteCandidateProjectId={deleteCandidateProjectId}
              deletingProjectId={deletingProjectId}
              onDraftChange={setProjectNameDraft}
              onCommitName={commitProjectName}
              onCancelEdit={() => {
                setProjectNameDraft(projectName);
                setEditingProjectName(false);
              }}
              onStartEdit={() => {
                setProjectMenuOpen(false);
                setProjectNameDraft(projectName);
                setEditingProjectName(true);
              }}
              onToggleMenu={() => setProjectMenuOpen((open) => !open)}
              onSelect={selectProject}
              onCreate={createProject}
              onDuplicate={duplicateProject}
              onToggleArchive={toggleProjectArchive}
              onDelete={(project) => void deleteProject(project)}
            />
            <small className="project-task-count">{activeProjectJobs.length ? `${activeProjectJobs.length}  görev · ${queueSummary}` : "Henüz görev yok"}</small>
            <button className="new-task-button" type="button" onClick={() => {
              setSelectedTemplateKey(null);
              setActiveTab("model");
              setWindowHint("Şablon seçin veya gereksinimleri girin; onayladıktan sonra yürütün");
            }}>
              <FilePlus size={16} weight="bold" />
              Yeni görev
            </button>
          </div>

          <TaskSequence
            jobs={recentJobs}
            activeJobId={activeAgentJob?.id}
            deleteCandidateJobId={deleteCandidateJobId}
            deletingJobId={deletingJobId}
            terminalCount={terminalJobs.length}
            onSelect={(job) => {
              setDeleteCandidateJobId(null);
              setActiveAgentJobId(job.id);
              setExpandedJobId(job.id);
              if (job.conversationId) setActiveConversationId(job.conversationId);
              setActiveTab("project");
            }}
            onDelete={(job) => void deleteJob(job)}
            onClearTerminal={clearTerminalJobRecords}
          />

          <div className="local-chip">
            <ShieldCheck size={18} weight="duotone" />
            <span>Çıktılar varsayılan olarak yerelde saklanır: </span>
          </div>
        </aside>

        <section className="main-window liquid">
          <header className="window-bar app-toolbar">
            <div className="project-title">
              <strong>{currentPage.title}</strong>
              <span>{projectName} · Standart kitaplığı GB/T</span>
              <small>{windowHint}</small>
            </div>
            <div className="top-menu" role="toolbar" aria-label="Çalışma alanı gezintisi">
              <button type="button" onClick={chooseProjectFile} title="CAD, çizim veya eskiz dosyası içe aktar">
                <FilePlus size={15} weight="bold" />
                İçe aktar
              </button>
              {navItems.map(([key, label]) => (
                <button type="button" aria-pressed={activeTab === key} className={activeTab === key ? "active" : ""} key={key} onClick={() => setActiveTab(key)}>
                  {label.replace(/^\d+\s*/, "")}
                </button>
              ))}
            </div>
            <div className="toolbar-actions">
              <motion.button className="icon-button" onClick={() => setAppearanceOpen((value) => !value)} whileHover={reducedMotion ? undefined : { y: -2 }} whileTap={{ scale: 0.96 }}>
                <Aperture size={18} weight="duotone" />
                <span>Görünüm</span>
              </motion.button>
              <motion.button className="icon-button" aria-label="Ayarları aç" title="Ayarlar" onClick={() => setActiveTab("settings")} whileHover={reducedMotion ? undefined : { y: -2 }} whileTap={{ scale: 0.96 }}>
                <GearSix size={18} weight="duotone" />
              </motion.button>
            </div>
            <div className="window-controls" role="group" aria-label="Pencere kontrolü">
              <motion.button
                className="window-control minimize"
                type="button"
                title="Pencereyi küçült"
                aria-label="Pencereyi küçült"
                onClick={() => controlWindow("minimize")}
                whileHover={reducedMotion ? undefined : { y: -1 }}
                whileTap={{ scale: 0.96 }}
              >
                <Minus size={14} weight="bold" />
                <span>Küçült</span>
              </motion.button>
              <motion.button
                className="window-control maximize"
                type="button"
                title="Pencereyi büyüt veya geri yükle"
                aria-label="Pencereyi büyüt veya geri yükle"
                onClick={() => controlWindow("maximize")}
                whileHover={reducedMotion ? undefined : { y: -1 }}
                whileTap={{ scale: 0.96 }}
              >
                <Square size={12} weight="bold" />
                <span>Büyüt</span>
              </motion.button>
              <motion.button
                className="window-control close"
                type="button"
                title="Pencereyi kapat"
                aria-label="Pencereyi kapat"
                onClick={() => controlWindow("close")}
                whileHover={reducedMotion ? undefined : { y: -1 }}
                whileTap={{ scale: 0.96 }}
              >
                <X size={13} weight="bold" />
                <span>Kapat</span>
              </motion.button>
            </div>

            <AnimatePresence>
              {appearanceOpen ? (
                <motion.div
                  className="appearance-popover"
                  initial={reducedMotion ? false : { opacity: 0, y: -10, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={reducedMotion ? undefined : { opacity: 0, y: -10, scale: 0.98 }}
                  transition={{ duration: 0.22 }}
                >
                  <div className="switcher-head">
                    <span>Görünüm</span>
                    <small>{activeWallpaperName}</small>
                  </div>
                  <input ref={wallpaperInputRef} className="wallpaper-input" type="file" accept="image/*,video/*" onChange={importWallpaper} />
                  <button
                    className="drop-wallpaper"
                    onClick={chooseWallpaper}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={dropWallpaper}
                  >
                    <UploadSimple size={22} weight="duotone" />
                    <strong>Yerel duvar kâğıdını içe aktar</strong>
                    <span>Resim, GIF veya videoyu önizlemek için buraya sürükleyin</span>
                  </button>
                  <div className="wallpaper-grid compact">
                    {wallpapers.map((wallpaper) => (
                      <motion.button
                        className={activeWallpaper === wallpaper.id ? `wallpaper-tile ${wallpaper.id} active` : `wallpaper-tile ${wallpaper.id}`}
                        key={wallpaper.id}
                        onClick={() => setActiveWallpaper(wallpaper.id)}
                        whileHover={reducedMotion ? undefined : { y: -3 }}
                        whileTap={{ scale: 0.97 }}
                      >
                        <span className="tile-preview" style={wallpaper.assetUrl ? { backgroundImage: `url("${wallpaper.assetUrl}")` } : undefined} />
                        <strong>{wallpaper.name}</strong>
                        <small>{wallpaper.hint}</small>
                      </motion.button>
                    ))}
                    {customWallpaper ? (
                      <motion.button
                        className={activeWallpaper === "custom" ? "wallpaper-tile custom active" : "wallpaper-tile custom"}
                        onClick={() => setActiveWallpaper("custom")}
                        whileHover={reducedMotion ? undefined : { y: -3 }}
                        whileTap={{ scale: 0.97 }}
                      >
                        <span
                          className="tile-preview custom-preview"
                          style={customWallpaper.kind === "image" ? { backgroundImage: `url("${customWallpaper.url}")` } : undefined}
                        >
                          {customWallpaper.kind === "video" ? <Play size={18} weight="fill" /> : null}
                        </span>
                        <strong>Duvar kâğıtlarım</strong>
                      </motion.button>
                    ) : null}
                  </div>
                  {recentWallpapers.length > 0 ? (
                    <div className="recent-wallpapers">
                      <span>Son kullanılan</span>
                      {recentWallpapers.map((wallpaper) => (
                        <button key={wallpaper.path} type="button" onClick={() => applyWallpaperPath(wallpaper.path)}>
                          <ImageSquare size={15} weight="duotone" />
                          <strong>{wallpaper.name}</strong>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <div className="wallpaper-motion-grid" role="radiogroup" aria-label="Duvar kâğıdı hareketi">
                    {(Object.keys(wallpaperMotionLabels) as WallpaperMotionMode[]).map((mode) => (
                      <button
                        type="button"
                        role="radio"
                        aria-checked={wallpaperMotionMode === mode}
                        className={wallpaperMotionMode === mode ? "active" : ""}
                        key={mode}
                        onClick={() => setWallpaperMotionMode(mode)}
                      >
                        {wallpaperMotionLabels[mode]}
                      </button>
                    ))}
                    <button type="button" className="wallpaper-shot-button" onClick={() => setWallpaperShot((shotIndex) => (shotIndex + 1) % wallpaperShots.length)}>
                      <Aperture size={15} weight="duotone" />
                      Yakın görünüşü değiştir
                    </button>
                  </div>
                  <div className="wallpaper-controls">
                    <div className="panel-opacity-presets" role="group" aria-label="Arayüz kaplama ön ayarı">
                      <button type="button" className={workspaceOpacity <= 30 ? "active" : ""} onClick={() => setWorkspaceOpacity(24)}>Geçişli</button>
                      <button type="button" className={workspaceOpacity > 30 && workspaceOpacity < 66 ? "active" : ""} onClick={() => setWorkspaceOpacity(46)}>Dengeli</button>
                      <button type="button" className={workspaceOpacity >= 66 ? "active" : ""} onClick={() => setWorkspaceOpacity(78)}>Odak</button>
                    </div>
                    <label>
                      <span>Hareket miktarı</span>
                      <input type="range" min="0" max="100" value={wallpaperMotionStrength} onChange={(event) => setWallpaperMotionStrength(Number(event.target.value))} />
                    </label>
                    <label>
                      <span>Parlaklık</span>
                      <input type="range" min="72" max="112" value={wallpaperBrightness} onChange={(event) => setWallpaperBrightness(Number(event.target.value))} />
                    </label>
                    <label>
                      <span>Bulanıklık</span>
                      <input type="range" min="0" max="14" value={wallpaperBlur} onChange={(event) => setWallpaperBlur(Number(event.target.value))} />
                    </label>
                    <label>
                      <span>Vinyet</span>
                      <input type="range" min="0" max="42" value={wallpaperVignette} onChange={(event) => setWallpaperVignette(Number(event.target.value))} />
                    </label>
                    <label>
                      <span>Arayüz kaplaması <output>{workspaceOpacity}%</output></span>
                      <input type="range" min="18" max="92" value={workspaceOpacity} onChange={(event) => setWorkspaceOpacity(Number(event.target.value))} />
                    </label>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </header>

          {renderWorkspacePanel()}
          <AppUpdatePanel expanded={activeTab === "settings"} />

          {["project", "model", "holes", "drawing"].includes(activeTab) ? (
            <>
          {["model", "holes", "drawing"].includes(activeTab) ? (
          <section className="codex-bridge" ref={bridgeRef}>
            <div className="bridge-copy">
              <p className="eyebrow">AGENT BRIDGE</p>
              <h2>CAD görevi oluştur</h2>
              <p>Hedefi, kayıt konumunu ve yürütme tercihlerini adım adım doldurun. Uygulama bunları yerel bir CAD Agent görevine dönüştürür; dosyalar yerelde saklanır.</p>
            </div>

            <div className="bridge-controls">
              <section className="workflow-card">
                <div className="workflow-card-head">
                  <span>01</span>
                  <div>
                    <strong>Görev içeriği</strong>
                    <small>İstediğiniz modeli veya çizimi açıklayın</small>
                  </div>
                </div>
                <label className="bridge-field wide">
                  <span>Gereksinim açıklaması</span>
                  <textarea value={codexConfig.objective} onChange={(event) => updateCodexConfig({ objective: event.target.value })} />
                </label>
                <div className="bridge-field">
                  <span>Hedef modül</span>
                  <div className="segmented-control">
                    {(Object.keys(codexTargets) as Array<CodexConfig["target"]>).map((target) => (
                      <button
                        type="button"
                        className={codexConfig.target === target ? "active" : ""}
                        key={target}
                        onClick={() => updateCodexConfig({ target })}
                      >
                        {codexTargets[target]}
                      </button>
                    ))}
                  </div>
                </div>
              </section>

              <section className="workflow-card">
                <div className="workflow-card-head">
                  <span>02</span>
                  <div>
                    <strong>Yerelde kaydet</strong>
                    <small>Çıktıları ve hedef klasörü seçin</small>
                  </div>
                </div>
                <div className="bridge-field">
                  <span>Çıktı</span>
                  <div className="segmented-control output-control">
                    {(Object.keys(codexOutputs) as Array<CodexConfig["expectedOutput"]>).map((output) => (
                      <button
                        type="button"
                        className={codexConfig.expectedOutput === output ? "active" : ""}
                        key={output}
                        onClick={() => updateCodexConfig({ expectedOutput: output })}
                      >
                        {codexOutputs[output]}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="bridge-field wide">
                  <span>Çıktı klasörü</span>
                  <div className="output-path-row">
                    <input value={codexConfig.outputDir} onChange={(event) => updateCodexConfig({ outputDir: event.target.value })} />
                    <button type="button" onClick={chooseOutputDir}>Seç</button>
                  </div>
                </label>
              </section>

              <section className="workflow-card">
                <div className="workflow-card-head">
                  <span>03</span>
                  <div>
                    <strong>Yürütme ayarları</strong>
                    <small>Varsayılan otomatik seçimdir; gerekirse elle belirtin</small>
                  </div>
                </div>
                <div className="bridge-field wide">
                  <span>Hedef uygulama</span>
                  <div className="segmented-control software-control">
                    {(Object.keys(cadApplicationLabels) as Array<CodexConfig["cadApplication"]>).map((application) => (
                      <button
                        type="button"
                        className={codexConfig.cadApplication === application ? "active" : ""}
                        key={application}
                        onClick={() => updateCodexConfig({ cadApplication: application })}
                      >
                        {cadApplicationLabels[application]}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="execution-grid">
                  <div className="bridge-field">
                    <span>Üretim yöntemi</span>
                    <div className="segmented-control">
                      {(Object.keys(processLabels) as Array<CodexConfig["process"]>).map((process) => (
                        <button
                          type="button"
                          className={codexConfig.process === process ? "active" : ""}
                          key={process}
                          onClick={() => updateCodexConfig({ process })}
                        >
                          {processLabels[process]}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="bridge-field">
                    <span>Malzeme</span>
                    <div className="segmented-control">
                      {(Object.keys(materialLabels) as Array<CodexConfig["material"]>).map((material) => (
                        <button
                          type="button"
                          className={codexConfig.material === material ? "active" : ""}
                          key={material}
                          onClick={() => updateCodexConfig({ material })}
                        >
                          {materialLabels[material]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="bridge-field compact-inputs">
                  <span>Referans ölçüler</span>
                  <div className="number-grid">
                    {[
                      ["length", "Uzunluk"],
                      ["width", "Genişlik"],
                      ["height", "Yükseklik"],
                      ["wallThickness", "Duvar kalınlığı"],
                    ].map(([key, label]) => (
                      <label key={key}>
                        <em>{label}</em>
                        <input
                          type="number"
                          min="0"
                          step="0.1"
                          value={codexConfig[key as "length" | "width" | "height" | "wallThickness"]}
                          onChange={(event) => updateCodexConfig({ [key]: Number(event.target.value) } as Partial<CodexConfig>)}
                        />
                      </label>
                    ))}
                  </div>
                </div>

                <div className="bridge-toggles">
                  <button type="button" aria-pressed={codexConfig.realCutouts} className={codexConfig.realCutouts ? "toggle-pill active" : "toggle-pill"} onClick={() => updateCodexConfig({ realCutouts: !codexConfig.realCutouts })}>
                    Gerçek delik kesimi
                  </button>
                  <button type="button" aria-pressed={codexConfig.strictGbDrawing} className={codexConfig.strictGbDrawing ? "toggle-pill active" : "toggle-pill"} onClick={() => updateCodexConfig({ strictGbDrawing: !codexConfig.strictGbDrawing })}>
                    Sıkı çizim standardı
                  </button>
                  <button type="button" aria-pressed={codexConfig.localCadAutomation} className={codexConfig.localCadAutomation ? "toggle-pill active" : "toggle-pill"} onClick={() => updateCodexConfig({ localCadAutomation: !codexConfig.localCadAutomation })}>
                    Yerel CAD Otomasyon
                  </button>
                </div>
              </section>
            </div>

            <div className="bridge-runtime">
              <div className="runtime-line">
                <span>Executor</span>
                <strong>{agentProviderCatalog[apiConfig.agentProvider].name}</strong>
              </div>
              <div className="runtime-line">
                <span>Hedef uygulama</span>
                <strong>{cadApplicationLabels[codexConfig.cadApplication]}</strong>
              </div>
              <div className="runtime-line">
                <span>Skill</span>
                <strong>{codexConfig.cadApplication === "autocad" ? "autocad-automation" : codexConfig.cadApplication === "both" ? "SW + AutoCAD skills" : "solidworks-automation"}</strong>
              </div>
              <div className="runtime-line">
                <span>Yetkiler</span>
                <strong>{codexConfig.localCadAutomation ? "Onaydan sonra yerel CAD uygulamasını kontrol et" : "Yalnızca plan/betik oluştur"}</strong>
              </div>
              <div className="runtime-line">
                <span>Üretim girdileri</span>
                <strong>{`${processLabels[codexConfig.process]} · ${materialLabels[codexConfig.material]} · ${codexConfig.length}x${codexConfig.width}x${codexConfig.height}`}</strong>
              </div>
              <div className="runtime-line orchestration-line">
                <span>Mühendislik orkestrasyonu</span>
                <strong>AI Otomatik yönlendir · Aşama incelemesi</strong>
              </div>
              <div className="prompt-preview">
                <span>Yürütme planı önizlemesi</span>
                <p>{codexPrompt}</p>
              </div>
              <motion.button
                className="primary-button bridge-run shine"
                type="button"
                disabled={submissionKind !== null}
                aria-busy={submissionKind === "task"}
                onClick={enqueueCodexTask}
                whileHover={submissionKind || reducedMotion ? undefined : { y: -2 }}
                whileTap={submissionKind ? undefined : { scale: 0.975 }}
              >
                {submissionKind === "task" ? <SpinnerGap className="spin" size={18} /> : <Lightning size={18} weight="duotone" />}
                {submissionKind === "task" ? "Görev oluşturuluyor" : `${agentProviderCatalog[apiConfig.agentProvider].name} ile yürüt`}
              </motion.button>
              <motion.button
                className="ghost-button bridge-run"
                type="button"
                disabled={submissionKind !== null}
                aria-busy={submissionKind === "task"}
                onClick={() => void enqueueDfmReviewTask()}
                whileHover={submissionKind || reducedMotion ? undefined : { y: -2 }}
                whileTap={submissionKind ? undefined : { scale: 0.975 }}
              >
                {submissionKind === "task" ? <SpinnerGap className="spin" size={18} /> : <ShieldCheck size={18} weight="duotone" />}
                {submissionKind === "task" ? "DFM görevi oluşturuluyor" : "DFM kontrolünü çalıştır"}
              </motion.button>
            </div>
          </section>
          ) : null}

          <footer className="status-strip">
            <div className="desktop-statusbar" aria-live="polite">
              <span className={selectedProvider?.ready ? "ready" : "warning"}>{agentProviderCatalog[apiConfig.agentProvider].name} {selectedProvider?.ready ? "Bağlandı" : "Doğrulanmadı"}</span>
              <span>Worker {workerStatus.running ? `Çalışıyor · ${workerStatus.pid ?? "-"}` : "Başlatılmadı"}</span>
              <span>SolidWorks {runtimeHealth?.solidworks?.ok ? "Kullanılabilir" : "Kontrol bekliyor"}</span>
              <span>AutoCAD {runtimeHealth?.autocad?.ok ? "Kullanılabilir" : "Algılanmadı"}</span>
              <span>{queueLoaded ? queueSummary : "Kuyruk yükleniyor"}</span>
            </div>

            <section className="agent-console" aria-live="polite">
              <div className="agent-head">
                <div>
                  <p className="eyebrow">AI EXECUTION CHAT</p>
                  <h2>AI Yürütme konuşması</h2>
                </div>
                <ConversationControls
                  conversations={projectConversations}
                  activeConversationId={activeConversation?.id}
                  provider={apiConfig.agentProvider}
                  model={apiConfig.model}
                  providers={(Object.keys(agentProviderCatalog) as AgentProviderId[]).map((providerId) => ({
                    value: providerId,
                    label: `${agentProviderCatalog[providerId].company} · ${agentProviderCatalog[providerId].name}`,
                    disabled: runtimeHealth ? !runtimeHealth.agentProviders?.find((provider) => provider.id === providerId)?.installed : false,
                  }))}
                  models={providerModelOptions.map((model) => ({
                    value: model.value,
                    label: `${agentProviderCatalog[apiConfig.agentProvider].company} · ${model.label}`,
                  }))}
                  onSelectConversation={selectAgentConversation}
                  onCreateConversation={() => createAgentConversation()}
                  onSelectProvider={selectAgentProvider}
                  onSelectModel={selectAgentModel}
                />
                <span>{activeAgentJob ? `${jobStatusLabel(activeAgentJob.status)} · ${activeAgentJob.progress}%` : activeConversation ? "Talimat bekleniyor" : "Yeni konuşma oluşturarak başlayın"}</span>
              </div>

              <div className={activeAgentJob ? "agent-body" : "agent-body single"}>
                <div className="chat-thread" aria-label="AI Yürütme konuşma kaydı">
                  {activeConversationMessages.length === 0 ? (
                    <div className="chat-empty">
                      <ChatCircleText size={20} weight="duotone" />
                      <strong>{activeConversation ? "Bu konuşmada henüz mesaj yok" : "Yeni bağımsız konuşma oluşturarak başlayın"}</strong>
                    </div>
                  ) : activeConversationMessages.map((message) => (
                    <motion.div
                      className={`chat-bubble ${message.role}`}
                      key={message.id}
                      initial={reducedMotion ? false : { y: 8, opacity: 0 }}
                      animate={{ y: 0, opacity: 1 }}
                    >
                      <span>{message.role === "user" ? "Siz" : message.role === "system" ? "Sistem" : "CAD Agent"}</span>
                      <p>{message.content}</p>
                      <small>{formatTimeLabel(message.at)}</small>
                    </motion.div>
                  ))}
                </div>

                {activeAgentJob ? <div className="agent-live-panel">
                  <div className="live-head">
                    <ChatCircleText size={18} weight="duotone" />
                    <strong>{activeAgentJob ? jobDisplayTitle(activeAgentJob) : "İlk görev bekleniyor"}</strong>
                    <span>{activeAgentJob ? jobStatusLabel(activeAgentJob.status) : "Hazır"}</span>
                  </div>
                  <div className="live-progress">
                    <i style={{ width: `${activeAgentJob?.progress ?? 0}%` }} />
                  </div>
                  <div className="live-summary">
                    <p>{activeAgentJob ? compactJobMessage(activeAgentJob, activeAgentEvents) : "Gereksinimlerinizi girdikten sonra AI yürütme adımları, araç sonuçları ve çıktı dosyaları burada görünür."}</p>
                  </div>
                  {activeAgentJob.result?.engineeringPlan?.phases?.length ? (
                    <div className="engineering-plan-view">
                      <strong>AI Mühendislik yolu</strong>
                      <div>
                        {activeAgentJob.result.engineeringPlan.phases.map((phase, index) => (
                          <span className={phase.human_gate ? "human-gate" : ""} key={phase.id || `${phase.name}-${index}`}>
                            <i>{index + 1}</i>
                            {phase.name || phase.id}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {activeAgentJob?.status === "approval_required" ? (
                    <button className="approval-button" type="button" onClick={() => void approveJob(activeAgentJob.id)}>
                      Yerel yürütmeyi onayla
                    </button>
                  ) : null}
                  {activeAgentJob?.status === "review_required" ? (
                    <ManualReviewPanel
                      draft={activeManualReviewDraft}
                      options={activeManualReviewOptions}
                      onChange={(draft) => updateManualReviewDraft(activeAgentJob.id, draft)}
                      onSubmit={(approved) => void reviewJob(activeAgentJob.id, approved)}
                    />
                  ) : null}
                  <div className="live-timeline">
                    {activeAgentEvents.length === 0 ? (
                      <div className="timeline-empty">Görev başladıktan sonra görevin alınması, onay, AI başlangıcı, inceleme, çıktı yolları ve hatalar burada gösterilir.</div>
                    ) : (
                      activeAgentEvents.slice(-6).map((event, index) => (
                        <div className="timeline-item" key={`${event.at}-${event.type}-${index}`}>
                          <span>{eventTypeLabel(event.type)}</span>
                          <p>{event.message || "Durum güncellendi"}</p>
                          <small>{formatTimeLabel(event.at)}</small>
                        </div>
                      ))
                    )}
                  </div>
                  {(activeAgentLogs.stdout || activeAgentLogs.stderr) && (
                    <div className="agent-log-preview">
                      <strong>AI Çıktı</strong>
                      {activeAgentLogs.stdout ? <pre>{activeAgentLogs.stdout}</pre> : null}
                      {activeAgentLogs.stderr ? <pre className="error-log">{activeAgentLogs.stderr}</pre> : null}
                    </div>
                  )}
                </div> : null}
              </div>

              <div className="agent-input-row">
                <textarea
                  value={agentInput}
                  onChange={(event) => setAgentInput(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") void submitAgentMessage();
                  }}
                  placeholder="Örnek: bu muhafazanın USB açıklığını 1 mm büyüt; STL ve GB/T PDF çizimini yeniden dışa aktar"
                />
                <button type="button" disabled={submissionKind !== null} aria-busy={submissionKind === "chat"} onClick={() => void submitAgentMessage()}>
                  {submissionKind === "chat" ? <SpinnerGap className="spin" size={18} /> : <PaperPlaneTilt size={18} weight="fill" />}
                  {submissionKind === "chat" ? "Gönderiliyor" : "Gönder ve yürüt"}
                </button>
              </div>
            </section>

            <section className="queue-panel">
              <div className="queue-head">
                <div>
                  <p className="eyebrow">AUTOMATION QUEUE</p>
                  <h2>Yerel görev izleyici</h2>
                </div>
                <div className="queue-actions">
                  <span className={workerStatus.running ? "worker-pill running" : "worker-pill"}>
                    {workerLabel}
                  </span>
                  {workerStatus.running ? (
                    <button type="button" disabled={workerAction !== null} onClick={() => void restartLocalWorker()} title="Yerel yürütücüyü durdurup yeniden başlatın">
                      <ArrowClockwise className={workerAction === "restart" ? "spin" : undefined} size={15} weight="bold" />
                      {workerAction === "restart" ? "Yeniden başlatılıyor" : "Yürütücüyü yeniden başlat"}
                    </button>
                  ) : null}
                  <button type="button" disabled={workerAction !== null} onClick={() => void (workerStatus.running ? stopLocalWorker() : startLocalWorker())}>
                    {workerAction === "start" ? "Başlatılıyor" : workerAction === "stop" ? "Durduruluyor" : workerStatus.running ? "Durdur" : "Başlat"}
                  </button>
                  <span>{queueLoaded ? queueSummary : "Yükleniyor"}</span>
                </div>
              </div>
              {queueLoadError ? <div className="queue-error" role="alert">{queueLoadError}</div> : null}
              <div className="queue-list">
                {activeProjectJobs.length === 0 ? (
                  <div className="queue-empty">
                    <Sparkle size={19} weight="duotone" />
                    <span>AI konuşması veya görev şablonu üzerinden başlatılan görevler burada görünür.</span>
                  </div>
                ) : (
                  activeProjectJobs.slice(0, 4).map((job) => {
                    const expanded = expandedJobId === job.id;
                    const events = jobEvents[job.id] ?? [];
                    const logs = jobLogTails[job.id] ?? {};
                    const workerLogs = (job.workerLog ?? []).slice(-5);
                    return (
                      <motion.article className={`queue-job ${job.status} ${expanded ? "expanded" : ""}`} key={job.id} layout>
                        <div className="job-main">
                          <div>
                            <strong>{jobDisplayTitle(job)}</strong>
                            <small>{compactJobMessage(job, events)}</small>
                          </div>
                          <span>{jobStatusLabel(job.status)}</span>
                        </div>
                        <div className="job-progress" aria-label={`${jobDisplayTitle(job)} İlerleme ${job.progress}%`}>
                          <i style={{ width: `${job.progress}%` }} />
                        </div>
                        <div className="job-controls">
                          <button className="expand-button" type="button" onClick={() => setExpandedJobId(expanded ? null : job.id)}>
                            <CaretDown size={15} weight="bold" />
                            {expanded ? "Adımları daralt" : "Adımları görüntüle"}
                          </button>
                          {job.uiConfig?.agentChat === true ? (
                            <button type="button" onClick={() => setActiveAgentJobId(job.id)}>
                              Konuşmayı izle
                            </button>
                          ) : null}
                          {job.status === "approval_required" ? (
                            <button type="button" onClick={() => void approveJob(job.id)}>
                              Onayla
                            </button>
                          ) : null}
                          {job.status === "review_required" ? (
                            <button type="button" onClick={() => {
                              setActiveAgentJobId(job.id);
                              setExpandedJobId(job.id);
                            }}>
                              İnceleme yaz
                            </button>
                          ) : null}
                          {job.status === "failed" ? (
                            <button type="button" disabled={retryingJobId !== null} onClick={() => void retryJob(job.id)}>
                              <ArrowClockwise className={retryingJobId === job.id ? "spin" : undefined} size={15} weight="bold" />
                              {retryingJobId === job.id ? "Yeniden sıraya alınıyor" : "Yeniden yürüt"}
                            </button>
                          ) : null}
                          {job.status === "queued" || job.status === "running" || job.status === "approval_required" ? (
                            <button type="button" onClick={() => void cancelJob(job.id)}>
                              İptal
                            </button>
                          ) : null}
                        </div>
                        <AnimatePresence>
                          {expanded ? (
                            <motion.div
                              className="job-process"
                              initial={reducedMotion ? false : { height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={reducedMotion ? undefined : { height: 0, opacity: 0 }}
                            >
                              <div className="process-grid">
                                <div>
                                  <span>Mevcut görev</span>
                                  <strong>{job.detail}</strong>
                                </div>
                                <div>
                                  <span>Yürütme uygulaması</span>
                                  <strong>{job.targetSoftware || "AI otomatik belirlesin"}</strong>
                                </div>
                                <div>
                                  <span>Son heartbeat</span>
                                  <strong>{formatTimeLabel(job.heartbeatAt || workerStatus.health?.heartbeatAt)}</strong>
                                </div>
                                <div>
                                  <span>Worker</span>
                                  <strong>{job.workerPid ? `PID ${job.workerPid}` : workerLabel}</strong>
                                </div>
                              </div>

                              {job.approvalReasons?.length ? (
                                <div className="process-note warning">
                                  <strong>Onay gerekiyor</strong>
                                  <p>{job.approvalReasons.join("; ")}</p>
                                </div>
                              ) : null}
                              {job.error ? (
                                <div className="process-note error">
                                  <strong>Hata</strong>
                                  <p>{job.error}</p>
                                </div>
                              ) : null}
                              {job.result?.outputPath || job.artifactLedgerPath || job.reviewGatePath ? (
                                <div className="process-paths">
                                  {job.result?.outputPath ? <span>Çıktı: {job.result.outputPath}</span> : null}
                                  {job.artifactLedgerPath ? <span>Çıktı kayıt defteri: {job.artifactLedgerPath}</span> : null}
                                  {job.reviewGatePath ? <span>İnceleme kaydı: {job.reviewGatePath}</span> : null}
                                </div>
                              ) : null}

                              <div className="process-columns">
                                <div className="process-timeline">
                                  <strong>Yürütme adımları</strong>
                                  {(events.length ? events : [{ message: job.lastMessage || "Worker'ın görevi alması bekleniyor", at: job.updatedAt, type: job.status }]).slice(-8).map((event, index) => (
                                    <div className="timeline-item" key={`${event.at}-${event.type}-${index}`}>
                                      <span>{eventTypeLabel(event.type)}</span>
                                      <p>{event.message || "Durum güncellendi"}</p>
                                      <small>{formatTimeLabel(event.at)}</small>
                                    </div>
                                  ))}
                                </div>
                                <div className="process-timeline">
                                  <strong>Worker Günlük</strong>
                                  {(workerLogs.length ? workerLogs : [{ message: "Henüz worker günlüğü yok; görev başladığında otomatik yenilenir.", at: job.updatedAt }]).map((entry, index) => (
                                    <div className="timeline-item" key={`${workerLogTime(entry)}-${index}`}>
                                      <span>{formatTimeLabel(workerLogTime(entry))}</span>
                                      <p>{workerLogMessage(entry)}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                              {(logs.stdout || logs.stderr) && (
                                <div className="agent-log-preview full">
                                  <strong>Agent Çıktı sonu</strong>
                                  {logs.stdout ? <pre>{logs.stdout}</pre> : null}
                                  {logs.stderr ? <pre className="error-log">{logs.stderr}</pre> : null}
                                </div>
                              )}
                            </motion.div>
                          ) : null}
                        </AnimatePresence>
                      </motion.article>
                    );
                  })
                )}
              </div>
            </section>

          </footer>
            </>
          ) : null}
        </section>
      </motion.section>
    </main>
  );
}

export default App;
