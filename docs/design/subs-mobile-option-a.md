# Subs Mobile View — Option A (single top bar)

Reference for implementing the consolidated mobile layout. Phone target 390×844; everything scales with `flex` so it holds on 360–430px widths.

## 1. Tokens

```css
:root {
  --bg:        #eef0f5;   /* page ground */
  --card:      #ffffff;
  --ink:       #151b33;   /* primary text */
  --muted:     #5b6478;   /* secondary text — 5.5:1 on white */
  --line:      #d9dde8;   /* borders / dividers */
  --ind:       #2f3f8f;   /* brand indigo (active tab, accents) */
  --ind-soft:  #e6e9f6;   /* indigo tint for icon wells / chips */
  --danger:    #9b2c2c;
  --font:      Lato, "Helvetica Neue", Arial, sans-serif;
  --r-card:    12px;
  --r-pill:    999px;
  --shadow-card: 0 1px 2px rgba(21,27,51,.06);
}
body { margin:0; font-family:var(--font); background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased; }
```

Load Lato weights 400 / 700 / 900:
`<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700;900&display=swap" rel="stylesheet">`

## 2. Layout shell

The old header (~190px) + bottom nav (~100px) + segmented control become one 56px bar. Page content starts at 56px and scrolls under it.

```html
<div class="shell">
  <header class="topbar">…</header>
  <main class="page">…</main>
</div>
```

```css
.shell  { min-height:100dvh; display:flex; flex-direction:column; }
.topbar { position:sticky; top:0; z-index:10; }
.page   { flex:1 1 0; min-height:0; overflow-y:auto; }
```

Use `100dvh` and `padding-bottom: env(safe-area-inset-bottom)` on `.page` so the Safari toolbar doesn't clip the last card. Once installed as a PWA (`display: standalone` in the manifest) the "Not Secure" strip disappears and you get the full height.

## 3. Top bar

```html
<header class="topbar">
  <a href="/account" class="logo" aria-label="Open account menu">
    <img src="/logo.png" alt="McGarey Construction">
  </a>
  <nav class="tabs" aria-label="Sections">
    <a href="/todos"   class="tab">            <svg …/> <span>To-Dos</span></a>
    <a href="/joblog"  class="tab" aria-current="page"> <svg …/> <span>Job Log</span></a>
    <a href="/tm"      class="tab">            <svg …/> <span>T&amp;M</span></a>
  </nav>
  <button class="menu-btn" aria-label="Menu"><svg …/></button>
</header>
```

```css
.topbar {
  height:56px; box-sizing:border-box; padding:0 12px;
  display:flex; align-items:center; gap:10px;
  background:var(--card); border-bottom:1px solid var(--line);
}
.logo { width:40px; height:40px; border-radius:10px; overflow:hidden; flex-shrink:0; }
.logo img { width:100%; height:100%; object-fit:cover; display:block; }

.tabs {
  flex:1 1 0; min-width:0;
  display:flex; gap:2px; padding:3px;
  background:var(--bg); border-radius:21px;
}
.tab {
  flex:1 1 0; min-width:0; height:36px; border-radius:18px;
  display:flex; align-items:center; justify-content:center; gap:6px;
  font-size:14px; font-weight:700; text-decoration:none;
  color:var(--muted); background:transparent;
}
.tab svg { width:18px; height:18px; stroke:currentColor; fill:none; stroke-width:2.2; }
.tab[aria-current="page"] { background:var(--ind); color:#fff; }

.menu-btn {
  width:40px; height:40px; border:0; background:none; border-radius:10px;
  display:flex; align-items:center; justify-content:center; color:var(--ink); flex-shrink:0;
}
```

Notes
- Touch targets: logo 40px, tabs 36px tall inside a 42px track, menu 40px — all ≥ 44px effective with the bar padding.
- Icons are 18px stroke SVGs (Lucide‑style: `square-check`, `calendar`, `file-text`, `menu`). Don't use emoji.
- On very narrow widths (≤360) drop the tab labels to icon-only with `@media (max-width:360px) .tab span { display:none }`.

## 4. Page title row

Replaces the company/user/sub block. Carries the sub name so context survives the header trim.

```html
<div class="page-head">
  <h1>Job Log</h1>
  <div class="ctx">Saul 1 · next 2 weeks</div>
</div>
```

```css
.page-head { padding:14px 16px 8px; display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.page-head h1 { margin:0; font-size:24px; font-weight:800; letter-spacing:-.2px; }
.ctx { font-size:13px; font-weight:600; color:var(--muted); white-space:nowrap; }
```

Per page: Job Log → `Saul 1 · next 2 weeks`; T&M → `Saul 1 · 3 drafts`; To‑Dos keeps its To‑Dos / Mentions toggle instead of a title.

## 5. Job Log rows and install cards

```css
.day { display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-bottom:1px solid var(--line); }
.day b { font-size:16px; font-weight:800; }
.day span { font-size:14px; color:var(--muted); }
.day.today { border-bottom:2px solid var(--ind); }
.day.today b { color:var(--ind); }

.install {
  background:var(--card); border-radius:var(--r-card); border-left:4px solid var(--ind);
  padding:14px 14px 12px; display:flex; flex-direction:column; gap:8px; box-shadow:var(--shadow-card);
}
.install .num    { font-size:17px; font-weight:800; color:var(--ind); }
.install .status { font-size:12px; font-weight:700; border:1px solid var(--line); border-radius:8px; padding:4px 10px; }
.install .meta   { display:flex; gap:10px; align-items:center; font-size:14px; color:var(--muted); }
.install .hours  { color:var(--ink); font-weight:700; display:inline-flex; gap:4px; align-items:center; }
.dot { width:10px; height:10px; border-radius:5px; background:#3b6de0; display:inline-block; }
```

