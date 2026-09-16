import { useParams } from "react-router-dom";
import TraceView from "@/components/admin/TraceView";

/** 独立路由页：聊天页「查看调用链」深链 /admin/sessions/:id；内容与可观测性「调用链」标签共用 TraceView。 */
export default function AdminTracePage() {
  const { sessionId } = useParams();
  return (
    <TraceView
      sessionId={sessionId}
      // 左上角「←」直接回到该会话的对话，不必再点侧边栏
      backTo={`/sessions/${sessionId}`}
      backLabel="返回对话"
    />
  );
}
