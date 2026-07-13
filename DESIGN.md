# Dimension — Style Reference
> dusk-lit workspace with frosted glass panels

**Theme:** dark

Dimension operates as a dusk-lit AI workspace: deep matte-black canvases (#0a0a0a) carry frosted-glass panels, pill-shaped controls, and whisper-weight headlines that lean on medium weights (500) rather than bold statements. The system is almost entirely achromatic — white and warm grays do all the talking — punctuated by a signature gradient hero that transitions from warm amber through to cobalt blue, evoking a sunset bleeding into a product UI. Components are lightweight and round: 9999px pill buttons, 10px UI radii, 24px card radii, with hairline 1px borders rather than heavy shadows. The visual rhythm is quiet, controlled, and editorial — every element feels placed rather than dropped, with generous breathing room and a single violet glow (#6b62f2 at 0.565 alpha) as the only chromatic accent, used sparingly in linear gradient washes.

> **Hooxi-CMS 적용 노트**: 본 레퍼런스는 랜딩페이지 성격의 원본이다. 내부 CMS(데이터 테이블·폼 중심)에는 색/서피스/타이포/라운드/보더/버튼 시스템을 그대로 채택하되, 랜딩 전용 요소(72px display hero, 전면 warm→cool 그라데이션, floating bottom nav)는 로그인 화면 등 적절한 지점에만 제한 적용한다. 상태 배지(계약·이슈·정산 등 도메인 색)는 기능 신호이므로 achromatic 원칙의 예외로 다크 배경에 맞춰 채도를 낮춰 유지한다.

## Tokens — Colors

| Name | Value | Token | Role |
|------|-------|-------|------|
| Void Canvas | `#0a0a0a` | `--color-void-canvas` | Primary page background, base surface for the dark UI shell |
| Graphite | `#161616` | `--color-graphite` | Elevated surface for floating panels, pill nav bar, modal bodies — one step above canvas |
| Frosted Glass | `#d4d4d4` | `--color-frosted-glass` | Translucent panel fill at 10% opacity over dark surfaces |
| Ink Black | `#000000` | `--color-ink-black` | Icon strokes, SVG fill, deep contrast elements on light surfaces |
| Snow White | `#ffffff` | `--color-snow-white` | Primary CTA fill, headline text on dark surfaces, card backgrounds |
| Bone | `#ededed` | `--color-bone` | Primary readable text on dark surfaces — slightly warmer than pure white |
| Ash | `#c2c2c2` | `--color-ash` | Secondary body text, helper copy, de-emphasized labels |
| Slate | `#686868` | `--color-slate` | Muted text, link text, tertiary metadata |
| Smoke | `#b2b2b2` | `--color-smoke` | Disabled/idle button text, ghost control labels |
| Hairline | `#e5e5e5` | `--color-hairline` | 1px borders — appears as light edge against dark canvas (앱에서는 white/10 사용) |
| Dusk Violet | `#6b62f2` | `--color-dusk-violet` | The only chromatic accent — gradient wash / radial glow only, never solid fill |

## Tokens — Typography

- **DM Sans** (`--font-dm-sans`, 대체 Inter) — display·body·UI. 72px display는 weight 500 / -0.035em. 13–18px UI는 +0.025em. 700+ 금지, 500 restraint가 시그니처.
- **Geist** (`--font-geist`, 대체 Inter) — 섹션 헤딩·에디토리얼 본문. 24px 이상. 32px/600·36px/500·48px/500.

### Type Scale
| Role | Size | Line Height | Letter Spacing |
|------|------|-------------|----------------|
| caption | 13px | 1.5 | 0.33px |
| body | 16px | 1.5 | — |
| subheading | 18px | 1.5 | — |
| heading-sm | 24px | 1.33 | — |
| heading | 36px | 1.11 | — |
| heading-lg | 48px | 1 | — |
| display | 72px | 1 | -2.52px |

## Tokens — Spacing & Shapes

**Density:** comfortable. Spacing scale 4·6·8·10·12·14·16·20·22·24·28·32·40·44·48·56 px.

### Border Radius
| Element | Value |
|---------|-------|
| ui | 10px |
| cards | 24px |
| icons | 4px |
| panels | 42px |
| buttons | 9999px |
| largeCards | 40px |

### Shadows
- subtle: `rgba(255,255,255,0.1) 0 0 0 1px inset` — 그 외 elevation은 box-shadow 대신 translucency·hairline·surface contrast로.

### Layout
- Page max-width 1200px · Section gap 64–80px · Card padding 28px · Element gap 8–16px

## Components (요약)
- **White Pill CTA** — 흰 배경·#161616 텍스트·9999px·8×12 padding. 유일한 filled 버튼.
- **Ghost Nav Button** — 투명·흰 텍스트 85%·1px hairline·9999px·6×14.
- **Floating Frosted Nav** — #161616(반투명)·19px 비대칭 radius·4px blur·1px border·floating(16–24px margin).
- **Hairline Ghost Button** — 투명·1px hairline·10px radius(비-pill)·tight padding. 연동/태그 라벨용.
- **Frosted Glass Feature Card** — rgba(212,212,212,0.1)·24px radius·blur 4px·no shadow.
- **Numbered Accordion Row / Bulleted Feature Row** — 에디토리얼 리스트, 보더·배경 없음.
- **Section Header** — Geist 32/600 또는 36/500·#ededed.
- **Icon Glyph** — 단색 #fff/#000·4px 컨테이너 radius·16–20px·~1.5px stroke.

## Do's and Don'ts
### Do
- 모든 primary 버튼·nav·pill은 9999px.
- display 헤드라인 DM Sans 72px/500·-2.52px (500 초과 금지).
- 다크 표면 본문은 #ededed, 흰 표면 본문은 #161616 (본문에 순수 #fff 금지).
- 모든 다크 표면 보더는 1px hairline(앱: white/10). 2px+·box-shadow 금지.
- warm→cool 그라데이션은 hero/spotlight에만. UI 컨트롤·카드 금지.
- element gap 8–16px, section gap 64–80px.
- Dusk Violet은 gradient wash에만.
### Don't
- box-shadow로 elevation 주지 말 것 (translucency·hairline·surface contrast로).
- 추가 브랜드 색 도입 금지 (2% colorfulness 유지).
- 카드 radius 4px 미만·42px 초과 금지 (24/40/42 sweet spot).
- hero 헤드라인 weight 700+ 금지.
- Geist를 24px 미만 본문에 쓰지 말 것 (13–18px는 DM Sans).
- floating nav를 viewport edge에 붙이지 말 것 (16–24px margin).
- solid #6b62f2를 버튼 fill·텍스트로 쓰지 말 것.

## Surfaces
| Level | Name | Value | Purpose |
|-------|------|-------|---------|
| 0 | Void Canvas | `#0a0a0a` | Page background |
| 1 | Graphite | `#161616` | Elevated panels — nav·dropdown·dark cards |
| 2 | Frosted Glass | `rgba(212,212,212,0.1)` | Translucent overlay panels(blur) |
| 3 | Snow White | `#ffffff` | Inverted surfaces — white CTA·white panels |

## Agent Prompt Guide
- text: #ededed(dark 본문) / #161616(white 위 본문)
- background: #0a0a0a(canvas) / #161616(elevated)
- border: white/10 (1px hairline)
- accent: #6b62f2 (gradient wash only)
- primary action: #ffffff filled pill

## Gradient System
1. **Hero Horizon** — amber/coral → cobalt, hero 전면 배경에만.
2. **Dusk Violet Wash** — 90deg, #6b62f2 0.565α 중앙 50% 밴드, 40/60% 투명. 다크 UI 하이라이트 스트립.
3. **Radial Spotlight** — #6b62f2 중심 → #fff, 제품 리빌 스팟. 카드·버튼·텍스트엔 금지, hero/accent/spotlight만.

## Similar Brands
Linear · Vercel · Raycast · Arc Browser — dark canvas + monochromatic + pill controls + hairline borders + weight-500 restraint + Geist/DM Sans pairing.

## CSS Custom Properties (핵심)
```css
:root {
  --color-void-canvas:#0a0a0a; --color-graphite:#161616; --color-frosted-glass:#d4d4d4;
  --color-snow-white:#ffffff; --color-bone:#ededed; --color-ash:#c2c2c2;
  --color-slate:#686868; --color-smoke:#b2b2b2; --color-hairline:#e5e5e5; --color-dusk-violet:#6b62f2;
  --gradient-dusk-violet:linear-gradient(90deg,rgba(0,0,0,0),rgba(0,0,0,0) 40%,rgba(107,98,242,.565) 50%,rgba(0,0,0,0) 60%,rgba(0,0,0,0));
  --font-dm-sans:'DM Sans',Inter,system-ui,sans-serif; --font-geist:'Geist',Inter,system-ui,sans-serif;
  --radius-ui:10px; --radius-cards:24px; --radius-icons:4px; --radius-panels:42px; --radius-buttons:9999px; --radius-largecards:40px;
}
```
