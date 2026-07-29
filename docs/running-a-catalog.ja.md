# カタログを建てる

[English](running-a-catalog.md) · 日本語

amenbo のプラグインカタログは、**静的ファイルを3つ置くだけ**です。サーバは要りません。公開する気のない
プラグインを社内に配る、というのがいちばん多い建て方です。

この文書は、その**カタログを建てる側**に向けたものです。プラグインそのものの書き方は
[プラグインを作る](writing-a-plugin.ja.md)にあります。

> 第三者カタログの登録は amenbo 2.0.0 から使えます。手元で `amenbo plugin catalog --help` が応えるか
> 確かめてください。

## 利用者から見えるもの

利用者は、あなたの `catalog.json` の URL で登録します。

```sh
amenbo plugin catalog add https://plugins.example.com/catalog.json --name "社内カタログ"
```

このとき amenbo は、その隣にある `catalog-key.pub` を取りに行き、**指紋を見せて同意を取り、その鍵を
pin します**。以後、そのカタログから入れるプラグインは**その鍵でだけ**検証されます。

```
https://plugins.example.com/catalog.json publishes a signing key:
  fingerprint 2F09ABE300368325
  Plugins installed from this catalog will be trusted on this key.
```

つまり登録はブックマークではなく、**信頼の根を1つ増やす行為**です。鍵を公開していないカタログも登録
できますが、閲覧できるだけで、そこからは何も install できません。

## 置く3つのファイル

同じディレクトリに並べます。amenbo は `catalog.json` の URL から、残りの2つを相対で導きます。

| ファイル | 中身 | 誰がいつ取るか |
| --- | --- | --- |
| `catalog.json` | 一覧の描画に要るものだけ | 全員が、閲覧のたびに1回（1時間キャッシュ） |
| `plugins/<name>.json` | install に要るもの（署名・checksum・設定・イベント） | 開いた／入れる1件だけ |
| `catalog-key.pub` | 署名鍵の公開半分 | 登録のとき1回 |

一覧と詳細を分けているのは、**署名が一覧でいちばん大きい**からです。閲覧しているだけの人が、全プラグイン
ぶんの署名を落とす必要はありません。

## `catalog.json`

封筒と、プラグイン1件ぶんのエントリです。

```json
{
  "catalog_v": 1,
  "generated_at": "2026-07-27T03:38:10Z",
  "plugins": [
    {
      "name": "helloctl",
      "desc": "社内のあれこれを1コマンドで",
      "author": "Example Corp",
      "repo": "example/helloctl",
      "os": ["macos"],
      "category": "workflow",
      "official": false,
      "featured": false,
      "added_at": null,
      "detail_sum": "sha256:5aa7ef29d87409ef9b83d6bc3998c18a67d843ca030381724207bb00e57ad0a9"
    }
  ]
}
```

- `catalog_v` は**封筒のバージョン**で、今は `1` です。amenbo は知らないバージョンのカタログを丸ごと拒否します。
  エントリにフィールドが増えるだけなら上がりません（古い amenbo は知らないキーを読み飛ばします）。
- `generated_at` は任意です。
- エントリが1件でも壊れていれば、**その1件だけ**が落ちます。カタログ全体は使えるままです。

**どの項目が一覧に行き、どれが詳細に行くかを、あなたが決める必要はありません。** `amenbo plugin validate`
に `--json` を付けると、manifest を `entry` と `detail` の2つに割って返します。集約はそれをそのまま
publish するだけです——この形なら、amenbo が後からフィールドを増やしても、あなたのスクリプトは直りません。

3つだけ、**カタログの持ち物**があります。amenbo は空で返すので、埋めるのは集約の側です。

| 項目 | 埋め方 |
| --- | --- |
| `detail_sum` | 書き出した詳細文書の SHA-256（`sha256:<hex>`）。**必須です**——利用者の amenbo は、一覧のこの値だけを見て「更新があるか」を判定します |
| `added_at` | そのプラグインが載った日。一覧の「新着」の軸で、無ければ「不明」として扱われます（git 履歴から採るのが素直です） |
| `featured` | そのカタログのおすすめ。使わないなら `false` のままで結構です |

`official` は**公式カタログの印**です。自分のカタログのエントリには書かないでください。

## `plugins/<name>.json`

install に要るものです。`name` だけが一覧と重複していて、これが2つの文書の継ぎ目になります。

```json
{
  "name": "helloctl",
  "url": "https://github.com/example/helloctl/releases/download/v1/helloctl-v1.tar.gz",
  "checksum": "sha256:e23f6791e6852331a4c4bf147e86d57e6088dcbffbf936f56ade7df8c0ca6d8f",
  "signature": "untrusted comment: signature from minisign secret key\nRUQlgzYA…\n",
  "payload_v": 1
}
```

