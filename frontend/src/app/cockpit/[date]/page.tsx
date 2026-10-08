import { TraderCockpitView } from '@/components/cockpit/TraderCockpitView';

interface PageProps {
  params: Promise<{ date: string }>;
}

export default async function CockpitDatePage({ params }: PageProps) {
  const { date } = await params;
  return <TraderCockpitView initialDate={date} />;
}