Card list wrapper: `display:flex; flex-direction:column; gap:10px; padding:12px 0;` inside a `padding:0 16px` container.

## 6. T&M tickets + FAB

```css
.ticket {
  display:flex; flex-direction:column; gap:8px; padding:16px;
  background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-card);
  text-decoration:none; color:var(--ink);
}
.ticket .num  { font-size:17px; font-weight:800; }
.ticket .pill { font-size:12px; font-weight:700; background:var(--bg); border-radius:var(--r-pill); padding:5px 12px; }
.ticket .sub  { display:flex; justify-content:space-between; font-size:14px; color:var(--muted); }

.fab {
  position:fixed; right:16px; bottom:calc(24px + env(safe-area-inset-bottom));
  width:56px; height:56px; border-radius:28px; border:0;
  background:var(--ind); color:#fff; box-shadow:0 6px 16px rgba(47,63,143,.35);
  display:flex; align-items:center; justify-content:center;
}
```

## 7. To‑Dos / Mentions toggle + empty state

```css
.seg { padding:12px 16px 4px; display:flex; gap:8px; }
.seg a { flex:1; height:38px; border-radius:10px; display:flex; align-items:center; justify-content:center;
         font-size:15px; font-weight:700; color:var(--muted); text-decoration:none; }
.seg a[aria-current="page"] { background:var(--card); border:1px solid var(--line); color:var(--ink); font-weight:800; }
.badge { margin-left:8px; min-width:20px; height:20px; padding:0 6px; border-radius:10px;
         background:var(--ind); color:#fff; font-size:12px; display:inline-flex; align-items:center; justify-content:center; }

.empty { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; padding:0 32px; text-align:center; }
.empty .well { width:56px; height:56px; border-radius:28px; background:var(--ind-soft); color:var(--ind); display:flex; align-items:center; justify-content:center; }
.empty h2 { margin:0; font-size:18px; font-weight:800; }
.empty p  { margin:0; font-size:14px; color:var(--muted); line-height:1.4; }
```

## 8. Account sheet (behind the logo / menu button)

Holds what left the header: company, signed‑in user, active sub with a Switch action, and sign out.

```html
<div class="scrim"></div>
<section class="sheet" role="dialog" aria-label="Account">
  <div class="grab"></div>
  <div class="who">
    <img src="/logo.png" alt="">
    <div><b>McGarey Construction</b><span>Daniel McGarey · signed in</span></div>
    <button class="close" aria-label="Close">×</button>
  </div>
  <div class="viewing">
    <div><small>Viewing as</small><b>Saul 1</b></div>
    <a class="switch" href="/subs">Switch</a>
  </div>
  <a class="row" href="/crew">Crew &amp; contacts</a>
  <a class="row" href="/notifications">Notifications</a>
  <a class="row danger" href="/signout">Sign out</a>
</section>
```

```css
.scrim { position:fixed; inset:0; background:rgba(21,27,51,.45); }
.sheet {
  position:fixed; left:0; right:0; bottom:0;
  background:var(--card); border-radius:20px 20px 0 0;
  padding:10px 20px calc(32px + env(safe-area-inset-bottom));
  box-shadow:0 -8px 30px rgba(21,27,51,.25);
}
.grab   { width:40px; height:4px; border-radius:2px; background:var(--line); margin:0 auto 10px; }
.who    { display:flex; align-items:center; gap:14px; padding:6px 0 14px; border-bottom:1px solid var(--line); }
.who img{ width:48px; height:48px; border-radius:12px; object-fit:cover; }
.who b  { display:block; font-size:18px; font-weight:900; }
.who span { font-size:14px; color:var(--muted); }
.viewing{ display:flex; justify-content:space-between; align-items:center; padding:14px 4px 10px; border-bottom:1px solid var(--line); }
.viewing small { display:block; font-size:12px; font-weight:700; color:var(--muted); letter-spacing:.6px; text-transform:uppercase; }
.viewing b { font-size:18px; font-weight:800; }
.switch { height:36px; padding:0 14px; border-radius:18px; background:var(--ind-soft); color:var(--ind); font-size:14px; font-weight:700; display:flex; align-items:center; text-decoration:none; }
.row    { display:flex; align-items:center; gap:14px; padding:14px 4px; border-bottom:1px solid var(--line); color:var(--ink); font-size:16px; font-weight:700; text-decoration:none; }
.row.danger { color:var(--danger); border-bottom:0; padding-top:16px; }
```

Open it with a real `<dialog>` or a state flag; trap focus and close on scrim tap / Escape.

## 9. Before → after

| | Before | After |
|---|---|---|
| Fixed chrome (header + tabs + nav) | ~290px | 56px |
| Job Log days visible before scroll (844px phone) | 5 | ~9 |
| Company / user / sub | always on screen | title row (sub) + account sheet |
| Logo | none | 40px in top bar, 48px in sheet |

Design canvas with the four screens: https://claude.ai/artifact/K1dJ69zPA7Jj8CsA5hECLP
