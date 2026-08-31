# 静的アセットを assets/ に集約し Cloudflare Access を bypass する

## Context

### 問題
iPhone Safari および PWA（ホーム画面に追加したアプリ）で、公演スケジュール画面のスタイルが一切適用されない。ヘッダーも含めて素の HTML として表示される。

### 原因（検証で裏付け済み）
サイト全体が Cloudflare Access で保護されているため、`<link rel="stylesheet">` による `assets/style.css` の取得リクエストが、認証 Cookie の確立前に飛ぶと Access のログイン画面 HTML を返してしまい、ブラウザが CSS として解釈できずスタイルが一切当たらない。

根拠として以下を確認済み：
- `settings.html` ではインライン `<style>` で定義した `.settings-section` 等は効くが、外部 `style.css` にしか定義がない `header` / `.settings-link` は効かない → CSS ファイル自体が取得できていない
- プライベートブラウザで先に `style.css` に直接アクセスして認証を通してから index.html を開き直すと、スタイルが正常に適用される → Cookie 確立の順序が原因
- 同じ理由で `site.webmanifest` も CORS エラーで取得失敗しており、PWA のインストール情報が読めていない

なお画像（`fliers/`・`talents/`）は現状正常に表示されているため、今回の変更対象に含めない。

### 制約
Cloudflare Access は **1 アプリケーションあたり最大 5 つの宛先（ホスト名＋パス）** しか登録できない。bypass が必要なファイルを個別に列挙すると 6 件以上になり上限を超える。

### 目指す状態
静的アセットを `docs/assets/` 配下に集約し、Access のパス指定ワイルドカード `assets/*` の **1 エントリ** で全アセットを bypass できるようにする。これにより PWA・Safari の双方で初回アクセス時からスタイルが正しく適用され、ホーム画面への追加も正常に機能する。

---

## Step 0（先行検証）: ワイルドカードの動作確認

**このステップを最初に行う。** 計画全体がパスのワイルドカード対応を前提にしているため、先に実機で確認して失敗リスクを潰す。

1. Zero Trust → Access → Applications で Self-hosted アプリを新規作成（例: `fanaby-event-assets`）
2. 宛先に `fanaby-event.pages.dev` / パス `assets/*` を設定
3. ポリシーを **Bypass**（Include は Everyone）で保存
4. iPhone Safari のプライベートブラウズで `https://fanaby-event.pages.dev/` を開き、**スタイルが最初から適用されるか**確認

- ✅ 適用された → ワイルドカードが有効。Step 1 以降へ進む
- ❌ 適用されない → ワイルドカードが効いていない可能性。この場合ファイル移動をしても解決しないため、Step 1 以降は実施せず方針を再検討する

---

## Step 1: 静的ファイルを docs/assets/ へ移動

`git mv` で以下 5 ファイルを移動する（Git の履歴を保つため `mv` ではなく `git mv` を使う）。

| 移動元 | 移動先 |
|---|---|
| `docs/site.webmanifest` | `docs/assets/site.webmanifest` |
| `docs/icon-192.png` | `docs/assets/icon-192.png` |
| `docs/icon-512.png` | `docs/assets/icon-512.png` |
| `docs/apple-touch-icon.png` | `docs/assets/apple-touch-icon.png` |
| `docs/favicon.svg` | `docs/assets/favicon.svg` |

## Step 2: HTML 4ファイルの参照パスを更新

`docs/index.html` / `docs/settings.html` / `docs/exclude-settings.html` / `docs/register.html` の **各ファイル 7〜10 行目**が完全に同一のブロックになっている。4ファイルとも同じ置換を適用する。

変更前:
```html
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/icon-192.png" type="image/png">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="manifest" href="/site.webmanifest">
```

変更後:
```html
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/assets/icon-192.png" type="image/png">
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
  <link rel="manifest" href="/assets/site.webmanifest">
```

絶対パス（先頭 `/`）を維持する。同ファイル内の `assets/style.css` は相対パスだが、そちらは既存のまま触らない（`docs/` 直下の HTML からは相対・絶対どちらでも同じ URL に解決されるため）。

## Step 3: site.webmanifest 内の icon パスを更新

`docs/assets/site.webmanifest` の `icons` 配列を絶対パスのまま書き換える。

