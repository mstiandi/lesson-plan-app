# SPEC: v3.4 Vercel 函数超时修复

## 问题
POST /api/generate 和 POST /api/revise 在 Vercel 返回 500。
原因：DeepSeek API 调用耗时 10-30 秒，超过 Vercel Hobby Plan 默认 10 秒函数超时。

## 修法
Vercel Hobby Plan 支持最长 60 秒。创建 `vercel.json` 提升超时上限。

## 新建文件：`vercel.json`

```json
{
  "functions": {
    "routes/lesson.py": {
      "maxDuration": 60
    }
  }
}
```

## 验收
- [ ] `POST /api/generate` 在 Vercel 不再 500
- [ ] `POST /api/revise` 在 Vercel 不再 500
- [ ] 教案/教学计划/教学总结三种业务均可正常生成
