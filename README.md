# 2026 玉山人工智慧挑戰賽

ETF 投資策略相關程式碼。

## 環境
- Python 3.11(Jupyter kernel: `esunaicup2026_py311`)
- 套件:`finlab`

```bash
pip install finlab
```

## FinLab 登入
使用瀏覽器互動式登入,憑證存於本機 `~/.finlab/credentials.json`:

```bash
python -m finlab login
```

## 內容
- `finlab_api_test.ipynb`:FinLab API 連線與資料測試
- `verify_dplan.ipynb`:D-Plan schema 驗證

## 注意
- `data/` 與 CSV/Parquet 檔不會被上傳(見 `.gitignore`),FinLab 資料請在本機自行下載。
- 請勿提交任何 token 或憑證。
