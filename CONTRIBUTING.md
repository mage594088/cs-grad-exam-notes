# 如何貢獻

謝謝你願意花時間幫忙!這份筆記能一直維持正確、好讀,靠的就是大家的勘誤和補充。

## 回報錯誤 / 提出建議

請開一個 [Issue](../../issues),簡單說明:

- 是哪個檔案、哪個章節/頁面
- 錯誤內容是什麼,或你建議補充什麼

## 請不要做的事

- 請不要把筆記另外重新包裝上傳到其他平台或雲端硬碟再分享出去 —— 麻煩直接分享這個
  repo 的連結就好,這樣才能確保大家拿到的都是最新版本。
- 請不要把任何內容用於商業用途(詳見 [LICENSE](LICENSE))。

## 開發環境設置

如果想跑測試或 lint 工具,需要先建立虛擬環境並安裝套件:

Windows(PowerShell 或 Git Bash):

```bash
python -m venv venv
cd venv && ln -s Scripts bin && cd ..
venv/bin/pip install pytest flake8
```

macOS / Linux:

```bash
python3 -m venv venv
venv/bin/pip install pytest flake8
```

macOS/Linux 的 venv 原生就有 `bin/` 資料夾,不需要額外建符號連結,Windows 才需要上
面那個 `ln -s Scripts bin` 的步驟。裝好之後就能跑下面的 `Test:` 指令。

## Commit Message 格式

如果要送 PR,commit message 麻煩照這個格式寫:

```text
<type>: <一句話說明改了什麼,50 字元以內>

<可選:更詳細的說明>

- <具體變更 1>
- <具體變更 2>
```

`<type>` 從下面挑一個:

| type | 用途 |
| --- | --- |
| feat | 新增內容(例如新增一份筆記) |
| fix | 修正錯誤(錯字、算式錯誤等) |
| docs | 只改 README / CONTRIBUTING 這類說明文件 |
| test | 只改測試,沒改功能邏輯 |
| refactor | 重新整理內容,意思不變 |
| chore | 雜項(設定檔、專案結構調整等) |

如果你的改動有動到 `tools/` 底下的檢查工具,commit message 最後麻煩附上你跑過的測
試指令,例如:

```bash
Test: venv/bin/python -m pytest
Test: venv/bin/python -m flake8 tools tests
```

有任何問題,歡迎在 Issue 裡留言討論。
