import { AuroraCockpitView } from '@/components/cockpit/AuroraCockpitView';

export const metadata = {
  title: '交易复盘驾驶舱 · 极光暗夜流光版 · AI认知复盘交易系统',
  description: '极光暗夜流光版 Bento Grid 交易复盘驾驶舱，全景呈现大盘天气、连板天梯、题材战场与极端对冲池',
};

export default function CockpitPage() {
  return <AuroraCockpitView initialDate="2026-10-08" />;
}
