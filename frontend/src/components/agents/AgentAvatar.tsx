import { avatarColor, avatarInitial } from "@/lib/avatar";
import { useAgentAvatarUrl } from "@/lib/useAgentAvatarUrl";
import { cn } from "cn";

export interface AgentAvatarProps {
  agentId?: string;
  name: string;
  /** 是否已上传头像（来自接口的 has_avatar） */
  hasAvatar?: boolean;
  /** 头像版本（一般传 updated_at），变化时重新拉取 */
  version?: string;
  /** 本地预览（新建时选中文件、尚未上传）优先于远端头像 */
  previewUrl?: string;
  className?: string;
}

/** 智能体头像：有图片用图片，否则用名字首字。尺寸/字号由 className 指定。 */
export default function AgentAvatar({
  agentId,
  name,
  hasAvatar = false,
  version,
  previewUrl,
  className,
}: AgentAvatarProps) {
  const remoteUrl = useAgentAvatarUrl(hasAvatar ? agentId : undefined, version);
  const url = previewUrl ?? remoteUrl;
  const base = "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full";

  if (url) {
    return (
      <img src={url} alt={`${name} 头像`} className={cn(base, "object-cover", className)} />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(base, "font-medium text-white", avatarColor(name), className)}
    >
      {avatarInitial(name)}
    </span>
  );
}
