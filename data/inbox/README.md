# 歷史成分股匯入格式

將官方定期審核公告整理為 universe_membership.csv 後放入此資料夾（大型或原始檔不提交 Git）。

欄位必須完全符合以下順序：

universe,symbol,effective_from,effective_to,announced_on,source_url
TW50,2330,2024-01-02,2024-06-30,2023-12-15,https://official.example/review

- universe：`TW50` 或 `TWMC100`；不可將兩個指數混成同一股票池。
- symbol：四位數台股代號。
- effective_from／effective_to：該成分期間，格式為 YYYY-MM-DD；仍在成分中的期間可留白。
- announced_on：官方公告日，不能晚於生效日。
- source_url：原始官方公告或附件連結，必填。

匯入器會拒絕日期格式錯誤、公告晚於生效日，以及同一指數內同一股票期間重疊的紀錄。