`signature` は、**その URL が実際に返したバイト列**への minisign 署名です。manifest が書いた checksum を
信じて署名するのではなく、**落として、照合して、そのバイト列に署名します**。OS ごとに別のビルドを配る
なら、`assets` のキーごとに同じことをします。

配布物の `url` は **https** でなければなりません（`amenbo plugin validate` が入口で断ります）。
`catalog.json` 自身の URL は http でもかまいません——手元での試運転がそれです。

## 鍵を作る

署名するのは**あなたの CI** で、amenbo ではありません。amenbo 側に秘密鍵を触る面はありません。

```sh
minisign -G -p catalog-key.pub -s catalog.key
```

- **公開半分**（`catalog-key.pub`）を `catalog.json` の隣に置きます。
- **秘密鍵**（`catalog.key`）は CI のシークレットへ。ファイルのまま渡せないので、`base64` でくるみます
  （`base64 -i catalog.key | pbcopy`）。パスワードは別のシークレットに分けます。
- **指紋**は `catalog-key.pub` のコメント行に minisign が書いている16桁です
  （`untrusted comment: minisign public key 2F09ABE300368325`）。利用者が登録のときに見るのはこの文字列
  なので、**配布元のページや README にも載せておいてください**。突き合わせられます。

## 集約スクリプト

`plugins/*.yaml` を読み、`_site/` に3つのファイルを書き出す最小の形です。依存は amenbo と minisign
だけで、`amenbo plugin validate --json` が返した2つの文書をそのまま publish します。

```python
#!/usr/bin/env python3
"""plugins/ の manifest から、署名済みの amenbo プラグインカタログを作る。"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CATALOG_V = 1


def documents(amenbo, manifest):
    """manifest を amenbo に読ませ、割られた2つの文書を受け取る。

    どのフィールドがどちらの文書に行くかを決めるのは amenbo で、このスクリプトではない。
    amenbo が後からフィールドを増やしても、ここは直さずに済む。
    """
    proc = subprocess.run(
        [amenbo, "--json", "plugin", "validate", str(manifest)],
        capture_output=True,
        text=True,
    )
    report = json.loads(proc.stdout or "{}")
    if not report.get("ok"):
        sys.exit(f"{manifest}: {proc.stdout.strip() or proc.stderr.strip()}")
    return report["entry"], report["detail"]


def signed(distributable, label, key, password):
    """配布物を1つ落とし、manifest が宣言した digest と照合し、そのバイト列に署名する。"""
    with urllib.request.urlopen(distributable["url"], timeout=60) as response:
        data = response.read()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if digest != distributable["checksum"]:
        sys.exit(f"{label}: url が返すのは {digest} で、宣言は {distributable['checksum']}")
    with tempfile.TemporaryDirectory() as tmp:
        asset, signature = Path(tmp) / label, Path(tmp) / f"{label}.minisig"
        asset.write_bytes(data)
        subprocess.run(
            ["minisign", "-S", "-s", str(key), "-m", str(asset), "-x", str(signature)],
            input=f"{password}\n",
            text=True,
            capture_output=True,
            check=True,
        )
        return {"url": distributable["url"], "checksum": digest, "signature": signature.read_text()}


def encode(document):
    """2つの文書を同じ書き方で出す。detail_sum が「書いたバイト列そのもの」の digest になる。"""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugins-dir", type=Path, default=Path("plugins"))
    parser.add_argument("--out", type=Path, default=Path("_site"))
    parser.add_argument("--key", type=Path, required=True, help="署名に使う minisign 秘密鍵")
    parser.add_argument("--amenbo", default=os.environ.get("AMENBO_BIN", "amenbo"))
    args = parser.parse_args()
    password = os.environ.get("CATALOG_KEY_PASSWORD", "")

    (args.out / "plugins").mkdir(parents=True, exist_ok=True)
    entries = []
    for manifest in sorted(args.plugins_dir.glob("*.yaml")):
        entry, detail = documents(args.amenbo, manifest)
        # 公式バッジは amenbo チームのカタログのもの。ここで付けられるものではない。
        entry["official"] = False
        if detail.get("assets"):
            detail["assets"] = {
                platform: signed(asset, f"{entry['name']}-{platform}", args.key, password)
                for platform, asset in sorted(detail["assets"].items())
            }
        else:
            detail.update(signed(detail, entry["name"], args.key, password))
        text = encode(detail)
        (args.out / "plugins" / f"{entry['name']}.json").write_text(text)
        # 書き出した詳細文書の digest。利用者の amenbo が「別のビルドだ」と気づく唯一の材料。
        entry["detail_sum"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        entries.append(entry)
        print(f"ok {entry['name']}")

    catalog = {
        "catalog_v": CATALOG_V,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": entries,
    }
    (args.out / "catalog.json").write_text(encode(catalog))
    print(f"wrote {args.out}/catalog.json with {len(entries)} plugin(s)")


if __name__ == "__main__":
    main()
```

