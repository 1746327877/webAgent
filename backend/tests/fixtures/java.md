# Java 并发小样例（供入库/检索手工验证与后续 seed 使用）

## 线程池

`ExecutorService` 是线程池的核心接口，`ThreadPoolExecutor` 提供可调参实现。

## 内存模型

`volatile` 保证可见性与有序性，`synchronized` 额外保证原子性。
