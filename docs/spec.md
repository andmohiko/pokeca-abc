# ポケカABC（Pokémon TCG AI Battle Challenge）

## コンテスト概要

**「AIはポケモンカードゲームを超えられるか」** をテーマにした、ポケカで対戦するAIエージェントの開発コンテスト。

| 項目 | 内容 |
|---|---|
| 正式名称 | Pokémon Trading Card Game AI Battle Challenge |
| 略称 | ポケカABC / PTCGABC |
| 主催 | Kaggle |
| 共催 | 株式会社ポケモン、HEROZ株式会社、株式会社松尾研究所 |
| 協力 | Google、NVIDIA |
| 参加費 | 無料 |
| 参加形態 | 個人またはチーム（最大5名） |
| 公式サイト | https://ptcg-abc.pokemon.co.jp/ |

## 大会構成

### 第一ラウンド（2部門制）

| | シミュレーション部門 | ストラテジー部門 |
|---|---|---|
| 期間 | 2026/6/16 20:00 〜 8/17 8:59（JST） | 2026/6/16 20:00 〜 9/14 8:59（JST） |
| 提出物 | AIエージェント（Pythonコード） | 戦略ロジックのレポート |
| 提出回数 | 1日5回まで | 1チーム1回 |
| 賞金 | なし | 1〜8位: 各$30,000 |
| Kaggleページ | https://www.kaggle.com/competitions/pokemon-tcg-ai-battle | https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy |

### 第二ラウンド

- ストラテジー部門上位8チームが進出
- 1位: $50,000、2位: $30,000
- 2026年末以降開催予定

## 対戦ルール

- ポケカの対戦ルールをベースに、本大会用に独自調整
- 使用可能カード: **主催者指定リストのみ**（約2,000種）
- 持ち時間: **最大10分**（時間切れ＝敗北）
- デッキ: 60枚構成（通常のポケカルール準拠）

## カードプール

Kaggleのストラテジー部門のDataタブからダウンロード可能:
- `Card_ID_List_EN.pdf` — 英語版カードリスト
- `Card_ID_List_JP.pdf` — 日本語版カードリスト
- 各カードにはIDが振られており、コード内ではこのIDで扱う

https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/data

## 開発者がやること

### 1. AIエージェントを書く

**Pythonで `main.py` を書く。**

エージェントは `agent(obs_dict: dict) -> list[int]` という関数。
盤面情報（observation）を受け取り、選択肢のインデックスのリストを返す。

```python
def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)

    # 初回呼び出し → デッキリスト（カードID×60）を返す
    if obs.select is None:
        return my_deck

    # 以降 → 行動のインデックスリストを返す
    select = obs.select
    options = select.option  # 選択可能な行動一覧
    # ... スコアリングなどで最適な行動を選ぶ ...
    return [best_option_index]
```

### 2. デッキを組む

`deck.csv` にカードIDを1行1枚、計60行で記述する。

### 3. 提出する

`main.py` + `cg/` + `deck.csv` を `submission.tar.gz` にまとめてKaggleに提出。

---

## エージェントの設計

### 基本フロー

```
盤面情報(obs_dict)
  → Observationオブジェクトに変換
  → 選択肢一覧(select.option)を取得
  → 各選択肢にスコアを付ける
  → 最高スコアの行動を返す
```

### 選択肢の種類（OptionType）

| OptionType | 説明 |
|---|---|
| `PLAY` | 手札からカードをプレイ |
| `EVOLVE` | ポケモンを進化させる |
| `ATTACH` | エネルギー/道具を付ける |
| `ATTACK` | ワザを使う |
| `RETREAT` | にげる |
| `ABILITY` | 特性を使う |
| `CARD` | カードを選択する（サーチ、トラッシュ等） |
| `YES` / `NO` | はい/いいえの選択 |
| `NUMBER` | 数値の選択 |
| `ENERGY_CARD` / `ENERGY` | エネルギーの選択（にげるコスト等） |

### 実装アプローチ

1. **ルールベース**（推奨スタート地点）
   - if文でカードごとに優先度をハードコード
   - サンプルコードが公開されている
2. **機械学習 / 強化学習**
   - 盤面を特徴量化して学習させる上級アプローチ

### スコアリングの設計思想（サンプルコードより）

スコアは「行動の強さ」ではなく **「ターン内での実行順序の優先度」** を表す:

| 行動 | スコア帯 | 理由 |
|---|---|---|
| 進化 | 30000〜70000 | 先に進化すると後の行動を制御しやすい |
| アイテム使用 | 40000〜80000 | 盤面を整えてから攻撃 |
| サポート使用 | 14000〜35000 | 1ターン1枚制約 |
| エネルギー付け | 20000前後 | 攻撃準備 |
| 攻撃 | attackId値（低い） | ターン最後の行動 |

---

## 主要API（cg-lib）

### データ型

| クラス | 説明 |
|---|---|
| `Observation` | 盤面全体の情報 |
| `State` | 現在の対戦状態 |
| `Pokemon` | 場のポケモン（HP、エネルギー、道具等） |
| `Card` | カード情報 |
| `SelectContext` | 何の選択を求められているか |
| `OptionType` | 選択肢の種類 |

### よく使う関数

```python
from cg.api import (
    to_observation_class,  # obs_dictをObservationに変換
    all_card_data,         # 全カードデータ取得
    AreaType,              # 場所の種類（手札、山札、ベンチ等）
    CardType,              # カードの種類（ポケモン、トレーナーズ等）
    LogType,               # ログの種類
    SelectContext,         # 選択コンテキスト
    OptionType,            # 選択肢の種類
)
```

### Observationの構造

```
obs.current          → State（現在の盤面）
  .yourIndex         → 自分のプレイヤーインデックス（0 or 1）
  .turn              → 現在のターン数
  .players[i]        → PlayerState
    .hand            → 手札のカード一覧
    .active          → バトル場のポケモン
    .bench           → ベンチのポケモン一覧
    .discard         → トラッシュ
    .prize           → サイド
    .deckCount       → 山札の枚数
    .asleep          → ねむり状態か
    .paralyzed       → マヒ状態か
  .stadium           → スタジアムカード
obs.select           → 今何を選ぶべきか
  .context           → SelectContext（選択の種類）
  .option            → 選択可能な行動リスト
  .minCount          → 最低選択数
  .maxCount          → 最大選択数
  .effect            → 効果を発動したカード
  .contextCard       → コンテキストカード
  .deck              → デッキが見えている場合のカード
  .remainDamageCounter → 残りダメカン数
obs.logs             → ログ一覧
```

---

## フォルダ構成

```
pokeca-abc/
├── .venv/              # uv が自動管理
├── .python-version
├── pyproject.toml      # 依存管理
├── uv.lock
├── cg/                 # cg-lib（API・型情報）
├── main.py             # エージェント本体
└── deck.csv            # デッキリスト（カードID×60行）
```

## 開発サイクル

```
① ローカルでmain.pyを編集
  ↓
② Kaggle Notebookにコピペして対戦テスト
  ↓
③ ロジック修正 → ①に戻る
  ↓
④ 満足したら提出
```

## 参考リンク

必要があれば下記のドキュメントに書かれているURLを参照し、必要な情報を取得すること

@docs/references
