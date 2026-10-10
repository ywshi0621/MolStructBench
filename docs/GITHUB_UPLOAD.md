# GitHub 上传准备

本目录可作为独立仓库根目录。只上传该目录，不上传旧开发工作区或历史私人结果包。
预编译 OpenCode 大文件、个人配置/密钥、缓存、运行日志与输出在 .gitignore 中排除。
开源目录不包含 .git 历史；先检查 git status，再由仓库拥有者初始化和设置自己的远程地址。
WITHOUT_HARNESS 没有 Harness 依赖；WITH_HARNESS 安装时下载固定上游二进制并校验 hash。
两个 GitHub 仓库或同一组织下的两个发行仓库均可，当前不自动创建、推送或公开发布远程仓库。
