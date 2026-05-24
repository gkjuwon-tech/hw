# Conet Tactile — 하드웨어 빌드 가이드 (공동창업자 전용)

> **읽는 사람**: 공동창업자. 하드웨어를 한 번도 안 만져본 사람.
> **쓴 사람**: 형. CEO 겸 기획자 겸 SW 총괄 겸 PCB schematic 다 그린 사람. 즉, 너 빼고 다 한 사람.
> **목적**: 너 이거 보고 부품 발주하고, PCB 위탁 조립 시키고, 도착하면 펌웨어 굽고, 우리 백엔드에 데이터 박히는 거까지 혼자 다 하게 만드는 거. 어렵지 않음. 형이 어려운 거 다 끝냈음.
> **톤**: 친절하지만 약은 올림. 너 일 안 한다는 거 형이랑 너 둘 다 알고 있음. 그래도 사랑은 함.
>
> ---
>
> 이 문서랑 별개로 [`HOW_IT_WORKS.md`](./HOW_IT_WORKS.md) 는 "이게 도대체 뭐냐" 를 누구나 이해할 수 있게 설명하는 문서고, [`BOM.md`](./BOM.md) 는 양산 단가 기준 BOM. 이 문서 (`HARDWARE_BUILD_GUIDE.md`) 는 "**너** 진짜로 1대 만들어라" 용임.

---

## 0. 시작하기 전에 — 너 지금 뭐하는 건지 알고 시작해라

### 0.1 우리 회사 30초 요약

```
공장 컨베이어 벨트 위에 깔판 하나 깔면,
그 위를 지나가는 부품을 손바닥으로 만져보듯 검사해서
불량을 AI 가 자동으로 걸러주는 시스템.

깔판 = 우리가 파는 하드웨어 (1회성)
AI = 우리가 파는 클라우드 (월 구독)
설치 = 가위로 잘라서 양면테이프로 붙임. 끝.
```

이게 전부. 더 자세한 건 [HOW_IT_WORKS.md](./HOW_IT_WORKS.md). 안 읽고 부품부터 사려고 하지 마라. 안 읽고 사면 너 뭐 사는지도 모르는 채로 30만원 카드 긁는 거임. 진심.

### 0.2 네가 만들 건 이거다 — "투자자 앞에 들고 갈 프로토 1대"

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1) Tactile Mesh    얇은 센서 깔판 (200 × 200 mm).                       │
│    └─ Velostat 압력 필름 + 도전성 천 격자 16×16. TPU 라미네이트.       │
│    └─ 네가 가위질해서 만듦.                                              │
│                                                                         │
│ 2) Scanner PCB     4-layer 커스텀 PCB. 형이 schematic + layout 다 함.   │
│    └─ ESP32-S3-WROOM-1 모듈 + MUX 2개 + ADC + USB-C + 보호회로.        │
│    └─ JLCPCB 에 SMT 풀턴키 어셈블리 위탁. 너는 클릭만 함.               │
│    └─ 5장에 약 ₩60,000 + 배송. 1주일 후 완제품 5장이 박스로 옴.        │
│                                                                         │
│ 3) Cloud           우리 백엔드. 이 레포의 `backend/`. 형이 다 짰음.    │
│    └─ 너는 `docker compose up` 한 줄만 치면 됨.                         │
│                                                                         │
│ 4) 노트북          백엔드를 굴릴 컴퓨터. 네 노트북.                     │
│    └─ Edge 박스 (Jetson) 는 어차피 컴퓨터랑 동일한 추론을 돌리는 거     │
│       라서 첫 프로토에선 필요 없음. 너 노트북이 곧 Edge 박스임.        │
└─────────────────────────────────────────────────────────────────────────┘
```

> 💡 **왜 처음부터 PCB? — 브레드보드는 왜 안 함?**
> 1. **투자자 앞에 들고 갈 거다.** 점퍼와이어 다발이 책상에 펼쳐져 있으면 "장난감" 으로 보임. 4-layer PCB 5장이 알루미늄 박스에 들어가 있으면 "양산 직전 단계" 로 보임. 같은 일을 하는데 가치가 10배 차이남.
> 2. **점퍼 빠지면 데이터 날아감.** 데모 5분 전에 한 가닥 빠지면 진짜 운다.
> 3. **양산 BOM 검증을 처음부터 하는 거.** 브레드보드에서 동작한다고 PCB 에서 동작한다는 보장 없음. 어차피 PCB 로 갈 거면 처음부터 PCB.

### 0.3 예산 / 시간 — **약 30만원, 약 2~3주**

| 항목 | 비용 (1대) | 시간 |
|------|-----------:|------|
| 깔판 부품 (Velostat + 도전성 천 + TPU + 양면테이프) | **약 8만원** | 발주 1주 |
| Scanner PCB × 5장 (JLCPCB SMT 풀턴키) | **약 12만원** | 7~10일 |
| 도구 (없으면 사야 함; 인두 작은 거 + 멀티미터 + 커터 + 라미네이터) | **약 12만원** | 같이 배송 |
| 조립 | 0 | **반나절** |
| 펌웨어 굽기 | 0 | **1시간** |
| 백엔드 띄우기 | 0 | **10분** |
| 첫 inspect 성공 | 0 | **30분** |
| **합계** | **약 30 ~ 32만원** | **약 2~3주 (대부분 배송 대기)** |

> 💡 형이 PCB 설계, SW 전부, 깔판 설계, 펌웨어, 펌웨어 ↔ 백엔드 게이트웨이, 캘리브레이션 알고리즘, 가격 모델, 웹훅, 마이그레이션, Docker, 테스트 30개 다 끝냈음. 너 진짜로 할 거: **(a) 발주 5번 (b) 가위질 + 라미네이팅 1번 (c) PCB 도착하면 케이블 2개 꽂기 (d) Arduino IDE 에서 펌웨어 굽기 (e) `docker compose up` 한 줄.** 이 5개임.

### 0.4 마음의 준비 (← 진심임)

- **부품 잃어버리지 마라.** SMT 부품 0402 사이즈 (1mm 도 안 됨) 들어있음. JLCPCB 가 다 붙여서 보내는데, 떨어진 거 하나 책상 어딘가에 굴러가면 다신 못 찾음.
- **인두에 손 데지 마라.** 진짜로. 한 번 데면 1주일 일 못 함.
- **멀티미터는 검정 = 마이너스, 빨강 = 플러스.** 헷갈리지 마.
- **데모 일정 잡혔으면 그 전 1주일 동안은 깔판 하나 더 만들어둬라.** 백업 없으면 라인 망가지면 끝.
- **막히면 형한테 톡.** 단, "안 됨" 만 보내지 마. **사진 + 어디까지 진행 + 어디서 막힘** 같이 보내. 안 그러면 형도 답 못함.

---

## 1. 하드웨어 vs 소프트웨어 — 너 어디까지 책임지냐

```
                     ┌─────────────────────────────┐
                     │   고객 공장 컨베이어 벨트   │
                     └──────────────┬──────────────┘
                                    │
                  ─── HARDWARE ─────┴──── (← 네 일)
                                    │
              ┌─── Tactile Mesh ────┘
              │   (Velostat + 도전성 천 격자 + TPU)
              │                      ← 네가 가위질
              │
              ▼
       Scanner PCB
       (ESP32-S3-WROOM-1 + MUX × 2 + ADC + USB-C)
              │                      ← 형이 설계, JLCPCB 가 조립, 너는 발주
              │
              │  USB-C
              ▼
   ─── SOFTWARE ─────────────────────────── (← 형 일)
              │
       너 노트북 (= Edge 역할)
              │
       Tactile Cloud  ←── FastAPI 백엔드 (이 레포 `backend/`)
              │
              ▼
       대시보드 / 슬랙 / MES
