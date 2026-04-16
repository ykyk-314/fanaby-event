# イベントID生成ルール変更：公演重複の解消

## Context

events.json で同一公演が重複レコードとして存在する。原因は2つ:

1. **タイトル不一致（5件）**: プロフィールページと劇場スケジュールで公演名に差異がある（例: "グランドバトルEAST" vs "グランドバトルEAST 第四部"）。`normalize_title()` では実テキスト差異を吸収できず、別IDが付与される。
2. **同一ID衝突（2件）**: 同日同タイトルで開始時間が異なる複数公演（昼夜公演等）が、start_timeがIDに含まれないため同一IDになる。

**今回は問題1+2のみ対応。** 複数芸人同公演問題（talent_idによる分離）は将来のデータモデル変更時に対応。

## 方針

ID生成キーから `title` を除外し、代わりに `venue` + `start_time` を使用する。

```
現在: SHA1(talent_id:date:normalize_title(title))[:8]
変更: SHA1(talent_id:date:venue:start_time)[:8]        ← venue/start_time が両方ある場合
      SHA1(talent_id:date:normalize_title(title))[:8]   ← フォールバック（venue/start_timeがnullの場合）
```

- title はソースによって揺れるが、venue と start_time は安定している
- フォールバックが発動するのはプロフィールのみイベント（劇場データなし）で、タイトル不一致問題が起きない単一ソースのケース

## 変更対象ファイル

### 1. `scripts/merge.py` （コア変更）

#### a. `make_event_id` 関数 (L60-63)
```python
def make_event_id(talent_id: str, event_date: str, title: str,
                  venue: str | None = None, start_time: str | None = None) -> str:
    """イベントID: SHA1(talent_id + date + venue + start_time) の先頭8文字。
    venue/start_time が不明な場合は normalized_title にフォールバック。"""
    if venue and start_time:
        key = f"{talent_id}:{event_date}:{venue}:{start_time}"
    else:
        key = f"{talent_id}:{event_date}:{normalize_title(title)}"
    return hashlib.sha1(key.encode()).hexdigest()[:8]
```

#### b. `_theater_key` 関数 (L152-153)
同じロジックに変更。venue/start_time を受け取って使用。

```python
def _theater_key(talent_id: str, event_date: str, title: str,
                 venue: str | None = None, start_time: str | None = None) -> str:
    if venue and start_time:
        return f"{talent_id}:{event_date}:{venue}:{start_time}"
    return f"{talent_id}:{event_date}:{normalize_title(title)}"
```

#### c. `build_event_from_profile` (L91-115)
`make_event_id` 呼び出しに `venue` と `start_time` を追加:
```python
"id": make_event_id(p["talent_id"], p["date"], p["title"],
                    venue=p.get("venue"), start_time=p.get("start_time")),
```

#### d. `_build_event_from_theater` (L182-203)
同様に `venue` と `start_time` を追加:
```python
"id": make_event_id(talent_id, te["date"], te["title"],
                    venue=te.get("venue"), start_time=te.get("start_time")),
```

#### e. `merge_theater_into_events` (L118-149) — インデックス構築と照合
プロフィールイベントのインデックス構築時:
```python
for i, ev in enumerate(events):
    key = _theater_key(ev["talent_id"], ev["date"], ev["title"],
                       venue=ev.get("venue"), start_time=ev.get("start_time"))
    event_index[key] = i
```

劇場イベント照合時:
```python
for tid in te["matched_talent_ids"]:
    key = _theater_key(tid, te["date"], te["title"],
                       venue=te.get("venue"), start_time=te.get("start_time"))
```

**照合上の考慮点**: プロフィール側のイベントは venue/start_time があれば新キー、なければタイトルベースのキーで登録される。劇場側は常に venue/start_time を持つため、プロフィール側が venue/start_time を持っていれば一致する。プロフィール側が venue/start_time を欠いている場合、劇場側のキーは `talent_id:date:venue:start_time` だがプロフィール側のキーは `talent_id:date:normalize_title` なので一致しない。

→ **デュアルインデックス戦略**: プロフィールイベントを2つのキーでインデックスに登録する。
1. venue+start_time がある場合: `talent_id:date:venue:start_time` で登録
2. 常に: `talent_id:date:normalize_title(title)` でも登録（セカンダリキー）

劇場イベント照合時は、まずプライマリキー（venue+start_time）で検索、なければセカンダリキー（title）で検索。

### 2. `docs/fliers/` — フライヤー画像のリネーム

IDが変わるイベントのフライヤーファイル名も変わる。
- `download_flyers` が `ev['id']` をファイル名に使用している (L236)
- ID変更時に旧ファイルが残り新ファイルが作成されるだけ（旧ファイルは孤立）
- → merge実行後、使われていない旧ファイルを削除するクリーンアップ処理を追加、または手動削除

### 3. `.claude/rules/scripts.md` — ドキュメント更新

ID生成ルールの記述を新仕様に更新:
```
- イベントID: `SHA1("{talent_id}:{date}:{venue}:{start_time}")[:8]`（venue/start_time不明時は `SHA1("{talent_id}:{date}:{normalize_title(title)}")[:8]`）
```

### 4. KV（Cloudflare Workers KV）

移行不要（リセットで対応）。IDが変わった分のステータスは再設定する。

## 変更しないファイル

| ファイル | 理由 |
|---|---|
| `scripts/build.py` | `ev["id"]` をそのまま使うだけ。ID形式は同じ8文字hex |
| `docs/assets/script.js` | `data-event-id` をそのまま使うだけ |
| `scripts/notify.py` | `talent_id` でグループ化するロジックに変更なし |
| `scripts/scrape_profile.py` | 出力形式に変更なし |
| `scripts/scrape_theater.py` | 出力形式に変更なし |
| `functions/api/viewing-statuses/[eventId].js` | EVENT_ID_RE は8文字hexチェックのみ。変更不要 |

## 検証手順

1. **変更前のデータ保存**: `data/events.json` のバックアップ
2. **merge.py を変更**
3. **merge.py を実行**: `python scripts/merge.py`
4. **重複解消の確認**:
   - 旧重複ペア5組（96103f25/ca0a7088, f14126e4/49fe60c2, 56f05ba0/d90772c1, de37ec09/b8995f47, f2ee595a/970cb0a5）が各1レコードに統合されていること
   - 旧ID衝突ペア2組（81ec0599×2, 919f2b19×2）がそれぞれ別IDを持つこと
   - 全IDがユニークであること
5. **build.py を実行**: `python scripts/build.py` でHTML生成確認
6. **孤立フライヤーの確認・削除**: `docs/fliers/` に旧IDのファイルが残っていれば削除
7. **ブラウザ確認**: ローカルでHTMLを開き、重複カードが消えていること
