# SentinelOps — *CausalNexus*

> **Açıklanabilir Log Analizi & Otonom İyileştirme Platformu**
> *Explainable Log Analysis & Autonomous Self-Healing — KVKK / BDDK uyumlu, %100 yerel (on-premise) AIOps.*

SentinelOps, bankacılık sınıfı sistemlerin loglarını tıpkı bir dil gibi **okuyan**, sistem
çökmeden milisaniyeler içinde anomaliyi yakalayan, hatanın **kök nedenini** kurumun kendi
dokümanlarıyla açıklayan ve gerektiğinde **kendi kendini iyileştiren** (otonom rollback /
restart / scale) bir yapay zeka platformudur. Hiçbir veri kurum dışına — OpenAI, Anthropic
gibi bulut API'lerine — **çıkmaz**.

---

## İçindekiler

1. [Giriş & Vizyon: "Yetişkinler İçin" SentinelOps](#1-giriş--vizyon-yetişkinler-için-sentinelops)
2. [Sistem Mimarisi: Su Arıtma Tesisi Metaforu](#2-sistem-mimarisi-su-arıtma-tesisi-metaforu)
3. [Derin Teknik ve Matematiksel Altyapı](#3-derin-teknik-ve-matematiksel-altyapı)
4. [Mevzuat ve Güvenlik Güvencesi (BDDK & KVKK)](#4-mevzuat-ve-güvenlik-güvencesi-bddk--kvkk)
5. [Adım Adım Kurulum ve Kullanım Rehberi](#5-adım-adım-kurulum-ve-kullanım-rehberi)
6. [Eğitici Sıkça Sorulan Sorular (FAQ)](#6-eğitici-sıkça-sorulan-sorular-faq)
7. [Proje Düzeni (Repo Haritası)](#7-proje-düzeni-repo-haritası)

---

## 1. Giriş & Vizyon: "Yetişkinler İçin" SentinelOps

### Bir saniyenin milyonlarca dolarlık bedeli

Bir bankanın ödeme sunucularını, durmaksızın akan bir nehir gibi düşünün. Bu nehirde her
saniye binlerce işlem akar: kart provizyonu, IBAN'a havale, kredi limiti sorgusu. Bu akış
bir **saniye** dahi dursa sonuçlar yıkıcıdır:

- **Doğrudan finansal kayıp:** Saniyede gerçekleşemeyen on binlerce işlem, anında ciroya
  yansır. Büyük bir ödeme ağında bir dakikalık kesinti, kelimenin tam anlamıyla milyonlarca
  dolarlık işlem hacminin buharlaşması demektir.
- **Yasal ve regülatif ceza:** BDDK'nın bilgi sistemlerinin sürekliliğine dair beklentileri
  bağlayıcıdır. Tekrar eden kesintiler idari para cezalarına ve denetim baskısına yol açar.
- **İtibar erozyonu:** "Bankamın uygulaması yine çöktü" algısı, parayla geri alınamaz.

Bu yüzden modern bankacılıkta amaç sadece "hatayı görmek" değil, **hata olmadan önce onu
sezmek ve otonom olarak engellemektir.**

### Geleneksel çözümlerin kusuru — "Alarm Fırtınası" körlüğü

Klasik log izleme araçları (Splunk, ELK / Elastic Stack, Grafana Loki) son derece değerlidir,
ama yapıları gereği üç temel kusura sahiptir:

| Geleneksel araç | Ne yapar? | Kusuru |
| --- | --- | --- |
| **Splunk / ELK** | Belirli kelimeleri (`ERROR`, `OOM`) görünce alarm üretir | Hata **olduktan sonra** çalar. Reaktiftir, proaktif değil. |
| **Statik eşik alarmları** | "CPU %90'ı geçti" der | Aynı anda yüzlerce alarm üreterek bir **alarm fırtınası** (alert storm) yaratır. Mühendis önemli sinyali gürültü içinde kaybeder. |
| **Dashboard'lar** | Grafik çizer | Size *neyin* bozulduğunu gösterir ama *neden* bozulduğunu **asla söyleyemez.** |

Bunu şöyle bir metaforla düşünün: Geleneksel araçlar, evinizde **yangın çıktıktan sonra**
öten bir duman dedektörüdür. Üstelik komşunun mangalında et pişerken de öterler (yanlış
alarm) ve siz koşup geldiğinizde size sadece "duman var" derler — mutfakta mı, salonda mı,
sebebi yağ mı elektrik mi, bilemezler.

### SentinelOps farkı — Logu *dil* gibi okumak

SentinelOps, logları bir kelime dizisi olarak değil, **bir cümle** olarak okur. Tıpkı bir
dil modelinin "Bugün hava çok..." cümlesinden sonra "güzel" kelimesini beklemesi gibi,
SentinelOps `REQ_RECEIVED → AUTH_OK → LEDGER_OK → RESP_SENT` (yani sağlıklı bir işlem
cümlesi) görmeye alışkındır. Bu akış aniden `MEM_PRESSURE → OOM_KILL → PROBE_FAIL →
CRASHLOOP` şeklinde "gramer dışı" bir cümleye döndüğünde, modelin "şaşkınlığı" (risk skoru)
tavan yapar.

Sonuç olarak SentinelOps:

- **Henüz sistem çökmeden** (`MEM_PRESSURE` aşamasında, daha `OOM` gelmeden) tehlikeyi sezer.
- Anomaliyi yakaladığında, kurumun **kendi olay tarihçesini ve mimari dokümanlarını** okuyarak
  *"Bu, INC-2026-0042'de görülen sınırsız ledger cache kaynaklı heap taşmasıdır"* gibi
  **insan dilinde bir kök neden** üretir.
- Bu kök nedene karşılık gelen **onaylı runbook** komutunu (`kubectl rollout undo ...`) otonom
  olarak tetikler — sistem **kendi kendini iyileştirir** (self-healing).
- Attığı her adımı, sonradan değiştirilemeyen, **kriptografik olarak zincirlenmiş** bir
  denetim defterine (immutable audit trail) yazar.

---

## 2. Sistem Mimarisi: Su Arıtma Tesisi Metaforu

Ham log verisini, bir şehir su şebekesine giren **çamurlu, ham nehir suyuna** benzetelim. Bu
su (içilebilir = güvenli, eyleme dönüştürülebilir bilgi) haline gelene kadar **dört arıtma
filtresinden** geçer. Her filtre suyun bir miktarını "temiz" ilan edip yan kanala alır,
yalnızca şüpheli kalanı bir sonraki, daha pahalı filtreye gönderir.

```
            HAM LOG AKIŞI  (çamurlu nehir suyu)
            data/sample_bgl.log  →  MessageBus (Kafka/Redis simülasyonu)
                          │
                          ▼
   ╔══════════════════════════════════════════════════════════╗
   ║  FİLTRE 1 — ANONYMIZER  (Kaba Izgara / PII Tortu Tutucu)  ║
   ║  src/anonymizer/mask.py                                    ║
   ║  IP→IP_ee8a1713 · card→[CARD] · iban→[IBAN] · @→[EMAIL]    ║
   ║  Zaman damgaları ASLA değiştirilmez.                       ║
   ╚══════════════════════════════════════════════════════════╝
                          │  (kişisel veriden arındırılmış log)
                          ▼
   ╔══════════════════════════════════════════════════════════╗
   ║  FİLTRE 2 — CausalConvLSTM  (Hızlı Membran / AI Süzgeci)  ║
   ║  src/models/causal_lstm.py                                 ║
   ║  Her loga risk skoru ∈ [0,1] verir.  (~milisaniye)         ║
   ╚══════════════════════════════════════════════════════════╝
                          │
              ┌───────────┴────────────┐
       score < 0.35                score ≥ 0.35
       (TEMİZ SU)                   (ŞÜPHELİ)
              │                          │
              ▼                          ▼
        "Safe (Normal)"   ╔══════════════════════════════════════╗
        LLM'e GİTMEZ      ║  FİLTRE 3 — EnrichLog RAG            ║
        (< 10 ms)         ║  (Bilge Kütüphaneci + Yerel LLM)     ║
                          ║  src/rag/enrich_log.py               ║
                          ║  cosine-similarity → top-k doküman → ║
                          ║  prompt → yerel LLM → RCA + JSON aksiyon║
                          ╚══════════════════════════════════════╝
                                       │
                                       ▼
                          ╔══════════════════════════════════════╗
                          ║  FİLTRE 4 — Healing & Audit          ║
                          ║  src/orchestrator/healing.py + audit.py║
                          ║  ROLLBACK / RESTART / SCALE (mock K8s) ║
                          ║  → SHA-256 hash-zincirli SQLite defter ║
                          ╚══════════════════════════════════════╝
                                       │
                                       ▼
                          OTONOM MÜDAHALE  +  DEĞİŞTİRİLEMEZ KAYIT
```

### Filtre 1 — Anonymizer (Kaba ızgara: PII tortu tutucu)

Nehir suyu tesise girer girmez kaba bir ızgaradan geçer; dallar, çöpler, taşlar burada
tutulur. SentinelOps'ta bu ızgaranın tuttuğu "tortu" **kişisel veridir**: IP adresleri,
kredi kartı numaraları, IBAN'lar, e-postalar, UUID'ler. [src/anonymizer/mask.py](src/anonymizer/mask.py)
bunları, log bir milimetre dahi ilerlemeden — yani *henüz hiçbir AI veya LLM görmeden* —
güvenli jetonlara dönüştürür. IP adresleri ise silinmez; **deterministik takma adlara**
(`IP_ee8a1713`) çevrilir (nedenini [Filtre 4](#filtre-4--otonom-healing--immutable-audit)
ve [FAQ](#6-eğitici-sıkça-sorulan-sorular-faq) bölümlerinde açıklıyoruz).

### Filtre 2 — CausalConvLSTM (Hızlı membran: AI süzgeci)

Izgaradan geçen su, çok ince gözenekli ve **çok hızlı** bir membrana çarpar. Bu membran her
log satırına saniyenin binde biri mertebesinde bir **risk skoru** $\in[0,1]$ atar. Normal
trafik (`REQ_RECEIVED`, `AUTH_OK`) neredeyse sürtünmesiz geçer (skor $\approx 0.000$);
"gramer bozukluğu" taşıyan loglar membranda takılır (skor $\approx 0.999$). Bu katman
[src/models/causal_lstm.py](src/models/causal_lstm.py) dosyasındaki nöral ağdır ve
matematiği [Bölüm 3](#3-derin-teknik-ve-matematiksel-altyapı)'te detaylandırılmıştır.

### Filtre 3 — EnrichLog RAG (Bilge kütüphaneci)

Membranda takılan şüpheli su, artık daha pahalı bir kimyasal analiz aşamasına girer. Burayı
şöyle düşünün: Elinizde anlamadığınız bir hata kodu var ve **kütüphanedeki en bilge
asistana** gidiyorsunuz. Bu asistan (RAG = *Retrieval-Augmented Generation*) rastgele
konuşmaz; önce raflara gider, sizin hatanıza **en çok benzeyen** geçmiş olay raporlarını ve
mimari dokümanları (`data/error_corpus/`, `data/system_docs/`) bulur (in-memory cosine
similarity), sonra bu kanıtları masaya koyarak yerel LLM'e *"Bu kanıtlara dayanarak kök neden
nedir?"* diye sorar. Kanıt yoksa asistan **uydurmaz**, açıkça "bilmiyorum" der. Bu katman
[src/rag/enrich_log.py](src/rag/enrich_log.py)'dedir.

### Filtre 4 — Otonom Healing & Immutable Audit

Analiz biten suyun arıtma sonucu artık nettir. Tesisin son aşaması iki iş yapar:

1. **İyileştirme ([src/orchestrator/healing.py](src/orchestrator/healing.py)):** LLM'in
   ürettiği yapısal JSON aksiyonunu (`{"action": "ROLLBACK", "target": "payment-v2"}`) alıp
   ilgili Kubernetes komutuna çevirir ve tetikler (`kubectl rollout undo deployment/payment-v2`).
   Demo'da bu komutlar **mock** edilmiştir — yani niyeti kaydeder ama gerçek bir kümeye
   dokunmaz; arayüz gerçek Docker SDK / K8s API'sini birebir taklit eder.
2. **Değiştirilemez kayıt ([src/orchestrator/audit.py](src/orchestrator/audit.py)):** Atılan
   her adım (hatta *reddedilen* adımlar bile) bir SQLite defterine, her satırın bir önceki
   satırın SHA-256 hash'iyle zincirlendiği bir blok-zinciri mantığıyla yazılır. Tek bir
   geçmiş kaydı kurcalamak tüm zinciri kırar ve `verify_chain()` ile anında yakalanır.

---

## 3. Derin Teknik ve Matematiksel Altyapı

### 3.1 CausalConvLSTM — Neden ve nasıl?

#### Sorun: Saf LSTM yavaştır, saf CNN bağlamı kaybeder

LSTM (*Long Short-Term Memory*) zamansal bağımlılıkları yakalamada güçlüdür, ancak yapısı
gereği **ardışıldır (sequential)**: $t$ anındaki gizli durum $h_t$, ancak $h_{t-1}$
hesaplandıktan sonra hesaplanabilir. Bu, uzun dizilerde GPU paralelizmini öldürür ve gecikme
yaratır. Saf bir 1D-CNN ise paraleldir ve hızlıdır, ama tek başına uzun menzilli zamansal
sıralama bilgisini LSTM kadar zarif tutmaz.

**Çözüm — hibrit mimari:** Önce hızlı, paralel ve **nedensel** bir 1D evrişim katmanı yerel
log-anahtar örüntülerini (örn. `MEM_PRESSURE` hemen ardından `OOM_KILL`) sıkıştırılmış
özniteliklere indirger; ardından sığ bir LSTM bu öznitelikler üzerinde küresel zamansal
bağlamı toplar. Mimarinin tam akışı [src/models/causal_lstm.py:95](src/models/causal_lstm.py#L95):

```
x (B, L)  →  Embedding (B, L, E)  →  transpose (B, E, L)
          →  CausalConv1d + ReLU (B, C, L)  →  transpose (B, L, C)
          →  LSTM → son gizli durum (B, H)
          →  Dropout → Linear (B, 1)  →  sigmoid  →  risk ∈ [0,1]
```

#### Zamansal sızıntı (temporal leakage) ve nedensel padding

Bir anomali dedektörünün **geleceğe bakması yasaktır**. $t$ anındaki bir logun riskini
hesaplarken $t+1, t+2, \dots$ loglarına bakmak, henüz olmamış bilgiyi kullanmak demektir;
buna **zamansal sızıntı** denir ve modeli üretimde işe yaramaz, hatta tehlikeli kılar.

Standart bir evrişim çekirdeği simetriktir: hem geçmişe hem geleceğe bakar. Nedensellği
korumak için girdiyi **yalnızca soldan (geçmiş yönünde)** doldururuz (left-padding) ve sağda
oluşan fazlalığı keseriz. Sol dolgu miktarı şu formülle belirlenir:

$$P=(k-1)\times d$$

Burada $P$ uygulanacak dolgu (padding) miktarı, $k$ çekirdek boyutu (kernel size), $d$ ise
genişletme (dilation) oranıdır. Varsayılan yapılandırmamızda ($k=3$, $d=1$) bu $P=(3-1)\times1=2$
verir.

> **Uygulama notu (CLAUDE.md kuralı):** Bu dolgu, bellek kopyalayan `F.pad` ile **değil**,
> `nn.Conv1d`'nin `padding` argümanıyla yapılır; ardından nedenselliği zorlamak için sondaki
> dolgu programatik olarak dilimlenip atılır:
> ```python
> x = self.conv(x)          # nn.Conv1d(..., padding=(k-1)*d, dilation=d)
> x = x[:, :, :-self.padding_size]   # geleceğe sızan sağ dolguyu kes
> ```
> Böylece çıktı pozisyonu `output[t]` yalnızca `input[≤ t]` girdilerine bağlı kalır. Bu
> davranış [tests/test_causal_lstm.py](tests/test_causal_lstm.py) içindeki
> `test_convolution_is_causal` ve `test_causal_conv_padding_formula` testleriyle doğrulanır.

#### Eğitim kayıp fonksiyonu — $L_2$ düzenlileştirilmiş BCE

Model, ikili (normal=0 / anomali=1) bir sınıflandırma problemi olarak, ağırlık çürümesi
(*weight decay*) ile $L_2$ düzenlileştirilmiş **İkili Çapraz Entropi** (Binary Cross-Entropy)
kaybını minimize eder:

$$\mathcal{L}(\Theta)=-\frac{1}{N}\sum_{i=1}^{N}\left[y_i\log(\hat{y}_i)+(1-y_i)\log(1-\hat{y}_i)\right]+\frac{\lambda}{2}\sum_{j=1}^{K}\theta_j^2$$

Terimleri okuyalım:

- $N$: minibatch'teki örnek sayısı; $y_i\in\{0,1\}$: gerçek etiket; $\hat{y}_i\in(0,1)$:
  modelin tahmin ettiği risk skoru (sigmoid çıktısı).
- İlk terim (BCE) tahmini gerçeğe yaklaştırır: $y_i=1$ iken $\hat{y}_i\to1$, $y_i=0$ iken
  $\hat{y}_i\to0$ olmaya zorlar.
- İkinci terim ($\frac{\lambda}{2}\sum_j\theta_j^2$) ağırlıkların ($\theta_j$) büyümesini
  cezalandırır; aşırı öğrenmeyi (overfitting) bastırır. $\lambda$ düzenlileştirme katsayısıdır
  (`config.yaml → training.l2_lambda = 1e-4`).

> **Sayısal kararlılık notu:** $L_2$ terimi, PyTorch'ta en kararlı yol olan Adam
> optimizatörünün `weight_decay` parametresiyle gerçeklenir; yani `weight_decay = λ`. Bkz.
> [src/models/train.py:87](src/models/train.py#L87). `test_training_loop_reduces_loss` ve
> `test_separates_normal_from_anomaly_after_training` testleri kaybın düştüğünü ve modelin
> normal ile anomaliyi ayırdığını kanıtlar.

Girdi temsili kısaca: her log satırından `key=...` log-anahtarı çıkarılır, $w=10$ uzunluğunda
kayan pencereler $X=\langle k_{t-w},\dots,k_{t-1}\rangle$ kurulur, eksik pencereler `<UNK>`
ile soldan doldurulur ve anahtarlar deterministik bir sözlükle ($\texttt{vocab.json}$)
tamsayıya çevrilir — bu sözlük, eğitim ile çıkarımın aynı indislere bakması için ağırlıklarla
birlikte saklanır.

### 3.2 EnrichLog İki Aşamalı Çıkarım (Two-Step Inference)

LLM çağrıları yavaş ve pahalıdır. Her log için bir LLM çağrısı yapmak, her ziyaretçiye genel
müdürün özel danışmanlığını sunmak gibidir — hem gereksiz hem ölçeklenemez. Bu yüzden çıkarım
**iki aşamalıdır** ([src/rag/enrich_log.py:85](src/rag/enrich_log.py#L85)).

#### Aşama 1 — Hafif eşik kontrolü (kapıdaki güvenlik görevlisi)

İlk aşama bilinçli olarak **önemsizdir**: sadece bir `if` karşılaştırması.

$$\text{risk score}<0.35\;\Longrightarrow\;\text{verdict}=\text{SAFE},\quad\text{LLM çağrısı YOK}$$

Eşiğin altındaki "normal" loglar burada erken elenir ve LLM/RAG yoluna hiç girmez. Bu,
toplam yükün büyük çoğunluğunu oluşturan sağlıklı trafiği, ağır makineyi çalıştırmadan
saf dışı bırakır; gecikmeyi log başına **$10\text{ ms}$ altında** tutar (CPU üzerinde dahi).
Eşik [config/config.yaml](config/config.yaml)'da `inference.risk_threshold` ile ayarlanır.
`test_stage1_latency_under_10ms` bu bütçeyi test eder.

#### Aşama 2 — Bilgi füzyonlu RAG (kütüphaneci devreye girer)

Eşik aşıldığında ağır makine uyanır:

1. **Vektör arama:** PII-maskelenmiş log, [src/rag/embeddings.py](src/rag/embeddings.py)
   ile gömülür ve in-memory `VectorStore` ([src/rag/vector_store.py](src/rag/vector_store.py))
   üzerinde **kosinüs benzerliği** ile sıralanır. Vektörler birim normlu olduğundan kosinüs
   benzerliği basit bir iç çarpıma indirgenir: $\text{sim}(q,d)=q\cdot d$. En benzer `top_k`
   (varsayılan 3) doküman çekilir.
2. **Bilgi füzyonu:** Çekilen geçmiş olay kayıtları (`error_corpus`) ve mimari dokümanlar
   (`system_docs`) bir prompt'a **kanıt blokları** olarak gömülür.
3. **Yerel LLM çıkarımı:** Bu zenginleştirilmiş prompt, yerel LLM'e
   ([src/rag/llm_client.py](src/rag/llm_client.py)) gönderilir; LLM tek bir JSON nesnesiyle
   **kök neden (RCA) + yapısal aksiyon** döndürür.

> **Sıfır halüsinasyon güvencesi:** Sistem prompt'u LLM'e şu katı kuralı dayatır — çekilen
> bağlamda logla net eşleşen bir referans **yoksa**, LLM bir çözüm **uydurmaz**; tam olarak
> `{"action": "UNKNOWN", "reason": "Kök neden bilinmiyor"}` döndürür. `test_zero_hallucination_without_matching_context`
> bunu doğrular.

### 3.3 Kriptografik Denetim Zinciri (Immutable Audit Trail)

Bankacılık denetiminin altın kuralı: **geçmiş değiştirilemez olmalı.** SentinelOps bunu, bir
blok zincirinin (blockchain) çalışma mantığını küçük bir SQLite tablosuna taşıyarak sağlar
([src/orchestrator/audit.py](src/orchestrator/audit.py)).

Her yeni denetim kaydı, içeriğinin yanı sıra **bir önceki kaydın hash'ini** (`prev_hash`) de
saklar. Kaydın kendi parmak izi şöyle hesaplanır:

$$h_n=\text{SHA-256}\bigl(\text{seq}\,\Vert\,\text{ts}\,\Vert\,\text{log}\,\Vert\,\text{score}\,\Vert\,\text{verdict}\,\Vert\,\text{action}\,\Vert\,h_{n-1}\bigr)$$

İlk kaydın referans aldığı genesis hash $h_0=\underbrace{00\dots0}_{64}$ şeklindedir. Bu yapı
kayıtları bir **kopmaz zincire** dönüştürür:

```
[Kayıt 1]            [Kayıt 2]            [Kayıt 3]
prev_hash = 000..0   prev_hash = h₁       prev_hash = h₂
record_hash = h₁  →  record_hash = h₂  →  record_hash = h₃
```

Bir saldırgan geçmiş bir kaydı (örn. otonom rollback'in kanıtını) silmek veya değiştirmek
isterse, o kaydın `record_hash`'i değişir; bu da bir **sonraki** kaydın `prev_hash`'iyle
artık uyuşmaz ve zincir kopar. `verify_chain()`, genesis'ten başlayıp her kaydın hash'ini
yeniden hesaplayarak bu tutarlılığı uçtan uca doğrular ve tek bir bit oynamasını dahi
yakalar. Tablo **yalnızca-ekleme** (append-only) tasarlanmıştır — `update` veya `delete`
metodu sunmaz — ve tüm SQL **parametreli sorgu** kullanır (SQL enjeksiyonuna karşı). Bkz.
`test_audit_chain_detects_tampering`.

---

## 4. Mevzuat ve Güvenlik Güvencesi (BDDK & KVKK)

SentinelOps, bankacılık uyumluluğunu sonradan eklenmiş bir kontrol listesi olarak değil,
mimarinin çekirdeğine işlenmiş bir tasarım ilkesi olarak ele alır.

### 4.1 KVKK / GDPR Uyumu — Veriyi minimize et, geri döndürülemez kıl

**6698 sayılı KVKK** ve onun bankacılık özelindeki iyi uygulama rehberleri, kişisel verilerin
test, analiz ve geliştirme ortamlarında **açık (clear-text) olarak kullanılmasını**
sınırlandırır; veri minimizasyonu ve maskeleme bekler. SentinelOps bu beklentiyi şöyle
karşılar:

- **Kaynakta maskeleme:** Hiçbir ham IP, IBAN, kart numarası, e-posta veya müşteri kimliği
  herhangi bir AI/LLM bileşenine ulaşmadan, [src/anonymizer/mask.py](src/anonymizer/mask.py)
  tarafından sınırda maskelenir. Kart numaraları ayrıca **Luhn** doğrulamasından geçirilerek
  yanlış pozitif maskeleme (örn. sıradan bir sipariş numarasını kart sanmak) engellenir.
- **Geri döndürülemez ama deterministik takma adlandırma (pseudonymization):** IP adresleri
  **tuzlanmış (salted) SHA-256** ile `IP_ee8a1713` gibi takma adlara çevrilir. Bu işlem tek
  yönlüdür — takma addan orijinal IP'ye dönüş matematiksel olarak olanaksızdır — ama
  *deterministiktir*: aynı IP daima aynı takma adı alır. Böylece "aynı kaynaktan gelen ardışık
  saldırı" gibi zamansal korelasyonlar kaybolmadan korunur (gerekçe için
  [FAQ'daki ilgili soru](#ip-adreslerini-hashlemek-yerine-neden-tamamen-silmiyoruz)).
- **Zaman bütünlüğü:** Zaman damgaları **asla** değiştirilmez. Milisaniye düzeyindeki olaylar
  arası farklar bot/brute-force tespiti için kritiktir; anonimleştirme bu sinyali bozmaz.

### 4.2 BDDK Bilgi Sistemleri Yönetmeliği Uyumu — Veri sınırı kurumu terk etmez

BDDK'nın bilgi sistemlerine ve **sır niteliğindeki bilgilerin paylaşılmasına** dair
düzenlemeleri, müşteri ve işlem sırrının kontrolsüz biçimde kurum dışına — özellikle
sınır ötesi bulut hizmetlerine — aktarılmasını sıkı koşullara bağlar. SentinelOps bu riski
**mimari olarak ortadan kaldırır**:

- **Sıfır dış API çağrısı:** Tüm RAG ve LLM çıkarımı, OpenAI / Anthropic gibi dış bulut
  sağlayıcılarına **dokunmadan**, tamamen yerel bir OpenAI-uyumlu `/v1/chat/completions`
  uç noktası üzerinden yürür. Bu uç nokta ya yerleşik **mock** sunucudur
  ([src/rag/mock_llm.py](src/rag/mock_llm.py)) ya da kurum içi (on-premise / private cloud)
  bir **Ollama / vLLM** örneğidir. Yapılandırma [config/config.yaml](config/config.yaml)'da
  `llm.mode = mock | ollama` ile yönetilir; istemci hiçbir koşulda harici bir hosta gitmez
  ([src/rag/llm_client.py](src/rag/llm_client.py)).
- **Yerel gömme (embedding):** Vektör araması varsayılan olarak ağ gerektirmeyen, deterministik
  bir **hashing embedder** ile çalışır; isteğe bağlı `real` modunda yerel olarak indirilmiş
  bir HuggingFace `bge-large-en` modeli kullanılır — yine kurum dışına veri gitmez.
- **Denetlenebilirlik:** [Bölüm 3.3](#33-kriptografik-denetim-zinciri-immutable-audit-trail)'teki
  hash-zincirli denetim defteri, BDDK denetçilerine sistemin attığı her otonom adımın
  değiştirilemez, doğrulanabilir bir kaydını sunar.

---

## 5. Adım Adım Kurulum ve Kullanım Rehberi

### 5.1 Ortamı kurma — neden sistem Python'ına dokunmuyoruz?

Bağımlılıkları (özellikle PyTorch'u) doğrudan sistem Python'ınıza kurmak, makinenizdeki başka
projeleri bozabilecek sürüm çakışmalarına yol açar. Bu yüzden projeyi **izole bir sanal
ortamda** çalıştırırız. Ayrıca PyTorch'un Python 3.14 için kararlı tekerlekleri (wheels)
henüz olmadığından **Python 3.12** kullanırız. Bu repo [`uv`](https://github.com/astral-sh/uv)
ile bootstrap edilmiştir:

```bash
# 1) İzole, projeye özel bir Python 3.12 ortamı oluştur (sistem Python'ına dokunmaz)
uv venv --python 3.12 .venv
source .venv/bin/activate

# 2) Bağımlılıkları kur
uv pip install -r requirements.txt     # uv yoksa: pip install -r requirements.txt
```

### 5.2 Testleri ve kalite kontrollerini koşturma

```bash
pytest                 # tüm testleri çalıştır (18 test, %100 başarı)
mypy src/              # strict tip denetimi (CLAUDE.md kuralı)
flake8 src/ tests/     # PEP-8 lint (azami satır uzunluğu 100)
```

Testler temiz geçtiğinde şuna benzer bir çıktı görürsünüz:

```text
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.1.0, pluggy-1.6.0
collected 18 items

tests/test_anonymizer.py ......                                          [ 33%]
tests/test_causal_lstm.py ......                                         [ 66%]
tests/test_e2e_oom.py ..                                                 [ 77%]
tests/test_enrich_log.py ....                                            [100%]

============================== 18 passed in 1.22s ==============================
```

### 5.3 Canlı log analizini başlatma

Aşağıdaki iki form da çalışır; varsayılan girdi `data/sample_bgl.log`'dur:

```bash
python src/main.py --input data/sample_bgl.log
# veya modül olarak:
python -m src.main --input data/sample_bgl.log
```

### 5.4 Gerçekçi konsol çıktısı (canlı akış)

Komutu çalıştırdığınızda terminalde tam olarak bu akışı görürsünüz: modelin küçük sentetik
veri üzerinde **eğitim kaybının düşmesi**, sağlıklı işlem loglarının **erken elenmesi** (`safe`),
ardından bellek baskısı → OOM → probe hatası → crashloop "cümlesinin" anomali olarak
yakalanması, otonom **ROLLBACK** komutunun tetiklenmesi ve son satırda **denetim zinciri
bütünlüğünün** (`chain_intact=True`) doğrulanması:

```text
[train] device=cpu samples=14 vocab=10
[train] final loss=0.0008
[safe ] score=0.000 | 2026-06-15T08:00:00.001Z INFO  service=payment-v2 node=IP_ee8a1713 use
[safe ] score=0.000 | 2026-06-15T08:00:00.045Z INFO  service=payment-v2 node=IP_ee8a1713 msg
[safe ] score=0.000 | 2026-06-15T08:00:00.090Z INFO  service=payment-v2 node=IP_ee8a1713 iba
[safe ] score=0.001 | 2026-06-15T08:00:00.140Z INFO  service=payment-v2 node=IP_ee8a1713 msg
[safe ] score=0.000 | 2026-06-15T08:00:01.001Z INFO  service=payment-v2 node=IP_8d99f4c0 msg
[safe ] score=0.000 | 2026-06-15T08:00:01.050Z INFO  service=payment-v2 node=IP_8d99f4c0 msg
[safe ] score=0.000 | 2026-06-15T08:00:01.095Z INFO  service=payment-v2 node=IP_8d99f4c0 msg
[safe ] score=0.002 | 2026-06-15T08:00:01.150Z INFO  service=payment-v2 node=IP_8d99f4c0 msg
[ANOM ] score=0.998 action=ROLLBACK target=payment-v2 executed=True
        RCA: payment-v2 exhausted JVM heap under sustained load (unbounded ledger cache), triggering OOMKilled and CrashLoopBackOff. History INC-2026-0042 and the architecture doc confirm rollback as the proven remediation.
        cmd: kubectl rollout undo deployment/payment-v2
[ANOM ] score=0.999 action=ROLLBACK target=payment-v2 executed=True
        RCA: payment-v2 exhausted JVM heap under sustained load (unbounded ledger cache), triggering OOMKilled and CrashLoopBackOff. History INC-2026-0042 and the architecture doc confirm rollback as the proven remediation.
        cmd: kubectl rollout undo deployment/payment-v2
[ANOM ] score=0.999 action=ROLLBACK target=payment-v2 executed=True
        RCA: payment-v2 exhausted JVM heap under sustained load (unbounded ledger cache), triggering OOMKilled and CrashLoopBackOff. History INC-2026-0042 and the architecture doc confirm rollback as the proven remediation.
        cmd: kubectl rollout undo deployment/payment-v2
[ANOM ] score=0.999 action=ROLLBACK target=payment-v2 executed=True
        RCA: payment-v2 exhausted JVM heap under sustained load (unbounded ledger cache), triggering OOMKilled and CrashLoopBackOff. History INC-2026-0042 and the architecture doc confirm rollback as the proven remediation.
        cmd: kubectl rollout undo deployment/payment-v2

[audit] records=56 chain_intact=True ops=[{'op': 'rollback', 'target': 'payment-v2'}, ...]
```

> **Çıktıyı okumak:** `score=0.000` olan loglar Aşama 1'de güvenli ilan edilip LLM'e hiç
> gitmedi. `MEM_PRESSURE` ile başlayıp `CRASHLOOP`'a kadar süren anomali zinciri ise
> `score≈0.999` ile yakalandı, RAG kütüphanecisi `INC-2026-0042` kaydını ve `payment-v2`
> mimari dokümanını eşleştirdi, LLM **ROLLBACK** önerdi ve otonom katman
> `kubectl rollout undo deployment/payment-v2` komutunu tetikledi. Son satır, atılan tüm
> adımların değiştirilemez deftere yazıldığını ve zincirin bütün (`chain_intact=True`)
> olduğunu doğrular.

---

## 6. Eğitici Sıkça Sorulan Sorular (FAQ)

### Neden basitçe logları ChatGPT API'sine göndermiyoruz?

İki temel sebep: **hukuk** ve **fizik**.

- **Hukuk (gizlilik):** Banka logları sır niteliğinde müşteri ve işlem verisi taşır. Bunları
  dış bir bulut API'sine (OpenAI, Anthropic) göndermek, KVKK ve BDDK'nın sır paylaşımı
  düzenlemelerini ihlal eder; veri kurumun denetim sınırını terk eder, üçüncü tarafça
  önbelleğe alınabilir. SentinelOps tüm çıkarımı yerel tutarak bu riski **mimari olarak**
  ortadan kaldırır ([Bölüm 4.2](#42-bddk-bilgi-sistemleri-yönetmeliği-uyumu--veri-sınırı-kurumu-terk-etmez)).
- **Fizik (gecikme & maliyet):** Saniyede on binlerce log üreten bir sistemde her satır için
  uzaktaki bir API'yi çağırmak hem ağ gecikmesi (yüzlerce ms) hem de astronomik maliyet
  demektir. İki aşamalı çıkarımımız, trafiğin büyük çoğunluğunu LLM'e hiç dokundurmadan
  $10\text{ ms}$ altında eler ([Bölüm 3.2](#32-enrichlog-iki-aşamalı-çıkarım-two-step-inference)).

### Sistem "normal" ile "anormal" logu nasıl ayırt ediyor?

CausalConvLSTM, tıpkı bir dil modelinin bir cümlede **sonraki kelimeyi tahmin etmesi** gibi
çalışır. Sağlıklı bir işlemin "dilbilgisini" (`REQ_RECEIVED → AUTH_OK → LEDGER_OK →
RESP_SENT`) öğrenmiştir. Akış bu öğrenilmiş örüntüden saparsa — model beklediği "kelimeyi"
göremezse — bu "şaşkınlık" yüksek bir risk skoruna ($\approx0.999$) dönüşür. Normal akışlar
modeli şaşırtmaz, skor $\approx0.000$ kalır. Ayrıntı için
[Bölüm 3.1](#31-causalconvlstm--neden-ve-nasıl).

### Otonom müdahale tehlikeli değil mi? Yanlışlıkla sistemi kapatırsa?

Sistem rastgele komut çalıştırmaz; **çok katmanlı bir güvenlik kemeri** vardır:

1. **Yalnızca onaylı runbook'lar:** Otonom katman sadece bilinen aksiyon türlerini
   (`ROLLBACK`, `RESTART`, `SCALE`) gerçekleştirir; tanımadığı bir aksiyonu veya hedefi olmayan
   bir komutu **reddeder** (no-op) ([src/orchestrator/healing.py](src/orchestrator/healing.py)).
2. **Kanıt zorunluluğu (sıfır halüsinasyon):** Bir müdahale ancak RAG, logu kurumun gerçek
   olay tarihçesi/mimari dokümanıyla eşleştirebilirse tetiklenir. Eşleşme yoksa LLM
   `{"action": "UNKNOWN"}` döner ve hiçbir şey yapılmaz.
3. **İmzalı, değiştirilemez kayıt:** Atılan veya reddedilen her adım hash-zincirli deftere
   işlenir; her şey denetlenebilir ve geriye dönük doğrulanabilirdir.

### IP adreslerini hash'lemek yerine neden tamamen silmiyoruz?

Çünkü bir IP'yi tamamen silmek, **güvenlik istihbaratını** de silmek olurdu. Eğer her IP'yi
`[IP]` ile değiştirseydik, "aynı kaynaktan gelen 1000 ardışık başarısız giriş denemesi" gibi
bir **brute-force saldırı kalıbını** ve zamansal nedenselliği göremezdik — tüm satırlar
aynileşirdi. Bunun yerine deterministik takma adlandırma kullanırız: `83.51.x.x` daima
`IP_ee8a1713` olur. Böylece orijinal IP geri döndürülemez biçimde gizli kalır (KVKK uyumu),
ama **aynı kaynaktan gelen olaylar birbirine bağlanabilir** kalır (saldırı korelasyonu
korunur). Bkz. [Bölüm 4.1](#41-kvkk--gdpr-uyumu--veriyi-minimize-et-geri-döndürülemez-kıl).

---

## 7. Proje Düzeni (Repo Haritası)

| Yol | Amaç |
| --- | --- |
| [src/anonymizer/](src/anonymizer/) | KVKK/BDDK PII maskeleme; deterministik IP takma adlandırma (salted SHA-256) |
| [src/models/](src/models/) | `CausalConvLSTM` + $L_2$-BCE eğitimi; cihaz oto-algılama; `vocab.json` kalıcılığı |
| [src/rag/](src/rag/) | EnrichLog iki aşamalı çıkarım, gömme (embedding), vektör deposu, yerel/mock LLM |
| [src/orchestrator/](src/orchestrator/) | Otonom iyileştirme (mock K8s) + hash-zincirli değiştirilemez denetim defteri |
| [src/messaging/](src/messaging/) | In-memory Kafka/Redis pub-sub simülasyonu |
| [src/main.py](src/main.py) | Uçtan uca boru hattı orkestratörü |
| [config/config.yaml](config/config.yaml) | Tüm hiperparametreler ve mod anahtarları (embeddings/LLM/eşik) |
| [data/](data/) | Örnek log (`sample_bgl.log`), olay tarihçesi (`error_corpus/`), mimari dokümanlar (`system_docs/`) |
| [tests/](tests/) | 18 test: anonimleştirme, nedensellik, eğitim, iki aşamalı çıkarım, uçtan uca OOM akışı |

### Yapılandırma anahtarları ([config/config.yaml](config/config.yaml))

| Anahtar | Varsayılan | Açıklama |
| --- | --- | --- |
| `inference.risk_threshold` | `0.35` | Aşama-1 kesme eşiği; altındaki loglar LLM'e gitmez |
| `rag.embeddings_mode` | `hash` | `hash` (offline, hızlı) veya `real` (yerel HF `bge-large-en`) |
| `rag.top_k` | `3` | RAG'in çekeceği en benzer doküman sayısı |
| `llm.mode` | `mock` | `mock` (yerleşik deterministik) veya `ollama` (kurum içi sunucu) |
| `model.window_size` | `10` | $X=\langle k_{t-w},\dots,k_{t-1}\rangle$ penceresinin $w$ uzunluğu |
| `training.l2_lambda` | `1e-4` | $L_2$ düzenlileştirme katsayısı $\lambda$ (optimizatör `weight_decay`) |

---

<div align="center">

**SentinelOps — CausalNexus**
*Logları dil gibi okur, çökmeden sezer, kendini iyileştirir, hiçbir veriyi kuruma kapı dışarı etmez.*

</div>