```

**네 일** = `HARDWARE` 박스 안의 모든 것 (단, PCB schematic + layout 은 형이 끝냈으니 너는 발주만).
**형 일** = `SOFTWARE` 박스 안의 모든 것 + PCB 설계 + 깔판 설계.
**둘 다 망하면 안 되는 거** = USB-C 케이블 빠지면 둘 다 망함.

> 💡 Edge 박스 (Jetson Orin Nano) 는 첫 프로토에서 **사지 마라.** 그건 양산 직전 "고객 공장에 두고 갈 박스" 인데, 첫 데모는 너 노트북에 USB-C 한 가닥 꽂아서 충분히 됨. Jetson 은 두 번째 라인 깔 때부터.

---

## 2. 부품 쇼핑 리스트 — **이 표 그대로 카드 긁어라**

> ⚠️ **가격은 2026년 5월 기준** (1 USD ≈ ₩1,360). 시간 지나면 살짝 바뀜.
> ⚠️ **링크는 끊어질 수 있음.** 끊어졌으면 부품명을 그대로 복사해서 같은 사이트 검색창에 붙여넣어. "링크 안 됨" 톡 보내지 마. 그냥 검색해.
> 💡 한국 발주는 **디바이스마트** (다음날 도착), 해외는 **Adafruit** (5~10일, DHL). PCB 는 **JLCPCB** 풀턴키.

### 2.1 깔판 (Tactile Mesh) — **약 8만원**

| # | 부품 | 수량 | 어디서 | 단가 (대략) | 링크 / 검색어 |
|---|------|------|--------|-----------:|---------------|
| M1 | **Velostat / Linqstat 시트** (압력 감지 필름, A4 1장) | 1장 (280×280 mm) | Adafruit | $4.95 ≈ ₩6,800 | [Adafruit #1361](https://www.adafruit.com/product/1361) — 검색어: `Velostat 1361` |
| M2 | **전도성 천** (silver-plated nylon ripstop, 50 mΩ/sq, A4 정도) | 1장 | Adafruit | $19.95 ≈ ₩27,000 | [Adafruit #1167](https://www.adafruit.com/product/1167) — 검색어: `conductive fabric ripstop` |
| M3 | **전도성 실** (silver-plated 4-ply) | 1롤 | Adafruit | $6.95 ≈ ₩9,500 | [Adafruit #641](https://www.adafruit.com/product/641) — 검색어: `conductive thread 641` |
| M4 | **Kapton 테이프** (25 µm × 12 mm 폭 × 33 m) | 1롤 | 디바이스마트 / 쿠팡 | ₩6,000 ~ 12,000 | 디바이스마트 검색: `Kapton tape 12mm` |
| M5 | **TPU 라미네이팅 필름** (식품등급, A4 10장 묶음) | 1팩 | 쿠팡 | ₩8,000 ~ 15,000 | 쿠팡 검색: `라미네이팅 필름 A4 무광` (광택 NO, 무광 / 매트) |
| M6 | **3M VHB 5952 양면테이프** (25 mm × 33 m) | 1롤 | 쿠팡 | ₩28,000 | 쿠팡 검색: `3M VHB 5952` |
| M7 | **FFC 케이블** (1.0 mm pitch, 16-pin × 2개, 길이 150 mm) | 2개 | 디바이스마트 / 디지키 | ₩2,500 / 개 | 디바이스마트 검색: `FFC 1.0mm 16pin 150mm` (좌우 동일면) |

**소계: 약 8만원.** Adafruit 3개 (M1, M2, M3) 한 번에 시키면 배송비 절약.

> 💡 **개인통관고유부호 안 만들었으면 지금 발급해.** [unipass.customs.go.kr](https://unipass.customs.go.kr) 1분 컷. Adafruit 결제할 때 필요함.

### 2.2 Scanner PCB — **JLCPCB SMT 풀턴키, 5장 약 12만원**

> 형이 다 끝냄. 너는 클릭 4번이면 됨. ㅋ

#### 형이 준 것

```
hardware/pcb/conet-scanner-v1/
├── README.md           ← 보드 설명, 핀맵, 알려진 이슈 (형이 쓴 거)
├── schematic.md        ← schematic 의 markdown 표현 (사람이 읽을 수 있게)
├── gerbers.zip         ← JLCPCB 에 던지는 제조 파일 ⭐
├── bom.csv             ← JLCPCB 가 부품 사올 목록 ⭐
└── cpl.csv             ← JLCPCB 가 부품 어디 붙일지 좌표 ⭐
```

> ⚠️ **현재 상태**: schematic.md 와 README.md 는 이 PR 에 같이 들어있음. `gerbers.zip`, `bom.csv`, `cpl.csv` 는 형이 EDA 툴 (KiCad / Altium) 작업해서 별도 PR 로 합류시킬 거임. 그 PR 머지되면 이 폴더가 완성됨. 그 전까지는 schematic.md 만 보면서 "아 이런 보드구나" 만 알면 됨.

#### JLCPCB 발주 - 클릭 4번

1. [jlcpcb.com](https://jlcpcb.com) → 회원가입 (이메일로 1분).
2. **Order Now** → "Add Gerber file" → `hardware/pcb/conet-scanner-v1/gerbers.zip` 업로드.
3. 옵션:
   - Base Material: **FR-4**
   - Layers: **4**
   - Dimensions: 자동 인식됨 (약 60 × 40 mm)
   - PCB Qty: **5** (5장이 가장 가성비, 더 비싸지 않음)
   - PCB Color: 검정 (간지) 또는 보라 (Conet 라임그린이랑 안 어울리지만 보라가 시그니처 PCB 색)
   - Surface Finish: **ENIG (lead-free)** — 식품 라인 갈 거니까 필수
   - Outer Copper Weight: **1 oz**
   - Inner Copper Weight: **0.5 oz**
   - Via Covering: **Tented**
4. 다음 페이지 → **PCB Assembly** 체크 ON (= SMT 풀턴키)
   - PCBA Type: **Standard**
   - Assembly Side: **Top Side** (보드 한쪽만)
   - Tooling Holes: **Added by JLCPCB**
   - Confirm Parts Placement: **Yes** (한 번 더 확인)
5. **Add BOM File**: `bom.csv` 업로드.
6. **Add CPL File**: `cpl.csv` 업로드.
7. JLCPCB 시스템이 BOM 매칭 결과를 보여줌. 빨간 줄 (Out of Stock) 나오면 → **Alternative** 클릭해서 대체 부품 골라. 형이 BOM 에 표시해놓은 대체 부품번호 따라가면 됨.
8. **Save to Cart** → **Checkout** → 배송지 (영문) + 개인통관고유부호 + DHL Express 선택.
9. 결제. 끝. **5장에 약 $80 ~ $90 (≈ ₩110,000)** + 배송비 $20 ≈ **합 ₩140,000**.

> 💡 **JLCPCB 가 부품도 다 사다가 다 붙여서 보내줌.** 너는 완성된 보드 5장을 박스로 받음. 인두질 안 해도 됨. 8~10일 후 도착.

#### PCB 도착 후 검사 (10분)

1. 박스 깔 때 SMD 부품 떨어뜨리지 말기. 보드는 ESD 백에 들어있음.
2. **육안 검사**: USB-C 커넥터, ESP32 모듈 (가운데 큰 부품), MUX 2개 (작은 사각형 두 개) 가 다 붙어 있는지.
3. **전원 검사**: USB-C 케이블 노트북에 꽂기. 보드의 빨간/녹색 LED 가 켜져야 함. LED 안 켜지면 = 보드 죽음 (드물지만 가능). 다른 보드 시도.
4. **시리얼 검사**: Arduino IDE 의 Tools → Port 에 보드가 잡혀야 함. (자세한 건 5절 참조)

> 💡 **5장 받는 이유**: 1장 데모용 + 1장 백업 + 1장 망가뜨릴 거 + 2장 다음 고객 라인용. 미리 받아두면 마음 편함.

### 2.3 도구 (한 번만 사면 됨) — **약 12만원**

> SMT 조립은 JLCPCB 가 다 함. 너는 디버그/수리용 도구만 있으면 됨.

| # | 도구 | 수량 | 어디서 | 단가 | 검색어 |
|---|------|------|--------|-----:|--------|
| T1 | **납땜 인두 키트** (60W 온도조절, 가위 떼면 끝, 와이어 인두용) | 1 | 쿠팡 | ₩30,000 | `납땜 인두 키트 온도조절` |
| T2 | **솔더 와이어** (0.5 mm 100g) | 1 | 쿠팡 | ₩8,000 | `솔더 0.5mm` |
| T3 | **디지털 멀티미터** | 1 | 쿠팡 | ₩15,000 | `디지털 멀티미터 DT-830B` |
| T4 | **로타리 커터** (45 mm + 자) | 1 | 쿠팡 | ₩10,000 | `로타리 커터 45mm` |
| T5 | **스테인리스 자 300 mm** (미끄럼방지) | 1 | 쿠팡 | ₩6,000 | `스테인리스 자 300mm` |
| T6 | **A3 라미네이팅 머신** (가정용) | 1 | 쿠팡 | ₩55,000 | `라미네이팅 머신 A3 가정용` |
| T7 | **정전기방지 작업매트** | 1 | 쿠팡 | ₩3,000 | `정전기방지 작업매트` |

**소계: 약 12만원.** 회사 서랍에 이미 있는 거 빼라. (인두 / 멀티미터 흔히 굴러다님.)

> 💡 **이미 갖고 있는 거 다 빼면 4~5만원 선까지 떨어짐.** 회사 책상 서랍 다 까봐. 그래도 라미네이터는 십중팔구 없음.

---

## 3. 발주 가이드 — **사이트별 한 페이지**

> 형은 발주 자동조종 모드인데 너는 처음일 수 있음. 이미 아는 데는 건너뛰어라.

### 3.1 디바이스마트 (devicemart.co.kr) — 한국, 다음날

1. [devicemart.co.kr](https://www.devicemart.co.kr/) → 회원가입 (사업자등록증 있으면 사업자, 세금계산서 발급용).
2. 검색창 → 부품명 그대로. 예: `Kapton tape 12mm`, `FFC 1.0mm 16pin 150mm`.
3. 장바구니 → **주문하기** → 배송지 → **신용카드** 결제.
4. **오후 3시 이전 결제 → 당일 출고 → 다음 영업일 도착.**
5. 세금계산서 발급 (자동).

### 3.2 쿠팡 — 한국, 다음날 (로켓배송)

1. 그냥 사. 모르면 부모님한테 물어봐.
2. **로켓배송** 마크 있는 거만. 일반 판매자는 1주일.
3. 회사 카드로 긁어. 영수증 안 잃어버리게.

### 3.3 Adafruit (adafruit.com) — 미국, DHL 5~10일

1. [adafruit.com](https://www.adafruit.com/) → 회원가입.
2. 검색 → 부품 번호 (예: `1361`).
3. 장바구니 → **Checkout** → 배송지 (영문, 예시):
   ```
   Name: Gildong Hong
   Address Line 1: 123-45 Teheran-ro, Gangnam-gu
   Address Line 2: 7F Conet Studio
   City: Seoul
   State/Province: Seoul
   Postal Code: 06234
   Country: South Korea
   Phone: +82-10-1234-5678
   ```
4. 배송: **DHL Express** ($55) ← 추천. 4~5일 도착.
5. 결제 (VISA / Master).
6. **개인통관고유부호** 필수 ([unipass.customs.go.kr](https://unipass.customs.go.kr)).
7. **합산 $150 이하면 면세.** 위 표 2.1 합산이 ~$32 이라서 면세권. 다른 거 같이 사면 합산되니 주의.

### 3.4 JLCPCB (jlcpcb.com) — 중국, DHL 8~10일 ⭐

> 위의 `2.2` 섹션에 클릭 순서 다 있음. 한 번 더 정리:

1. 회원가입 → **Order Now**.
2. **Gerber 업로드** → `hardware/pcb/conet-scanner-v1/gerbers.zip` (형이 별도 PR 로 합류시킨 뒤 가능).
3. 옵션: **4-layer / ENIG / 5장 / 검정 또는 보라**.
4. **PCB Assembly** 체크 → **Top Side / Standard**.
5. **BOM 업로드** (`bom.csv`) + **CPL 업로드** (`cpl.csv`).
6. 빨간 줄 (재고 없음) 나오면 → Alternative 클릭 → 대체부품 선택.
7. **DHL Express** 선택 → 결제 → 끝.
8. 진행 상황은 JLCPCB 사이트에서 추적. "Production" → "Quality Check" → "Shipped" 순서로 넘어감.

> 💡 **첫 사용자 쿠폰**: 회원가입 직후 신규 사용자 쿠폰 ($30 정도) 자동 적용됨. 받아먹어.

### 3.5 발주 체크리스트

- [ ] 위 표 (2.1, 2.2, 2.3) 모든 항목 → 사이트별 장바구니 담음.
- [ ] 디바이스마트: 세금계산서 발급 가능 회원가입.
- [ ] Adafruit / JLCPCB: 개인통관고유부호 입력란 채움.
- [ ] 영문 배송 주소 정확.
- [ ] 회사 카드 (지출증빙).
- [ ] 도착 예정일 캘린더에 박음.
- [ ] **결제 후 형한테 톡: "다 발주 완료. M1~M7 / PCB 5장 / 도구 X / Y / Z. 도착 예정 YYYY-MM-DD."**
  - "발주했음" 만 보내면 형이 못 알아봐. 항목 + 도착예정일 같이 보내야 함.

---

## 4. 조립 — **드디어 너 손 움직일 시간**

> ⏱️ **총 시간**: 깔판 1.5시간 + PCB 케이블 연결 5분 + 라미네이팅 30분 = **약 2시간**.
> 🩹 **안전**: 인두 350°C, 손 대지 마. 환기.

### 4.1 깔판 만들기 — 16 × 16 = 256 셀

> 원리: **Velostat** (압력 받으면 저항이 떨어지는 검정 필름) 위·아래로 **전도성 천 격자**. 가로줄 1개 (행) + 세로줄 1개 (열) 의 교차점이 한 셀. **16 × 16 = 256 셀**. PCB 의 ESP32 가 1초에 200번씩 256 셀 다 훑음.

```
┌─ Top TPU 코팅 ───────────────────────────────────────┐
│ ─── 열 1 ───  ─── 열 2 ───  ───  ...  ─── 열 16 ─── │  ← 세로줄 (전도성 천 16가닥)
├──────────────────────────────────────────────────────┤
│   ░░░░░░░░░░ Velostat 압력 필름 ░░░░░░░░░░░░░░░░░░  │  ← 압력으로 저항이 변하는 검정 필름
├──────────────────────────────────────────────────────┤
│ ─── 행 1 ───────────────────────────────────────────  │
│ ─── 행 2 ───────────────────────────────────────────  │  ← 가로줄 (전도성 천 16가닥)
│   ...                                                │
│ ─── 행 16 ──────────────────────────────────────────  │
├──────────────────────────────────────────────────────┤
│              Bottom TPU 코팅                          │
└──────────────────────────────────────────────────────┘
```

#### 단계별

1. **종이에 격자 그려라.** 200 × 200 mm 정사각. 한 셀 = 12.5 × 12.5 mm. 자 + 연필. 진짜로 그려라.
2. **Velostat 자르기**: 로타리 커터 + 자 → 200 × 200 mm 정사각 한 장.
   - 💡 Velostat 한 장으로 두 장 만들지 마. 처음엔 한 장에 한 라인.
3. **전도성 천을 가로줄로 자르기**: 너비 **5 mm**, 길이 **220 mm** (양 끝 10mm 씩 케이블 연결용 여유). **16 가닥**.
   - 💡 천이 잘 풀어짐. 끝단에 **투명 매니큐어** 발라서 굳히면 안 풀림. 진짜로.
4. **Velostat 한쪽 면에 가로줄 16개 평행하게 깔기**: 줄 간격 **12.5 mm**. Kapton 테이프로 끝단 임시 고정.
   - 💡 자를 대고 정렬해. 비뚤어지면 셀이 사다리꼴 됨.
5. **Velostat 위에 한 장 더 (또는 같은 한 장을 접어서)** 덮기.
6. **세로줄 16개**: 같은 방식으로 위층에 12.5 mm 간격, 가로줄과 직교.
7. **각 줄 끝단을 FFC 압착 또는 클립**:
   - **방법 A (간단)**: 점퍼와이어 클립으로 16가닥 행 + 16가닥 열을 PCB 의 FFC 커넥터 핀에 일대일로 물림. 처음 1대는 이렇게.
   - **방법 B (양산스러움)**: 도전성 접착제로 0.5 mm pitch FFC 케이블에 본딩. 양산은 ZIF 커넥터 + 전용 압착기.
8. **TPU 라미네이팅 필름** 위·아래 한 장씩 → 라미네이터 통과.
9. **밑면에 3M VHB 양면테이프** (컨베이어 부착용; 데모 시엔 책상에 깔아도 됨). **보호지는 절대 떼지 마**.

#### 라미네이팅 전 멀티미터 검사 — **반드시**

라미네이팅하면 못 고침. 무조건 검사 먼저.

1. 멀티미터 → 저항 Ω → 200 kΩ 레인지.
2. 빨강 → 가로줄 1번. 검정 → 세로줄 1번.
3. 손가락으로 셀 (1,1) 꾹.
   - **누르기 전**: 30 ~ 100 kΩ
   - **누른 후**: 2 ~ 10 kΩ
4. 누르면 저항이 떨어지면 정상. 안 떨어지면:
   - 격자 단선
   - 위·아래 도전층이 직접 닿음 (단락) → Velostat 한 겹 더 추가
5. 랜덤 **8~10셀** 검사. 256셀 다 안 해도 됨.

### 4.2 PCB 도착 후 — **케이블 2개 꽂으면 끝**

JLCPCB 가 완성품을 보내줌. 너는:

1. **깔판 ↔ PCB**: 깔판의 가로줄 16가닥 → PCB 의 **J1 (ROW)** 16핀 FFC 커넥터. 세로줄 16가닥 → **J2 (COL)** 16핀 FFC 커넥터.
   - FFC 케이블이면 그대로 슬라이드 인.
   - 점퍼 + 클립이면 핀 번호 따라 1:1 으로 물림. (PCB 의 핀 번호는 보드 silkscreen 에 인쇄됨.)
2. **PCB ↔ 노트북**: USB-C 케이블 한 가닥. 끝.

> 💡 핀맵 / 회로 / 알려진 이슈 → `hardware/pcb/conet-scanner-v1/README.md` 참고.

### 4.3 라미네이팅 (30분)

1. 깔판 위·아래 TPU 필름 한 장씩.
2. 라미네이터 예열 (3~5분).
3. **천천히** 통과 (빠르면 기포). 일정한 속도.
4. 식힌 뒤 가장자리 가위 다듬기.
5. 끝.

> ⚠️ 라미네이터 온도 110°C 권장. 140°C 넘으면 Velostat 손상.

---

## 5. 펌웨어 굽기 — Arduino IDE 로 PCB 의 ESP32-S3 굽는 법

### 5.1 Arduino IDE 설치 (15분, 1회)

1. [arduino.cc/en/software](https://www.arduino.cc/en/software) → 다운로드 → 설치.
2. **File → Preferences → Additional Boards Manager URLs**:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. **Tools → Board → Boards Manager** → 검색 `esp32` → **"esp32 by Espressif Systems"** 설치 (1~3분).
4. **Tools → Board → esp32 → "ESP32S3 Dev Module"**.
5. **Tools → USB CDC On Boot → Enabled** ⚠️ 안 켜면 USB 시리얼 안 나옴.
6. **Tools → Port** → 보드가 꽂힌 포트 선택.

### 5.2 펌웨어 굽기 (10분)

```bash
git clone https://github.com/gkjuwon-tech/hw.git
cd hw/firmware/tactile_scanner_esp32/
```

1. Arduino IDE 에서 `tactile_scanner_esp32.ino` 열기.
2. 우측 상단 **✓ (체크)** = 컴파일. 처음 30초~1분.
3. 우측 상단 **→ (화살표)** = 업로드. 1분 정도. 끝나면 보드의 LED 가 깜빡.

> 💡 PCB 의 핀맵은 펌웨어 (`tactile_scanner_esp32.ino`) 의 핀 정의와 **완전 일치**하게 형이 설계함. 그냥 굽기만 하면 됨.

### 5.3 USB 시리얼 확인 (5분)

펌웨어가 200 Hz 로 256 byte + 헤더를 USB CDC 로 토하고 있어야 함.

```bash
pip install pyserial
python3 - <<'EOF'
import serial, struct, sys
PORT = "/dev/tty.usbserial-XXX"   # ← Windows 면 COM3 같은 거. 너 포트 확인 후 바꿔.
BAUD = 2_000_000
HEADER = struct.Struct("<IHHIIHH")
MAGIC = 0x434F4E54
def read(s,n):
    b=b""
    while len(b)<n:
        c=s.read(n-len(b))
        if not c: sys.exit("port closed")
        b+=c
    return b
