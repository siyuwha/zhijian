import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

export default function ReviewPage() {
  const reviews = [
    { date: "2023-10-25", title: "指数探底回升，AI主线再度走强", id: "2023-10-25" },
    { date: "2023-10-24", title: "市场缩量震荡，高标分歧加剧", id: "2023-10-24" },
    { date: "2023-10-23", title: "普跌格局，耐心等待企稳信号", id: "2023-10-23" },
  ];

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-white">每日复盘</h2>
      </div>

      <div className="space-y-4">
        {reviews.map((review) => (
          <Link key={review.id} href={`/review/${review.id}`}>
            <Card className="bg-slate-900 border-slate-800 hover:border-teal-500/50 transition-colors cursor-pointer mb-4">
              <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="text-sm text-teal-400 mb-1">{review.date}</div>
                  <h3 className="text-lg font-medium text-slate-200">{review.title}</h3>
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