変更前:
```json
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
```

変更後:
```json
    { "src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png" }
```

- **絶対パスを維持する理由**: マニフェスト自身が `/assets/` 配下に移るため、相対パス（`icon-192.png`）でも結果的に解決はするが、将来どちらかが移動した際に静かに壊れる。絶対パスなら配置場所に依存しない
- `start_url` は `/` のまま変更しない。アプリ本体は認証必須のままにする（bypass 対象は静的アセットのみ）

## Step 4: ドキュメント更新

- **`.claude/rules/cloudflare.md`** — 「Cloudflare Access 構成」セクションの bypass パス一覧に `/assets/*`（静的アセット全般）を追記し、なぜ bypass が必要かの理由（認証 Cookie 確立前に CSS/JS 取得が走ると失敗する）を1行添える
- **`.claude/rules/frontend.md`** — ファイル構成表に移動後のパスを反映
- **`.claude/rules/phase4.md`** 40行目 — PWA 基盤のファイル名記述を新パスに合わせる

## Step 5: Cloudflare Access 設定の整理（任意）

Step 0 で作成した `assets/*` bypass アプリが機能していれば、既存の `fanaby-event-register` アプリに登録済みの `assets/register.js` と `assets/style.css` の2エントリは冗長になる。削除すると宛先枠が2つ空く。動作確認が完了してから実施する。

---

## セキュリティ上の確認（実施済み）

`assets/*` を公開（bypass）することの妥当性を検証済み：

- `docs/assets/*.js` に秘密情報・認証情報は含まれない（grep で確認済み。ヒットしたのは `register.js` の Turnstile レスポンストークン受け渡し処理のみで、これは実行時のユーザー入力値であり秘密ではない）
- JS から API エンドポイントのパスは読み取れるが、**各エンドポイント自体は Access 認証で保護されたまま**変わらない
- `register.html` / `register.js` は元々 bypass 済みで公開前提
- CSS・アイコン・マニフェストはいずれも機密性を持たない

---

## 検証手順

Step 1〜4 をマージ・デプロイした後、以下を順に確認する。

1. **PC ブラウザ（シークレットウィンドウ）**
   - `https://fanaby-event.pages.dev/` を開き、認証後にスタイルが適用されること
   - DevTools の Network タブで `assets/style.css` が **200 / `text/css`** で返ること（`text/html` ならまだ認証で弾かれている）
   - `assets/site.webmanifest` が 200 で返り、コンソールに CORS エラーが出ないこと

2. **iPhone Safari（プライベートブラウズ）**
   - 事前に `style.css` へ直接アクセスせず、いきなり `https://fanaby-event.pages.dev/` を開いてスタイルが当たること（これが今回の本丸）

3. **PWA**
   - ホーム画面から既存アプリを **一度削除**（古いマニフェストがキャッシュされているため必須）
   - Safari で開き直して「ホーム画面に追加」
   - 起動してスタイルが適用されること、アイコンが正しく表示されることを確認

4. **回帰確認**
   - `settings.html` / `exclude-settings.html` / `register.html` の表示崩れがないこと
   - ファビコンが各画面で表示されること
   - フライヤー画像・芸人アイコン（`fliers/` `talents/`）が引き続き表示されること

## 補足・既知のリスク

- **legacy probing**: iOS Safari は `<link rel="apple-touch-icon">` が無い場合に限りルートの `/apple-touch-icon.png` を探しに行く。本プロジェクトは全 HTML に明示的な link タグがあるため実害はない。ルート `/favicon.ico` の probing も同様に低リスク
- **PWA の再インストールが必須**: マニフェストの URL が変わるため、既存のホーム画面アイコンは古い情報を保持し続ける。削除→再追加をしないと直らない
- `scripts/build.py` は `docs/schedule.html` のみを生成しており、今回移動する5ファイルには一切触れない（確認済み）
- GitHub Actions の `git add` 対象は `data/` `docs/schedule.html` `docs/fliers/` `docs/talents/` のみで `docs/assets/` を含まないため、CI が移動を巻き戻すことはない（確認済み）

## ブランチ

現在 `main` を checkout しているため、作業ブランチを切ってから着手する。命名規則は `feature/YYMMDD`。
