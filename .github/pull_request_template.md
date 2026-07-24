## 变更内容

<!-- 用 2–5 句话说明做了什么，以及为什么。 -->

Closes #

## 变更类型

- [ ] Agent / LLM 编排
- [ ] 热力学模型或后端
- [ ] 参数或物性证据
- [ ] API / 数据契约
- [ ] 前端
- [ ] 文档 / 工程配置

## 科学与安全检查

- [ ] LLM 没有直接生成或修改热力学数值
- [ ] 所有数值结果来自 `thermo_engine`
- [ ] 数值结果经过 `validate_equilibrium_result`
- [ ] 没有虚构参数、实验数据或引用
- [ ] 测试夹具没有进入生产参数仓库
- [ ] 没有提交 API Key、`.env`、数据库或日志
- [ ] 不适用；本 PR 不涉及科学计算或参数

## 契约同步

- [ ] Python Schema、FastAPI、前端类型和契约测试已同步
- [ ] 不适用；本 PR 没有修改公共数据契约

## 验证证据

```text
python -m pytest
ruff check .
ruff format --check .
mypy .
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

<!-- 粘贴实际运行结果；可选后端请注明环境和跳过原因。 -->

## 已知限制

<!-- 说明适用范围、未覆盖情况和后续 Issue。 -->
