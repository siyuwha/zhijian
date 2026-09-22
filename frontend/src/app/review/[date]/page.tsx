import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default async function ReviewDetail({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">复盘报告: {date}</h2>
        <p className="text-slate-400">系统自动生成的深度复盘分析</p>
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-teal-400">大盘总览</CardTitle>
        </CardHeader>
        <CardContent className="text-slate-300 leading-relaxed space-y-4">
          <p>今日两市探底回升，三大指数全线收涨。早盘受外盘影响低开，随后在算力、通信等科技方向带领下震荡走高。两市成交额达8500亿，较昨日放量明显。北向资金净流入45亿元。</p>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-teal-400">涨停分析</CardTitle>
        </CardHeader>
        <CardContent className="text-slate-300 leading-relaxed space-y-4">
          <p>全市场涨停45家，跌停12家。连板最高标突破至5板，短线情绪显著回暖。其中，人工智能产业链表现抢眼，算力分支涨停家数最多，呈现明显的资金合力特征。</p>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-teal-400">板块归因</CardTitle>
        </CardHeader>
        <CardContent className="text-slate-300 leading-relaxed space-y-4">
          <p>领涨板块：算力租赁、光通信、CPO。逻辑支撑为海外科技巨头财报超预期及国内算力基础设施建设加速。资金主要流入科技成长方向，防守属性的医药、消费表现平淡。</p>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-teal-400">市场状态 & 明日推演</CardTitle>
        </CardHeader>
        <CardContent className="text-slate-300 leading-relaxed space-y-4">
          <p>当前市场处于混沌期向主升期过渡阶段。主线逐渐清晰，赚钱效应集中在泛科技方向。明日重点观察核心标的能否继续拓宽连板空间，以及量能是否持续放大。策略上建议轻指数重个股，聚焦主线核心人气股。</p>
        </CardContent>
      </Card>
    </div>
  );
}
