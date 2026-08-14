---
name: nsight-profiling
description: nsys / ncu で GPU・MPI アプリをプロファイルする実践パターン。外部遮断クラスタでの debuginfod ハング対策、mpiexec 下へのランク別ラッパ注入、ncu のリプレイ・カーネル限定・採取窓制御、Grid Size を指紋にした部分問題の分類、Long Scoreboard によるレイテンシ律速判定、CLI だけでの読み出し。GPU アプリのプロファイルを取る・読む・律速を判定するときに適用。
user-invocable: true
---

# Nsight Systems / Compute の実践プロファイリング

対象は任意の GPU / MPI アプリケーション。CLI のみ・計算ノードが外部遮断、という
HPC クラスタの典型環境を前提にする。

## 鉄則

1. **シンボル解決を切ってから測る。** 外部遮断ノードでは debuginfod 待ちで永久ハングする
2. **通信カーネル（NCCL / NVSHMEM 等のピア待ち型）を ncu の対象にしない。** リプレイ直列化でデッドロック
3. **律速判定は分岐一回**: DRAM% と SM% を比べ、高い方が 80% 超ならそれが結論。両方 <50% のときだけストール解析へ
4. **必ず検算を入れる**: 起動数・Grid の比・転送量の理論値照合。合わなければ同定や前提を疑う

---

## nsys

### 配置規約とラッパ注入

| 形 | 使える範囲 |
|---|---|
| `nsys profile ... mpiexec app` | 1ノードのみ（リモートランクを追えない）。全ランク1レポート |
| `mpiexec <ラッパ> app`（標準） | ノード数不問。ランク毎1レポート |

```sh
#!/bin/bash  # ラッパ: 対象ランクだけ nsys を挟んで実体を exec
R=${OMPI_COMM_WORLD_RANK:-0}       # Slurm 直起動なら SLURM_PROCID、MPICH なら PMI_RANK
case ",$PROF_RANK," in
  *,all,*|*",$R,"*) ;;
  *) exec "$REAL_BIN" "$@" ;;
esac
exec nsys profile --trace=cuda,nvtx,nccl --sample=none \
  --resolve-symbols=false --delay=$SKIP_SEC \
  -o "$OUT/rank$R" "$REAL_BIN" "$@"
```

- 対象がスクリプト → numactl → 実体のような**起動連鎖**を持つ場合、シェルの fork を
  nsys に追跡させるより、**実体の直前**にラッパを挟むのが確実。
  ランチャスクリプトに実行体の差し替えオプションがあればそこへ、無ければ
  実体バイナリをリネームして同名のラッパを置く方法もある
- 複数ノードでは各ノードの代表を 1 ランクずつ（例: ランク 0 と最終ノードの先頭）採ると
  ノード間の非対称が見える。全ランク採取はレポートが巨大化するので絞るのが既定

### 落とし穴

- **debuginfod ハング**: `export DEBUGINFOD_URLS=` + `--resolve-symbols=false`。
  症状は「アプリは完走して正常出力もあるのに `Press Ctrl-C to stop symbol files downloading`
  のまま停止」。**起動失敗に見えるが実は終了処理の停止** — 誤診しやすい。
  CUDA カーネル名は CUPTI 由来なので、シンボル解決を切っても失わない
- **`--duration` は使わない**: `--kill` の既定が sigterm で、満了時にアプリごと終了させられ
  最終出力を失う。定常状態だけ採るには `--delay=秒` で開始側を切る
- ウォームアップ実行にはプロファイルを掛けない（終了処理が走るたびにハング機会が増え、
  失敗時に「ウォームアップでハング」という誤った見え方をする）

### 読み出し（CLI で完結）

```sh
nsys stats --report cuda_gpu_kern_sum --format table rank0.nsys-rep  # 他: nvtx_sum / cuda_api_sum
nsys analyze rank0.nsys-rep                        # ルールベース自動診断
# stats が生成する .sqlite に SQL。カーネルは CUPTI_ACTIVITY_KIND_KERNEL（start/end は ns）
# GROUP BY cast(start/1e9 as int) で秒毎 GPU 占有率 = テキスト版タイムライン
```

SQLite でカーネル名を引くときは **`JOIN StringIds ON k.demangledName = s.id`** を使う。
`shortName` は関数の基底名だけで、`cutlass::device_kernel<Gemm...>` のようなテンプレート
カーネルが LIKE 照合から漏れる（集計が静かにゼロになる）。

---

## ncu

### 前提と採取

- **権限確認**: 計算ノードで `grep RmProfilingAdminOnly /proc/driver/nvidia/params` が 0 か。
  1 だと `ERR_NVGPUCTRPERM`。「このサイトでは ncu 不可」という古い記録は実機で検証し直す
- **リプレイ方式**: HW カウンタは一度に少数しか読めないため、同一起動をメモリ巻き戻し付きで
  複数回再実行する。アプリ全体の実行は目に見えて遅くなる（実測例で 2 割減）が、
  各パスは同一条件なので計測値は正確。アプリの最終出力も通常どおり得られる
- `-k "regex:a|b"` で対象カーネル限定（**必須**、鉄則2）。`-s N -c M` は
  **マッチした起動の通し番号**に対する窓 — 時間・Grid サイズ・フェーズでは切れない。
  初期化や最適化フェーズは `-s` で読み飛ばす
- **kernel replay（既定）が効かないアプリがある。本計画の前に1カーネルのスモークテストを。**
  リプレイは対象カーネルが触るデバイスメモリを退避（backing store）してから再実行するため、
  **デバイスメモリをほぼ使い切るアプリや VMM（cuMemCreate/cuMemMap）系の特殊確保を持つアプリでは
  退避が失敗**し、どのカーネルでも `LaunchFailed` になる。
  症状はカーネルにより 0% 失敗 / 2パス目失敗と揺れるが原因は同一層
