# fanaby-event

指定芸人の公演スケジュールを自動収集・通知・表示する個人用Webアプリ。
**無料・無課金で完結することが最重要。**

## カスタマイズ方針
- `data/config.json` が設定の起点。芸人・劇場・除外タイトルはここで管理する
- `docs/assets/`（style.css / script.js）は静的ファイル。`build.py` は触れない
- `data/events.json` は過去イベントも保持（carry-over）。削除・上書きに注意

## 技術スタック
| レイヤー | 技術 |
|---|---|
| スクレイピング | Python 3.11 + Selenium 4.21.0 |
| 設定管理 | python-dotenv 1.0.1 |
| CI/CD | GitHub Actions（JST 17:03 / 22:03 定期実行） |
| ホスティング | Cloudflare Pages（Cloudflare Access で認証） |
| 通知 | Gmail SMTP |

## コマンド
| 用途 | コマンド |
|---|---|
| プロフィールスクレイプ | `python scripts/scrape_profile.py` |
| 劇場スクレイプ | `python scripts/scrape_theater.py` |
| マージ・差分検出 | `python scripts/merge.py` |
| メール通知 | `python scripts/notify.py` |
| HTML生成 | `python scripts/build.py` |

## ディレクトリ構造
| パス | 役割 |
|---|---|
| `scripts/` | Pythonスクリプト群（実行順: scrape→merge→notify→build） |
| `data/events.json` | スクレイピング結果（Git管理・過去分も保持） |
| `docs/` | Cloudflare Pages 配信ディレクトリ |
| `docs/assets/` | 静的CSS/JS（Git管理・build.py は変更しない） |
| `docs/fliers/` | フライヤー画像（merge.py がDL・Git管理） |

## ブランチ戦略
```
main ←── feature/YYMMDD （機能開発・PRでマージ）
```
- ブランチ命名: `feature/YYMMDD`（例: feature/260402）

## 行動原則
- 無料・無課金の制約を常に意識する（Cloudflare Workers KV/D1 は無料枠内で検討）
- Selenium は `webdriver-manager` 不使用。`webdriver.Chrome(options=options)` のみ記述
- `docs/assets/` を変更する際は `build.py` の動作に影響がないか確認する
- 3ステップ以上の変更は Plan モードで開始する
- コンテキストが逼迫したら区切りを提案する
- 仕様は `.claude/rules/` を参照