with serial.Serial(PORT, BAUD, timeout=1) as s:
    while True:
        x=read(s,1)
        if x!=b"T": continue
        rest=read(s,HEADER.size-1)
        m,r,c,seq,ts,crc,_=HEADER.unpack(x+rest)
        if m!=MAGIC: continue
        frame=read(s,r*c)
        print(f"seq={seq} avg={sum(frame)/len(frame):.1f}")
EOF
```

깔판 누를 때 **avg** 값이 올라가야 함. 안 올라가면 깔판 ↔ PCB 배선 또는 깔판 자체 문제.

---

## 6. 백엔드 띄우기 — `docker compose up` 한 줄

### 6.1 사전 준비 (5분)

1. **Docker Desktop**: [docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/) 다운로드.
2. **Git**: [git-scm.com](https://git-scm.com).

### 6.2 띄우기 (5분)

```bash
git clone https://github.com/gkjuwon-tech/hw.git
cd hw/backend
docker compose up --build
```

빌드 1~3분. 끝나면:

- API: http://localhost:8000
- 문서: http://localhost:8000/docs
- 메트릭: http://localhost:8000/metrics
- 헬스: http://localhost:8000/healthz

### 6.3 첫 호출 (1분)

```bash
curl http://localhost:8000/healthz
# → {"status":"ok","version":"0.1.0","environment":"production"}

