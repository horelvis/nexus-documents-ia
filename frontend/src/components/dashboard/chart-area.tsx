"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp } from "lucide-react";

// Simple chart component without external dependencies
export function ChartArea() {
  // Mock data for document activity over time
  const chartData = [
    { month: "Jan", documents: 5 },
    { month: "Feb", documents: 8 },
    { month: "Mar", documents: 12 },
    { month: "Apr", documents: 15 },
    { month: "May", documents: 20 },
    { month: "Jun", documents: 25 },
  ];

  const maxValue = Math.max(...chartData.map(item => item.documents));
  const totalDocuments = chartData.reduce((sum, item) => sum + item.documents, 0);
  const averageGrowth = ((chartData[chartData.length - 1].documents - chartData[0].documents) / chartData[0].documents * 100).toFixed(1);

  return (
    <Card>
      <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 sm:flex-row">
        <div className="flex flex-1 flex-col justify-center gap-1 px-6 py-5 sm:py-6">
          <CardTitle>Document Activity</CardTitle>
          <CardDescription>
            Showing document uploads over the last 6 months
          </CardDescription>
        </div>
        <div className="flex">
          <div className="relative z-30 flex flex-1 flex-col justify-center gap-1 border-t px-6 py-4 text-left even:border-l data-[active=true]:bg-muted/50 sm:border-l sm:border-t-0 sm:px-8 sm:py-6">
            <span className="text-xs text-muted-foreground">
              Total Documents
            </span>
            <span className="text-lg font-bold leading-none sm:text-3xl">
              {totalDocuments}
            </span>
          </div>
          <div className="relative z-30 flex flex-1 flex-col justify-center gap-1 border-t px-6 py-4 text-left even:border-l data-[active=true]:bg-muted/50 sm:border-l sm:border-t-0 sm:px-8 sm:py-6">
            <span className="text-xs text-muted-foreground">
              Growth Rate
            </span>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold leading-none sm:text-3xl">
                {averageGrowth}%
              </span>
              <Badge variant="outline" className="text-green-600">
                <TrendingUp className="h-3 w-3 mr-1" />
                Trending up
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-2 sm:p-6">
        <div className="aspect-auto h-[250px] w-full">
          {/* Simple SVG chart */}
          <div className="flex h-full items-end justify-between px-4">
            {chartData.map((item, index) => (
              <div key={item.month} className="flex flex-col items-center gap-2">
                <div
                  className="w-8 bg-primary rounded-t transition-all duration-300 hover:bg-primary/80"
                  style={{
                    height: `${(item.documents / maxValue) * 200}px`,
                    minHeight: '4px'
                  }}
                />
                <span className="text-xs text-muted-foreground">
                  {item.month}
                </span>
                <span className="text-xs font-medium">
                  {item.documents}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}