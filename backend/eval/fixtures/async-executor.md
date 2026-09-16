# 异步编排与线程池的边界

## 什么该丢给线程池

只有阻塞式调用才需要线程池：JDBC、同步 HTTP 客户端这类。纯计算任务丢进线程池只会增加上下文切换开销，反而更慢。

## 与 CompletableFuture 的关系

CompletableFuture 负责编排依赖关系，真正的执行仍然落在某个线程池上。默认使用的 ForkJoinPool.commonPool 线程数有限，阻塞任务必须换成独立线程池。

## 常见误用

在 commonPool 上跑阻塞任务会把公共池占满，进而影响整个 JVM 的并行流，表现为"别处莫名其妙变慢"。
