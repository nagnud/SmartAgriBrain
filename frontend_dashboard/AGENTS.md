# 工程与 GitHub 推送约束

本文件适用于在 `pro` 目录及其子目录中工作的所有代码 agent。

## 唯一源代码目录

- `pro` 是前端及配套后端代码的唯一开发源。
- `.push-cache/` 是持久化 Git 推送队列，不是开发目录，不得手工清空、覆盖、重建或格式化。
- `SmartAgriBrain/` 是历史嵌套检出目录，不是开发源，不得把其中内容反向覆盖到 `pro`。
- 推送脚本只把 `pro` 的受控快照镜像到远端仓库 `feature/frontend` 分支下的 `frontend_dashboard/`。

## 受保护的推送机制

- 主入口是 `scripts/git/push-frontend.bat`，核心实现是 `scripts/git/push-frontend.ps1`。
- 不得删除、改名、复制覆盖或改回 HTTPS/token 认证。
- 推送必须继续使用 `ssh://git@ssh.github.com:443/nagnud/SmartAgriBrain.git` 和用户目录中的专用 SSH 密钥。
- 不得修改用户的全局 Git 或 SSH 配置；连接参数必须限制在脚本进程内。
- 禁止使用 `git push --force`、`--force-with-lease` 或任何可能覆盖远端历史的操作。
- 网络失败时必须保留 `.push-cache` 中所有待推送提交，并明确说明尚未上传。
- 修改远端地址、目标分支、源目录或 `frontend_dashboard` 映射前，必须先获得用户明确同意，并同步更新本文件和 `scripts/README.md`。

## 凭据与忽略规则

- 禁止在工程中保存 GitHub token、密码、SSH 私钥或其他真实凭据。
- `.env`、数据库、日志、私钥、`.push-cache/`、`SmartAgriBrain/` 和依赖/构建目录不得进入推送快照。
- 示例配置只能使用 `.env.example` 等不含真实密钥的文件。

## 修改后的必做验证

若修改 push 脚本，至少执行：

1. PowerShell 语法解析检查。
2. `push-frontend.ps1 -ValidateOnly`，确认无远端写入。
3. 在隔离测试目录验证无改动不产生空提交。
4. 验证断网时提交仍保留在持久队列，恢复后可由同一脚本继续推送。
5. 验证远端领先或非快进时不会 force push，冲突提交会保存在本地备份分支。
6. 检查提交内容中不存在 `.env`、token、私钥、缓存或嵌套仓库。

如果无法完成这些验证，不得声称脚本已经能够安全推送。