curl http://localhost:8000/v1/pricing/catalog
# → {"belt_widths":[...], "edge_appliance_krw":1690000, "cloud_tiers":[...]}
```

이게 나오면 백엔드 끝. 형이 한 일임. 고마워해라.

---

## 7. PCB ↔ 백엔드 게이트웨이 — 첫 inspect

### 7.1 게이트웨이 스크립트

```python
# save as: tools/gateway.py
import serial, struct, requests, time

PORT = "/dev/tty.usbserial-XXX"   # ← 너 포트로
BAUD = 2_000_000
HEADER = struct.Struct("<IHHIIHH")
MAGIC = 0x434F4E54
API = "http://localhost:8000"

def post(p, j):
    r = requests.post(f"{API}{p}", json=j, timeout=5)
    r.raise_for_status()
    return r.json()

def read_frame(s):
    while True:
        b = s.read(1)
        if b != b"T": continue
        rest = s.read(HEADER.size - 1)
        m, r, c, seq, ts, crc, _ = HEADER.unpack(b + rest)
        if m != MAGIC: continue
        data = s.read(r * c)
        return r, c, list(data)

def main():
    line = post("/v1/lines", {"name": "test-line-01", "rows": 16, "cols": 16})
    LINE_ID = line["id"]
    print(f"Line {LINE_ID} 생성됨")
    with serial.Serial(PORT, BAUD, timeout=1) as s:
        print("정상품 5개 흘려라...")
        for i in range(5):
            r, c, f = read_frame(s)
            post(f"/v1/lines/{LINE_ID}/frames", {"frame": f})
            print(f"  {i+1}/5 frame buffered")
            time.sleep(2)
        cal = post(f"/v1/lines/{LINE_ID}/calibrate", {})
        print(f"캘리브레이션 완료: {cal}")
        print("이제부터 inspect 무한루프 (Ctrl+C 로 종료)")
        while True:
            r, c, f = read_frame(s)
            v = post(f"/v1/lines/{LINE_ID}/inspect", {"frame": f})
            print(f"  verdict={v['verdict']} score={v['score']:.3f}")

