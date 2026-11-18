# SANDY (SANDEVISTAN)

APEX Legends 用の外部エイムアシスト。画面のピクセルをAIが読み、パッド入力で照準を寄せます。ゲームのメモリには触れません。

## 動作環境

- Windows 10 21H2 以降 / Windows 11 (64bit)
- DirectX 12 対応 GPU / VRAM 4GB 以上
- ViGEmBus (仮想パッドドライバ)
- XInput 対応コントローラ

## 構成

| ファイル | 内容 |
|---|---|
| pad_pass.py | 本体。画面取得・推論・入力 |
| tune.py | 調整UI |
| cfg.json | 設定 |
| apex_detect_v8n_v2.1.onnx | 推論用モデル |
| apex_detect_v8n_v2.1.pt | 学習済みモデル(元ファイル) |
| APEXAI.spec | PyInstaller 定義 |

## セットアップ

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-runtime.txt
.venv\Scripts\python pad_pass.py
```

コントローラを抜いた状態で起動し、仮想パッドが作られてから実機を接続します。

## ライセンス

GNU Affero General Public License v3.0 (LICENSE 参照)。

本ソフトウェアは Ultralytics YOLOv8 (AGPL-3.0) と、それで学習されたモデルを使用しています。詳細は NOTICE.md を参照してください。

本ソフトウェアの完全な対応ソースはこのリポジトリです。
