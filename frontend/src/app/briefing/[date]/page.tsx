import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default async function BriefingDetail({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">盘前简报: {date}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-teal-400">隔夜外盘</CardTitle>
          </CardHeader>
          <CardContent className="text-slate-300 space-y-2">
            <p>道琼斯指数收涨0.12%，纳斯达克指数受大型科技股拖累下跌1.5%。热门中概股涨跌不一。</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-teal-400">财经快讯</CardTitle>
          </CardHeader>
          <CardContent className="text-slate-300 space-y-2">
            <ul className="list-disc pl-5 space-y-1">
              <li>国常会部署加快推进基础设施建设</li>
              <li>多部门发文促消费，汽车家电下乡迎利好</li>
              <li>某芯片巨头宣布突破先进制程工艺</li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-slate-900 border-slate-800 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-teal-400">昨日回顾 & 今日关注</CardTitle>
          </CardHeader>
          <CardContent className="text-slate-300 space-y-4">
            <div>
              <h4 className="font-semibold text-slate-100 mb-1">昨日核心</h4>
              <p>算力概念掀涨停潮，高标龙头晋级5连板，确立短期主线地位。</p>
            </div>
            <div>
              <h4 className="font-semibold text-slate-100 mb-1">今日推演</h4>
              <p>受外盘科技股大跌影响，今日早盘相关概念大概率承压低开。重点关注核心标的低开后的承接力度。若能抗住分歧强势翻红，则主线地位进一步巩固；否则需防范短期退潮风险。大金融、消费等低位板块存在防守轮动可能。</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