if __name__ == "__main__":
    main()
```

### 7.2 실행 (3분)

```bash
cd hw
pip install pyserial requests
python tools/gateway.py
```

1. 라인 자동 생성.
2. 정상품 5개 흘리라고 시킴. 깔판 위에 정상품 (빵 1개 또는 무거운 책 등) 5번 올렸다 내렸다.
3. 캘리브레이션 자동.
4. inspect 무한루프. 정상품 = `pass`, 다른 거 = `fail`.

이 시점 = **데모 가능**. 형한테 영상 보내. 자랑할 때임. ㅋㅋ

---

## 8. 트러블슈팅 — **반드시 한 번은 겪는 문제들**

### 8.1 "PCB 가 포트에 안 잡혀"

| 증상 | 해결 |
|------|------|
| 포트 목록에 안 보임 | 1) USB-C 케이블 **데이터** 가능 케이블인지 확인 (충전전용 케이블 흔함). 2) Windows: [Espressif USB 드라이버](https://www.espressif.com/en/support/download/other-tools) 설치. 3) 케이블 방향 뒤집어서 다시. |
| 잡혔는데 업로드 실패 | PCB 의 **BOOT 버튼** 누른 채로 **RESET 버튼** 짧게 → BOOT 떼기 (부트로더 모드). 그 후 업로드. |
| "Failed to connect" | 위 부트로더 모드. 또는 Arduino IDE 의 **Upload Speed → 460800** 으로 낮춰. |

### 8.2 "프레임이 다 0"

| 증상 | 해결 |
|------|------|
| 모든 셀 ADC 값 = 0 | 깔판 ↔ PCB FFC 케이블 안 꽂힘 or 케이블 방향 반대. |
| 누르지도 않았는데 4095 | 깔판이 단락. Velostat 한 겹 더. |
| 한 행만 0 | 그 행의 FFC 핀 접촉 불량. 멀티미터로 도통 확인. |

### 8.3 "Cloud 가 500 토함"

`docker compose logs api` 로 봐. 99% 는:
- 라인이 calibrated 가 아님 → `/v1/lines/{id}/calibrate` 먼저.
- frame 크기 안 맞음 (line 만들 때 rows/cols 16×16 인지 확인).
- frame 이 list 가 아니라 string → JSON 직렬화 확인.

### 8.4 "verdict 가 다 pass"

- 캘리브레이션 때 **다양한 정상품** 5개 줬어야 함. 같은 거만 흘리면 그것만 정상으로 학습.
- 임계값 너무 높음. `PATCH /v1/lines/{id}` 로 `threshold_score` 를 기본 4.0 → 2.5 로.

### 8.5 "라미네이팅 후 깔판 사망"

- 라미네이터 온도 너무 높음 (110°C 이내).
- 라미네이팅 전 멀티미터 검사 했어야 함.
- 새로 만들어. 학습비.

### 8.6 "JLCPCB BOM 매칭에 빨간 줄"

- 재고 없음. **Alternative** 클릭 → 형이 BOM 에 표시한 대체 부품번호 따라가.
- 그래도 안 되면 → 형한테 톡. 부품 번호 + 스크린샷.

### 8.7 "통관 막힘"

- 개인통관고유부호 누락. [unipass.customs.go.kr](https://unipass.customs.go.kr).
- 합산 $150 초과 → 부가세 + 관세. 결제하면 풀려.

---

## 9. 너 진짜 할 일 (체크리스트) — **3주 컷**

이거 그대로 따라가. 못 하겠으면 어디서 막혔는지 형한테 톡.

### Week 1 — 발주 (월~화)

- [ ] [`HOW_IT_WORKS.md`](./HOW_IT_WORKS.md) 읽음 (30분)
- [ ] 이 문서 0~3절 읽음 (30분)
- [ ] 개인통관고유부호 발급 (10분)
- [ ] Adafruit / 디바이스마트 / 쿠팡 결제 (30분)
- [ ] **JLCPCB SMT 풀턴키 5장 결제** (40분) ⭐
- [ ] 회사 카드 영수증 챙김
- [ ] 형한테 톡: "M1~M7 / PCB 5장 / 도구 N개 발주 완료. 도착 예정 YYYY-MM-DD"

### Week 2 — 깔판 + 도구 도착

- [ ] 부품 박스 다 까서 한 곳에 모음 (15분)
- [ ] 종이에 16×16 격자 그림 (15분)
- [ ] Velostat 자르고 가로줄 16가닥 깔기 (30분)
- [ ] 세로줄 16가닥 + 절연층 (30분)
- [ ] 멀티미터 8~10셀 검사 → 통과 (15분)
- [ ] 라미네이팅 (30분)
- [ ] 형한테 깔판 누르면서 멀티미터 저항 변하는 영상 보냄 (5분)

### Week 3 — PCB 도착 + 펌웨어 + 첫 inspect

- [ ] PCB 5장 박스 도착, ESD 백 열기 (5분)
- [ ] 육안 검사 (10분)
- [ ] USB-C 꽂아서 LED 켜지는지 확인 (5분)
- [ ] 깔판 ↔ PCB FFC 케이블 연결 (10분)
- [ ] Arduino IDE 설치 + 펌웨어 굽기 (30분)
- [ ] `pyserial` 로 프레임 흐름 확인 (10분)
- [ ] Docker Desktop 설치 + `docker compose up` (15분)
- [ ] `gateway.py` 돌려서 라인 생성 → 5 프레임 → calibrate → inspect (30분)
- [ ] 정상품 / 비정상품 구분되는 영상 찍기 (10분)
- [ ] 형한테 영상 + **"진짜 됨"** 톡 ⭐

이 시점 = **둘 다 투자자 미팅 잡을 수 있음**.

---

## 10. 마지막 — 약 좀 올림

> 정리해보자.
>
> - **회사 아이템 기획**: 형.
> - **시장 분석 + 모트 설계**: 형.
> - **랜딩페이지 디자인 + 카피**: 형.
> - **가격 모델 설계**: 형.
> - **FastAPI 백엔드 (멀티테넌시 + auth + 가격 API + drift + 웹훅 + rate limit + Prometheus + Alembic + Docker + 테스트 30개)**: 형.
> - **펌웨어 (ESP32-S3 + MUX 스캔 + USB CDC + CRC + 200 Hz 프레임 포맷)**: 형.
> - **PCB schematic + layout**: 형.
> - **JLCPCB BOM + CPL + Gerber**: 형.
> - **공장에서 깔리는 깔판 설계**: 형.
> - **이 문서 (← 너 손에 들린 거)**: 형.
>
> 너 할 거:
> - **카드 5번 긁기**.
> - **가위질 한 번**.
> - **케이블 2개 꽂기**.
> - **Arduino IDE 클릭 5번**.
> - **`docker compose up` 한 줄**.
>
> 이 비율 봐. 형이 미친 게 아니라 너 진짜 운 좋은 거. 받은 패가 좋은 거니까 카드 게임 똑바로 하자. 진짜 1대 만들고 영상 보내. 그 뒤로는 너랑 형 둘 다 투자자 앞에서 같은 무게로 발표함.
>
> 막히면 톡. **"안 됨"** 만 보내지 마. 사진 + 어디까지 + 어디서. 안 그러면 형도 답 못함.
>
> 인두에 손 대지 마라. 진짜로.
>
> 가자.
>
> — 형
