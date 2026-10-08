import { TraderCockpitView } from '@/components/cockpit/TraderCockpitView';

export const metadata = {
  title: '交易员驾驶舱 · AI认知复盘交易系统',
  description: '7问第一屏与三层倒金字塔架构',
};

export default function CockpitPage() {
  return <TraderCockpitView initialDate="2026-10-08" />;
}