エラーは**その場で止める**形にしてあります。掲載が増えて「1件の URL が腐っただけでカタログが出せない」
のが困るようになったら、その1件を理由つきで落として先へ進む形へ変えてください。


## 同じバイト列は、二度目も同じに publish する

minisign の署名には、署名した時刻が入る。同じアセットを署名し直せば署名は別物になり、詳細ファイルも
`detail_sum` も動く。そして `detail_sum` は、利用者の amenbo が「このプラグインは新しいビルドになった」と
判断する唯一の材料になっている。publish のたびに全部を署名し直すカタログは、**何かを1つ載せるたびに、
全プラグインに更新が出たと全利用者へ言う**ことになる。

だから **バイト列が変わっていないなら、署名を持ち越す**。署名する前に、いま自分が publish している
そのプラグインの詳細ファイルを読み、アセットのダイジェストが同じなら、そこに載っている署名をそのまま使う。
持ち越す署名は、いまダウンロードしたバイト列に対して自分の公開鍵で検証してから使うこと——持ち越しは
そのバイト列についての主張であり、主張は確かめる価値がある。読めない・アセットが変わった・検証が通らない
——どれも署名し直すだけで、それは元々していたことでしかない。

署名が言うのは「このバイト列は自分の審査を通った」であって、いつ通ったかではない。前回の署名は、いまも
同じだけそれを支えている。

## GitHub Actions

`main` への push で建て直し、GitHub Pages へ置きます。**署名は merge のときだけ**——pull request の
実行に秘密鍵を渡さないでください。

```yaml
name: catalog

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: catalog
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      # manifest の規則は amenbo 本体が持っているので、CI にも amenbo が要ります。
      # `plugin validate` はまだリリース版に入っていないため、ソースから建てます。
      - uses: actions/checkout@v7
        with:
          repository: ShiroDoromoto/amenbo
          path: .amenbo-src
      - run: cargo build -p amenbo-cli
        working-directory: .amenbo-src

      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      - run: sudo apt-get update && sudo apt-get install -y --no-install-recommends minisign

      - name: Build the catalog
        env:
          AMENBO_BIN: ${{ github.workspace }}/.amenbo-src/target/debug/amenbo
          CATALOG_SIGNING_KEY: ${{ secrets.CATALOG_SIGNING_KEY }}
          CATALOG_KEY_PASSWORD: ${{ secrets.CATALOG_KEY_PASSWORD }}
        run: |
          set -euo pipefail
          # シークレットは base64 でくるんだ秘密鍵。実行が終われば RUNNER_TEMP ごと捨てられます。
          printf '%s' "$CATALOG_SIGNING_KEY" | base64 -d > "$RUNNER_TEMP/catalog.key"
          python3 scripts/build-catalog.py --key "$RUNNER_TEMP/catalog.key"
          cp catalog-key.pub _site/catalog-key.pub

      - uses: actions/upload-pages-artifact@v5
        with:
          path: _site

  publish:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
    steps:
      - uses: actions/configure-pages@v6
      - uses: actions/deploy-pages@v5
```

## 手元で試す

配る前に、利用者と同じ経路を1周できます。カタログ自身は http でよいので、静的サーバ1つで足ります。

```sh
python3 scripts/build-catalog.py --key catalog.key
cp catalog-key.pub _site/
(cd _site && python3 -m http.server 8765) &

amenbo plugin catalog add http://127.0.0.1:8765/catalog.json --name "社内カタログ" --yes
amenbo plugin catalog list      # 指紋が catalog-key.pub のものと一致するか
amenbo plugin install <name>
```

`--yes` は「指紋を見て同意した」を非対話で宣言するものです。付けなければ質問が出ます。

## 鍵を替えるとき

**利用者に再登録を求めることになります。** 登録時と違う鍵で署名された配布物を、amenbo は黙って
受け入れません。

```
Error: https://plugins.example.com/catalog.json now publishes a different key
(32701CC140855BC6, pinned: 2F09ABE300368325). amenbo will not accept it on the old
consent — unregister the catalog and register it again to trust the new key.
```

`amenbo plugin catalog remove <url>` してから `add` し直す——その1往復で、新しい指紋が**決める人の前に
出ます**。だから鍵の交換は、静かに済ませられる作業ではありません。**新しい指紋を先に告知してください。**

## amenbo がしないこと

- **カタログを作る道具は持ちません。** amenbo が持つのは検証だけで、秘密鍵を触る面はありません。
  利用者の端末で動く配布物に、署名する機能は入れない、という線です。
- **鍵の保管と失効に関与しません。** pin が守るのは「登録したときの鍵と同じか」だけです。その鍵が
  漏れていないことは、カタログを建てた側の責任です。
- **公式バッジは公式カタログのものです。** 第三者のカタログから来たプラグインは、amenbo の画面では
  **そのカタログの名前**で出ます。利用者が登録のときに付けた名前です。
