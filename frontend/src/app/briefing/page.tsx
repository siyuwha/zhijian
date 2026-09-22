import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";

export default function BriefingPage() {
  const briefings = [
    { date: "2023-10-26", title: "盘前简报：美股科技股重挫，A股如何应对？", id: "2023-10-26" },
    { date: "2023-10-25", title: "盘前简报：利好频出，关注大金融动向", id: "2023-10-25" },
  ];

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white">盘前简报</h2>
      </div>

      <div className="space-y-4">
        {briefings.map((brief) => (
          <Link key={brief.id} href={`/briefing/${brief.id}`}>
            <Card className="bg-slate-900 border-slate-800 hover:border-teal-500/50 transition-colors cursor-pointer mb-4">
              <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="text-sm text-teal-400 mb-1">{brief.date}</div>
                  <h3 className="text-lg font-medium text-slate-200">{brief.title}</h3>
                </div>
                <div className="text-sm text-slate-400">查看详情 &rarr;</div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