- **失敗したら必ず `/tmp/nsight-compute-*.log`（計算ノード）を回収して読む** — 真因が書いてある
  （例: `Allocation failed` / `Failed to find memObj` / `Failed to optimize backing store`）。
  症状からの消去法推定は誤りやすい（通信ライブラリを疑い、単体テストで棄却された実例あり）。
  切り分けは最小アプリの判定実験で行う
- **回避策: `--replay-mode application` + 1パスメトリクス**。
  メモリ退避を廃しアプリ全体を再実行するモードで、退避起因の失敗を原理的に回避する。成立条件は3つ:
  ①**1ランク実行**（アプリ再実行は多ランク MPI と非両立）
  ②**起動列を決定的に**（時間予算型の内蔵ベンチ・ウォームアップを無効化。揺れると
  `Unexpected number of profiled kernels`）
  ③**1パスに収まる `--metrics` に絞る** — 再実行1回で完結し実行間マッチング自体が不要
  （`sm__throughput` 等の複合メトリクスは多パス化して不可）。
  1パスで通る実績のある組: `gpu__time_duration.sum` + `dram__throughput.avg.pct_of_peak_sustained_elapsed`
  （+ `sm__warps_active.avg.pct_of_peak_sustained_active` まで可）。
  `--app-replay-match / --app-replay-mode`（relaxed 等）というマッチング調整もあるが、
  非決定性が残ると relaxed でも失敗した — **1パス化が確実**。
  フルセット相当はメトリクス種を変えた複数実行を「カーネル名+Grid+起動順」で手動合成する。
  検証済み: 重複測定した duration の実行間差 <1%、デバイスメモリ 8 割を確保した状態でも成立、
  kernel replay で失敗する種類のカーネル（クラスタ協調 GEMM 等）も計測できた
- `-k` は `--kernel-name-base demangled` と併用（`cutlass::device_kernel<Gemm...>` の
  関数ベース名は `device_kernel` で、既定照合では正規表現に掛からない）
- それも不可なら nsys sqlite のフェーズ分析（時間ビン集計・grid 推移・ストリーム並行度）
- **低 warp 占有 ≠ 異常**: warp-specialized カーネル（近年の cutlass GEMM 等）は少数ワープが
  TMA・Tensor コアを非同期駆動する設計で、占有 10% 前後が正常。占有率で良否を判定しない
- `--set` は2段構え: `basic`（SOL/Launch/占有率、約4パス）で律速判定 →
  疑いのあるカーネルだけ `full`（ストール内訳、約10倍）か `--section WarpStateStats`、
  最軽量は `--metrics smsp__average_warps_issue_stalled_long_scoreboard_per_issue_active.ratio,smsp__average_warp_latency_per_inst_issued.ratio`

### 読み出し

```sh
ncu --import x.ncu-rep --print-summary per-kernel   # カーネル別 min/max/avg（最初に見る）
ncu --import x.ncu-rep --csv --page details         # インスタンス単位（Grid Size 列付き）
ncu --import x.ncu-rep --page raw | grep <生メトリクス名>
```

**per-kernel サマリの Min/Max はメトリクスごとに独立** — 「DRAM 最小のインスタンスは
SM 最大だった」のような結合は読み取れない。インスタンス間のペア分析は必ず `--csv` で。

---

## 応用パターン

- **Grid Size は部分問題の指紋**: `<<<grid, block>>>` は起動メタデータとして CUPTI が常時記録
  するので、カーネル内部やソースが見えなくても外から分かる。同じカーネルが問題サイズを変えて
  繰り返し呼ばれるアプリ（多重格子の階層、AMR、バッチ処理の粒度違い等）では、
  CSV の Grid 列でインスタンスを分類してから集計する。**分類せず平均すると別 regime が混ざる**
- **nsys = 量 × ncu = 質**: 時間配分は nsys sqlite の `GROUP BY gridX`（全起動の悉皆集計）、
  律速判定は ncu のインスタンス分析（標本）。両者を Grid Size で突き合わせ、
  時間加重で結論を出す
- **レイテンシ律速の判定式**: `Stall Long Scoreboard ÷ Warp Cycles Per Issued Instruction > 50%`
  かつ DRAM 未飽和。details ページの OPT 診断文が割合まで計算してくれる。
  ただし**充填不足（Waves Per SM < 1）はワープのストール統計に現れない** —
  そちらは Launch Statistics 側で判定する（律速の種類で見る指標が変わる）
- **オーバーラップの証明は区間交差で**: 延べ時間の総和 > 経過時間は「何かが並行」しか示さない
  （計算同士の並行と区別できない）。全カーネル区間をスイープラインで「計算のみ/両方/通信のみ/空き」に
  分解すると隠蔽率と露出通信が直接出る。**干渉コストの検証**は同一 Grid のカーネルを
  「通信と重なった群 / 重ならなかった群」に分けて平均時間を比較する（差が数%なら隠蔽は実質無害）
- **転送量の逆算**: `DRAM% × Duration × ピーク帯域` を理論バイト/要素で割ると仕事量を推定できる。
  「この起動列は同じ計算量のはず」という前提の検算に使う — 実測例では均等と思われていた
  仕事分割が 25 倍不均等だったことをこの方法で検出した

## 適用実績・関連

- 理研 GB200 の HPCG 測定（2026-08-05、ジョブ 14412〜15228）で全パターンを実証。
  HPCG 固有の数値・オプション・ラッパ注入口（`--exec-name`）は `nvidia-hpc-benchmarks` スキル §5
